#!/usr/bin/env python3
"""Dependency-free CLI client for Cove Download Manager's official local API.

The program is intentionally a control-plane tool: download bytes flow directly
between aria2 and the remote server. Every command writes one JSON object to
stdout so tool-capable language models can consume it predictably.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlsplit


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = APP_DIR / "wrapper_config.json"
ALLOWED_SCHEMES = {"http", "https", "ftp", "magnet"}
MAX_CONNECTIONS_PER_SERVER = 16
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class CoveApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Any | None = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.exit_code = exit_code


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CoveApiError("invalid_arguments", message, exit_code=2)


@dataclass(frozen=True)
class LoadedSettings:
    path: Path
    values: dict[str, Any]


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normcase(os.path.abspath(os.fspath(path)))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def settings_candidates(explicit: str | None = None) -> list[Path]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("COVE_SETTINGS"):
        candidates.append(Path(os.environ["COVE_SETTINGS"]).expanduser())

    # Portable installs normally place the wrapper beside Cove.
    parent = APP_DIR.parent
    candidates.extend(
        [
            parent / "cove-app-data" / "cove-download-manager" / "settings.json",
            parent / "cove-app-data" / "settings.json",
        ]
    )

    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / ".config" / "cove" / "settings.json")
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        candidates.append(Path(xdg_config) / "cove" / "settings.json")
    candidates.append(Path.home() / ".config" / "cove" / "settings.json")
    return _dedupe_paths(candidates)


def load_settings(explicit: str | None = None) -> LoadedSettings:
    candidates = settings_candidates(explicit)
    selected: Path | None = None
    inaccessible: list[dict[str, str]] = []
    for path in candidates:
        try:
            if path.is_file():
                selected = path
                break
        except OSError as exc:
            inaccessible.append({"path": str(path), "reason": str(exc)})
    if selected is None:
        raise CoveApiError(
            "settings_not_found",
            "Cove settings were not found. Launch Cove once, or pass --settings PATH.",
            details={"checked": [str(path) for path in candidates], "inaccessible": inaccessible},
            exit_code=2,
        )
    try:
        values = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoveApiError(
            "settings_invalid",
            f"Could not read Cove settings: {exc}",
            details={"path": str(selected)},
            exit_code=2,
        ) from exc

    if not isinstance(values, dict):
        raise CoveApiError("settings_invalid", "Cove settings must contain a JSON object.", exit_code=2)
    token = values.get("api_token")
    port = values.get("api_port", 17681)
    if not isinstance(token, str) or len(token) < 24:
        raise CoveApiError(
            "settings_invalid",
            "Cove's API token is missing or invalid. Run an API-enabled Cove build once.",
            details={"path": str(selected)},
            exit_code=2,
        )
    try:
        if isinstance(port, bool):
            raise ValueError
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise CoveApiError("settings_invalid", "Cove's API port is invalid.", exit_code=2) from exc
    if not 1 <= port <= 65535:
        raise CoveApiError("settings_invalid", "Cove's API port is out of range.", exit_code=2)
    values["api_port"] = port
    return LoadedSettings(selected.resolve(), values)


def load_wrapper_config(path: str | None = None) -> tuple[Path, dict[str, Any]]:
    selected = Path(path or os.environ.get("COVE_API_CONFIG", DEFAULT_CONFIG_PATH)).expanduser()
    defaults: dict[str, Any] = {
        "auto_start_cove": True,
        "cove_executable": "",
        "cove_startup_timeout_seconds": 30,
        "allow_any_absolute_directory": True,
        "allowed_download_roots": [str(APP_DIR.parent)],
        "allow_cove_default_directory": True,
        "max_connections": MAX_CONNECTIONS_PER_SERVER,
        "api_timeout_seconds": 10,
    }
    if not selected.is_file():
        return selected.resolve(), defaults
    try:
        loaded = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoveApiError(
            "wrapper_config_invalid",
            f"Could not read wrapper configuration: {exc}",
            details={"path": str(selected)},
            exit_code=2,
        ) from exc
    if not isinstance(loaded, dict):
        raise CoveApiError("wrapper_config_invalid", "Wrapper configuration must be an object.", exit_code=2)
    defaults.update(loaded)
    return selected.resolve(), defaults


def cove_executable_candidates(config: dict[str, Any]) -> list[Path]:
    """Return configured and conventional portable-build locations.

    An installed client is normally placed beside Cove. A client run from the
    source tree also checks the repository's ignored ``release`` directory.
    No version number is hard-coded, so future releases continue to work.
    """
    configured = config.get("cove_executable") or os.environ.get("COVE_EXECUTABLE")
    if configured:
        return [_canonical(configured)]

    roots = [APP_DIR.parent, APP_DIR.parent / "release"]
    if len(APP_DIR.parents) > 1:
        roots.append(APP_DIR.parents[1] / "release")
    found: list[Path] = []
    for root in _dedupe_paths(roots):
        if not root.is_dir():
            continue
        found.extend(root.glob("Cove-Download-Manager-*-Portable.exe"))
        found.extend(root.glob("cove-download-manager-portable.exe"))
    found = _dedupe_paths(found)
    found.sort(
        key=lambda path: (path.stat().st_mtime if path.is_file() else 0, path.name),
        reverse=True,
    )
    return found or [APP_DIR.parent / "Cove-Download-Manager-Portable.exe"]


def resolve_cove_executable(config: dict[str, Any]) -> Path:
    candidates = cove_executable_candidates(config)
    return next((path for path in candidates if path.is_file()), candidates[0])


def validate_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoveApiError("invalid_url", "A non-empty download URL is required.", exit_code=5)
    value = value.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise CoveApiError("invalid_url", "Control characters are not allowed in URLs.", exit_code=5)
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise CoveApiError("invalid_url", "The URL is malformed.", exit_code=5) from exc
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise CoveApiError(
            "invalid_url",
            f"URL scheme '{scheme or '(missing)'}' is not allowed.",
            details={"allowed_schemes": sorted(ALLOWED_SCHEMES)},
            exit_code=5,
        )
    if scheme in {"http", "https", "ftp"} and not parsed.netloc:
        raise CoveApiError("invalid_url", "The URL must include a host.", exit_code=5)
    if scheme == "magnet" and not parsed.query:
        raise CoveApiError("invalid_url", "The magnet URI has no query payload.", exit_code=5)
    return value


def validate_filename(value: str | None) -> str | None:
    if value is None:
        return None
    if not value or value in {".", ".."}:
        raise CoveApiError("invalid_filename", "The filename is empty or reserved.", exit_code=5)
    if len(value) > 255:
        raise CoveApiError("invalid_filename", "The filename is too long.", exit_code=5)
    if any(char in value for char in '/\\:<>"|?*'):
        raise CoveApiError(
            "invalid_filename",
            "The filename must be a basename without reserved characters.",
            exit_code=5,
        )
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise CoveApiError("invalid_filename", "Control characters are not allowed in filenames.", exit_code=5)
    if value.endswith((" ", ".")):
        raise CoveApiError("invalid_filename", "Windows filenames may not end with a space or period.", exit_code=5)
    stem = value.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        raise CoveApiError("invalid_filename", "The filename is reserved by Windows.", exit_code=5)
    return value


def validate_task_id(value: Any) -> int:
    if isinstance(value, bool):
        raise CoveApiError("invalid_task_id", "Cove task IDs must be positive integers.", exit_code=5)
    try:
        task_id = int(value)
    except (TypeError, ValueError) as exc:
        raise CoveApiError("invalid_task_id", "Cove task IDs must be positive integers.", exit_code=5) from exc
    if task_id <= 0 or str(task_id) != str(value).strip():
        raise CoveApiError("invalid_task_id", "Cove task IDs must be positive integers.", exit_code=5)
    return task_id


def _canonical(path: str | Path) -> Path:
    expanded = os.path.expandvars(os.fspath(path))
    return Path(expanded).expanduser().resolve(strict=False)


def _is_within(path: Path, root: Path) -> bool:
    try:
        common = os.path.commonpath(
            [os.path.normcase(str(path)), os.path.normcase(str(root))]
        )
        return common == os.path.normcase(str(root))
    except ValueError:
        return False


def allowed_roots(settings: dict[str, Any], config: dict[str, Any]) -> list[Path]:
    raw_roots = config.get("allowed_download_roots", [])
    if not isinstance(raw_roots, list) or not all(isinstance(item, str) for item in raw_roots):
        raise CoveApiError(
            "wrapper_config_invalid",
            "allowed_download_roots must be a list of paths.",
            exit_code=2,
        )
    roots = [_canonical(item) for item in raw_roots]
    if config.get("allow_cove_default_directory", True) and settings.get("download_dir"):
        roots.append(_canonical(settings["download_dir"]))
    return _dedupe_paths(roots)


def resolve_directory(
    requested: str | None,
    settings: dict[str, Any],
    config: dict[str, Any],
    *,
    create: bool = False,
) -> Path:
    chosen = requested or settings.get("download_dir")
    if not chosen:
        raise CoveApiError("directory_missing", "No download directory was supplied or configured.", exit_code=5)
    expanded = Path(os.path.expandvars(os.fspath(chosen))).expanduser()
    if not expanded.is_absolute():
        raise CoveApiError("directory_not_absolute", "The download directory must be absolute.", exit_code=5)
    path = expanded.resolve(strict=False)
    if not config.get("allow_any_absolute_directory", True):
        roots = allowed_roots(settings, config)
        if not any(_is_within(path, root) for root in roots):
            raise CoveApiError(
                "directory_not_allowed",
                "The requested directory is outside the wrapper's allowed roots.",
                details={"directory": str(path), "allowed_roots": [str(root) for root in roots]},
                exit_code=5,
            )
    if path.exists() and not path.is_dir():
        raise CoveApiError("directory_invalid", "The destination exists but is not a directory.", exit_code=5)
    if not path.exists():
        if not create:
            raise CoveApiError(
                "directory_not_found",
                "The destination directory does not exist. Use --create-directory if intended.",
                details={"directory": str(path)},
                exit_code=5,
            )
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CoveApiError("directory_create_failed", str(exc), exit_code=5) from exc
    return path


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class CoveHttpClient:
    def __init__(self, settings: LoadedSettings, timeout: float) -> None:
        self.settings = settings
        self.endpoint = f"http://127.0.0.1:{settings.values['api_port']}/api/v1"
        self.token = settings.values["api_token"]
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urlrequest.Request(
            f"{self.endpoint}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urlerror.HTTPError as exc:
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
                server_error = error_payload.get("error", {})
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                server_error = {}
            code = server_error.get("code") or "api_http_error"
            message = server_error.get("message") or f"Cove's local API returned HTTP {exc.code}."
            exit_code = 5 if exc.code in {400, 411, 413, 415, 422} else 4
            raise CoveApiError(code, message, details={"http_status": exc.code}, exit_code=exit_code) from exc
        except (urlerror.URLError, TimeoutError, ConnectionError) as exc:
            raise CoveApiError(
                "cove_not_running",
                "Cove's official local API is not reachable. Launch Cove and try again.",
                details={"endpoint": self.endpoint, "reason": str(exc)},
                exit_code=3,
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise CoveApiError(
                "api_transport_error",
                f"Cove returned an invalid API response: {exc}",
                exit_code=3,
            ) from exc
        if not isinstance(data, dict):
            raise CoveApiError("api_transport_error", "Cove returned a non-object API response.", exit_code=3)
        if data.get("ok") is not True:
            api_error = data.get("error") if isinstance(data.get("error"), dict) else {}
            raise CoveApiError(
                api_error.get("code") or "api_error",
                api_error.get("message") or "Cove rejected the API request.",
                exit_code=4,
            )
        return data

    def health(self) -> dict[str, Any]:
        return self.request("GET", "/health", authenticated=False)


def ensure_cove_running(client: CoveHttpClient, config: dict[str, Any]) -> bool:
    """Return True when this call had to launch Cove, otherwise False."""
    initial_error: CoveApiError | None = None
    try:
        client.health()
        return False
    except CoveApiError as exc:
        if exc.code not in {"cove_not_running", "api_transport_error"}:
            raise
        if not config.get("auto_start_cove", True):
            raise
        initial_error = exc

    executable = resolve_cove_executable(config)
    if not executable.is_file() or executable.suffix.lower() != ".exe":
        raise CoveApiError(
            "cove_executable_not_found",
            "Cove could not be started because its executable was not found.",
            details={"path": str(executable)},
            exit_code=3,
        )

    try:
        startup_timeout = float(config.get("cove_startup_timeout_seconds", 30))
    except (TypeError, ValueError) as exc:
        raise CoveApiError(
            "wrapper_config_invalid",
            "cove_startup_timeout_seconds must be a number.",
            exit_code=2,
        ) from exc
    if not 1 <= startup_timeout <= 120:
        raise CoveApiError(
            "wrapper_config_invalid",
            "cove_startup_timeout_seconds must be between 1 and 120.",
            exit_code=2,
        )

    creation_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    try:
        subprocess.Popen(
            [str(executable)],
            cwd=str(executable.parent),
            close_fds=True,
            creationflags=creation_flags,
        )
    except OSError as exc:
        raise CoveApiError(
            "cove_start_failed",
            f"Windows could not launch Cove: {exc}",
            details={"path": str(executable)},
            exit_code=3,
        ) from exc

    deadline = time.monotonic() + startup_timeout
    assert initial_error is not None
    last_error = initial_error
    while time.monotonic() < deadline:
        time.sleep(0.25)
        try:
            client.health()
            return True
        except CoveApiError as exc:
            if exc.code not in {"cove_not_running", "api_transport_error"}:
                raise
            last_error = exc

    raise CoveApiError(
        "cove_start_timeout",
        "Cove was launched, but its official local API did not become ready in time.",
        details={"path": str(executable), "timeout_seconds": startup_timeout, "last_error": last_error.message},
        exit_code=3,
    )


def _client_metadata(settings: LoadedSettings, config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "settings_path": str(settings.path),
        "wrapper_config_path": str(config_path),
        "api_endpoint": f"http://127.0.0.1:{settings.values['api_port']}/api/v1",
        "auto_start_cove": bool(config.get("auto_start_cove", True)),
        "cove_executable": str(resolve_cove_executable(config)),
    }


def command_health(
    client: CoveHttpClient,
    settings: LoadedSettings,
    config_path: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    health = client.health()
    api_settings = client.request("GET", "/settings")["settings"]
    return {
        "ok": True,
        "command": "health",
        "service": health.get("service"),
        "api_version": health.get("api_version"),
        "cove_version": health.get("cove_version"),
        "settings": api_settings,
        **_client_metadata(settings, config_path, config),
    }


def command_settings(
    client: CoveHttpClient,
    settings: LoadedSettings,
    config_path: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ok": True,
        "command": "settings",
        "settings": client.request("GET", "/settings")["settings"],
        **_client_metadata(settings, config_path, config),
    }


def command_add(
    args: argparse.Namespace,
    client: CoveHttpClient,
    settings: LoadedSettings,
    config: dict[str, Any],
) -> dict[str, Any]:
    download_url = validate_url(args.url)
    filename = validate_filename(args.name)
    directory = None
    if args.directory is not None:
        directory = resolve_directory(
            args.directory,
            settings.values,
            config,
            create=args.create_directory,
        )
    elif args.create_directory:
        raise CoveApiError(
            "invalid_create_directory",
            "--create-directory requires --directory.",
            exit_code=5,
        )
    configured_max = _as_int(
        config.get("max_connections"), MAX_CONNECTIONS_PER_SERVER
    )
    hard_max = min(max(configured_max, 1), MAX_CONNECTIONS_PER_SERVER)
    connections = args.connections
    if connections is not None and not 1 <= connections <= hard_max:
        raise CoveApiError(
            "invalid_connections",
            f"Connections must be between 1 and {hard_max}.",
            exit_code=5,
        )
    if args.speed_limit_kbps is not None and args.speed_limit_kbps < 0:
        raise CoveApiError("invalid_speed_limit", "Speed limit cannot be negative.", exit_code=5)

    payload: dict[str, Any] = {"url": download_url}
    if directory is not None:
        payload["directory"] = str(directory)
        payload["create_directory"] = bool(args.create_directory)
    if filename:
        payload["filename"] = filename
    if args.connections is not None:
        payload["connections"] = connections
    if args.speed_limit_kbps is not None:
        payload["speed_limit_kbps"] = args.speed_limit_kbps

    download = client.request("POST", "/downloads", payload)["download"]
    return {
        "ok": True,
        "command": "add",
        "task_id": download["task_id"],
        "gid": download.get("gid"),
        "effective": {
            "directory": download["directory"],
            "filename": download.get("filename"),
            "connections": download["connections"],
            "speed_limit_kbps": download.get("speed_limit_kbps", 0),
            "used_cove_directory_default": args.directory is None,
            "used_cove_connection_default": args.connections is None,
        },
        "download": download,
    }


def command_list(args: argparse.Namespace, client: CoveHttpClient) -> dict[str, Any]:
    downloads = client.request("GET", "/downloads")["downloads"][: args.limit]
    return {
        "ok": True,
        "command": "list",
        "count": len(downloads),
        "downloads": downloads,
    }


def command_status(args: argparse.Namespace, client: CoveHttpClient) -> dict[str, Any]:
    task_id = validate_task_id(args.task_id)
    return {"ok": True, "command": "status", "download": client.request("GET", f"/downloads/{task_id}")["download"]}


def command_pause(args: argparse.Namespace, client: CoveHttpClient) -> dict[str, Any]:
    task_id = validate_task_id(args.task_id)
    download = client.request("POST", f"/downloads/{task_id}/pause", {})["download"]
    return {"ok": True, "command": "pause", "download": download}


def command_resume(args: argparse.Namespace, client: CoveHttpClient) -> dict[str, Any]:
    task_id = validate_task_id(args.task_id)
    download = client.request("POST", f"/downloads/{task_id}/resume", {})["download"]
    return {"ok": True, "command": "resume", "download": download}


def command_cancel(args: argparse.Namespace, client: CoveHttpClient) -> dict[str, Any]:
    task_id = validate_task_id(args.task_id)
    download = client.request("POST", f"/downloads/{task_id}/cancel", {})["download"]
    return {
        "ok": True,
        "command": "cancel",
        "task_id": task_id,
        "gid": download.get("gid"),
        "download": download,
        "partial_file_kept": True,
        "note": "Cancellation never deletes downloaded or partial files.",
    }


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(description="Safe JSON CLI for Cove Download Manager")
    parser.add_argument("--settings", help="Explicit Cove settings.json path")
    parser.add_argument("--config", help="Explicit wrapper_config.json path")
    parser.add_argument("--timeout", type=float, help="Local API timeout in seconds")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="Check Cove's official local API")
    sub.add_parser("settings", help="Show safe current settings without local secrets")

    add = sub.add_parser("add", help="Add a download")
    add.add_argument("url")
    add.add_argument("--directory")
    add.add_argument("--name")
    add.add_argument("--connections", type=int)
    add.add_argument("--speed-limit-kbps", type=int)
    add.add_argument("--create-directory", action="store_true")

    listing = sub.add_parser("list", help="List Cove download tasks")
    listing.add_argument("--limit", type=int, default=100)

    for name, help_text in (
        ("status", "Get one download's status"),
        ("pause", "Pause one download"),
        ("resume", "Resume one download"),
        ("cancel", "Cancel one download without deleting files"),
    ):
        item = sub.add_parser(name, help=help_text)
        item.add_argument("task_id")
    return parser


def emit(payload: dict[str, Any], *, pretty: bool = False) -> None:
    print(json.dumps(payload, indent=2 if pretty else None, separators=None if pretty else (",", ":")))


def main(argv: list[str] | None = None) -> int:
    pretty = False
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        pretty = bool(args.pretty)
        settings = load_settings(args.settings)
        config_path, config = load_wrapper_config(args.config)

        timeout = args.timeout
        if timeout is None:
            try:
                timeout = float(config.get("api_timeout_seconds", config.get("rpc_timeout_seconds", 10)))
            except (TypeError, ValueError) as exc:
                raise CoveApiError(
                    "wrapper_config_invalid",
                    "api_timeout_seconds must be a number.",
                    exit_code=2,
                ) from exc
        if timeout <= 0 or timeout > 120:
            raise CoveApiError("invalid_timeout", "Timeout must be between 0 and 120 seconds.", exit_code=5)
        client = CoveHttpClient(settings, timeout)
        cove_started = ensure_cove_running(client, config)

        if args.command == "health":
            result = command_health(client, settings, config_path, config)
        elif args.command == "settings":
            result = command_settings(client, settings, config_path, config)
        elif args.command == "add":
            result = command_add(args, client, settings, config)
        elif args.command == "list":
            if not 1 <= args.limit <= 1000:
                raise CoveApiError("invalid_limit", "List limit must be between 1 and 1000.", exit_code=5)
            result = command_list(args, client)
        elif args.command == "status":
            result = command_status(args, client)
        elif args.command == "pause":
            result = command_pause(args, client)
        elif args.command == "resume":
            result = command_resume(args, client)
        elif args.command == "cancel":
            result = command_cancel(args, client)
        else:  # pragma: no cover - argparse enforces the choices
            raise CoveApiError("invalid_command", f"Unsupported command: {args.command}", exit_code=2)
        result["cove_started"] = cove_started
        emit(result, pretty=pretty)
        return 0
    except CoveApiError as exc:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {"code": exc.code, "message": exc.message},
        }
        if exc.details is not None:
            payload["error"]["details"] = exc.details
        emit(payload, pretty=pretty)
        return exc.exit_code
    except KeyboardInterrupt:
        emit({"ok": False, "error": {"code": "interrupted", "message": "Command interrupted."}}, pretty=pretty)
        return 130
    except Exception:
        emit(
            {
                "ok": False,
                "error": {
                    "code": "internal_error",
                    "message": "The Cove client could not complete the command.",
                },
            },
            pretty=pretty,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
