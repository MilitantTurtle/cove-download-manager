import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cove_api


class ValidationTests(unittest.TestCase):
    def test_valid_https_url(self):
        value = "https://example.com/file.zip?download=true"
        self.assertEqual(cove_api.validate_url(value), value)

    def test_rejects_file_url(self):
        with self.assertRaises(cove_api.CoveApiError) as caught:
            cove_api.validate_url("file:///C:/Windows/win.ini")
        self.assertEqual(caught.exception.code, "invalid_url")

    def test_rejects_header_injection(self):
        with self.assertRaises(cove_api.CoveApiError):
            cove_api.validate_url("https://example.com/file\r\nX-Test: bad")

    def test_filename_is_a_basename(self):
        self.assertEqual(cove_api.validate_filename("model.gguf"), "model.gguf")
        for value in (
            "..",
            "folder/file.zip",
            "C:\\file.zip",
            "NUL.txt",
            "bad. ",
            "bad?.zip",
            "x" * 256,
        ):
            with self.subTest(value=value), self.assertRaises(cove_api.CoveApiError):
                cove_api.validate_filename(value)

    def test_task_id_validation(self):
        self.assertEqual(cove_api.validate_task_id("123"), 123)
        with self.assertRaises(cove_api.CoveApiError):
            cove_api.validate_task_id("not-an-id")


class DirectoryTests(unittest.TestCase):
    def test_rejects_relative_directory(self):
        config = {"allow_any_absolute_directory": True}
        with self.assertRaises(cove_api.CoveApiError) as caught:
            cove_api.resolve_directory("relative-folder", {}, config)
        self.assertEqual(caught.exception.code, "directory_not_absolute")

    def test_unrestricted_mode_allows_outside_configured_root(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            settings = {"download_dir": root}
            config = {
                "allow_any_absolute_directory": True,
                "allowed_download_roots": [root],
                "allow_cove_default_directory": True,
            }
            child = Path(root) / "models"
            resolved = cove_api.resolve_directory(str(child), settings, config, create=True)
            self.assertTrue(resolved.is_dir())
            self.assertEqual(cove_api.resolve_directory(outside, settings, config), Path(outside).resolve())

    def test_restricted_mode_still_enforces_configured_roots(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            settings = {"download_dir": root}
            config = {
                "allow_any_absolute_directory": False,
                "allowed_download_roots": [root],
                "allow_cove_default_directory": True,
            }
            with self.assertRaises(cove_api.CoveApiError) as caught:
                cove_api.resolve_directory(outside, settings, config)
            self.assertEqual(caught.exception.code, "directory_not_allowed")


class SettingsTests(unittest.TestCase):
    def test_rejects_boolean_api_port(self):
        with tempfile.TemporaryDirectory() as root:
            settings_path = Path(root) / "settings.json"
            settings_path.write_text(
                json.dumps({"api_token": "x" * 43, "api_port": True}),
                encoding="utf-8",
            )
            with self.assertRaises(cove_api.CoveApiError) as caught:
                cove_api.load_settings(str(settings_path))
            self.assertEqual(caught.exception.code, "settings_invalid")


    def test_rejects_disabled_api(self):
        with tempfile.TemporaryDirectory() as root:
            settings_path = Path(root) / "settings.json"
            settings_path.write_text(
                json.dumps({"api_token": "x" * 43, "api_port": 17681, "api_enabled": False}),
                encoding="utf-8",
            )
            with self.assertRaises(cove_api.CoveApiError) as caught:
                cove_api.load_settings(str(settings_path))
            self.assertEqual(caught.exception.code, "api_disabled")
            self.assertEqual(caught.exception.exit_code, 2)


class ExecutableDiscoveryTests(unittest.TestCase):
    def test_source_client_finds_portable_in_repository_release_directory(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            app_dir = repo / "tools" / "cove-api"
            release = repo / "release"
            app_dir.mkdir(parents=True)
            release.mkdir()
            executable = release / "Cove-Download-Manager-2.0.0-Portable.exe"
            executable.touch()
            with patch.object(cove_api, "APP_DIR", app_dir):
                self.assertEqual(cove_api.resolve_cove_executable({}), executable)

    def test_explicit_executable_takes_precedence(self):
        with tempfile.TemporaryDirectory() as root:
            executable = Path(root) / "Cove-Test.exe"
            executable.touch()
            resolved = cove_api.resolve_cove_executable(
                {"cove_executable": str(executable)}
            )
            self.assertEqual(resolved, executable.resolve())


class AddCommandTests(unittest.TestCase):
    def test_add_reads_signed_url_from_environment_without_modification(self):
        signed_url = "https://example.com/file.zip?sv=1&se=2&sig=abc%2Bdef"
        args = cove_api.build_parser().parse_args(
            ["add", "--url-env", "COVE_TEST_DOWNLOAD_URL"]
        )
        with patch.dict(os.environ, {"COVE_TEST_DOWNLOAD_URL": signed_url}):
            with tempfile.TemporaryDirectory() as root:
                settings = cove_api.LoadedSettings(
                    Path(root) / "settings.json",
                    {"download_dir": root},
                )

                class FakeClient:
                    def request(self, method, path, payload=None):
                        self.payload = payload
                        return {
                            "download": {
                                "task_id": 18,
                                "gid": None,
                                "status": "queued",
                                "directory": root,
                                "filename": None,
                                "connections": 16,
                                "speed_limit_kbps": 0,
                            }
                        }

                client = FakeClient()
                result = cove_api.command_add(
                    args,
                    client,
                    settings,
                    {"max_connections": 16},
                )

        self.assertTrue(result["ok"])
        self.assertEqual(client.payload["url"], signed_url)

    def test_add_requires_existing_url_environment_variable(self):
        args = cove_api.build_parser().parse_args(
            ["add", "--url-env", "COVE_TEST_MISSING_URL"]
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(cove_api.CoveApiError) as caught:
                cove_api.command_add(
                    args,
                    SimpleNamespace(),
                    SimpleNamespace(values={}),
                    {"max_connections": 16},
                )
        self.assertEqual(caught.exception.code, "url_environment_variable_not_found")

    def test_add_uses_current_cove_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            settings = cove_api.LoadedSettings(
                Path(root) / "settings.json",
                {
                    "download_dir": root,
                    "connections_per_server": 12,
                    "max_concurrent": 2,
                    "api_port": 17681,
                    "api_token": "x" * 43,
                },
            )
            config = {
                "allowed_download_roots": [root],
                "allow_cove_default_directory": True,
                "max_connections": 16,
            }

            class FakeClient:
                def __init__(self):
                    self.calls = []

                def request(self, method, path, payload=None):
                    self.calls.append((method, path, payload))
                    return {"download": {
                        "task_id": 17,
                        "gid": None,
                        "status": "queued",
                        "directory": root,
                        "filename": None,
                        "connections": 12,
                        "speed_limit_kbps": 0,
                    }}

            client = FakeClient()
            args = SimpleNamespace(
                url="https://example.com/file.bin",
                directory=None,
                name=None,
                connections=None,
                speed_limit_kbps=None,
                create_directory=False,
            )
            result = cove_api.command_add(args, client, settings, config)
            self.assertTrue(result["ok"])
            self.assertEqual(result["effective"]["connections"], 12)
            self.assertEqual(result["task_id"], 17)
            payload = client.calls[0][2]
            self.assertNotIn("directory", payload)
            self.assertNotIn("connections", payload)

    def test_add_rejects_more_than_stock_aria2_limit(self):
        with tempfile.TemporaryDirectory() as root:
            settings = cove_api.LoadedSettings(
                Path(root) / "settings.json",
                {
                    "download_dir": root,
                    "connections_per_server": 16,
                    "api_port": 17681,
                    "api_token": "x" * 43,
                },
            )
            args = SimpleNamespace(
                url="https://example.com/file.bin",
                directory=None,
                name=None,
                connections=17,
                speed_limit_kbps=None,
                create_directory=False,
            )

            with self.assertRaises(cove_api.CoveApiError) as caught:
                cove_api.command_add(
                    args,
                    SimpleNamespace(),
                    settings,
                    {"max_connections": 32},
                )

            self.assertEqual(caught.exception.code, "invalid_connections")
            self.assertIn("between 1 and 16", caught.exception.message)


@unittest.skipUnless(os.name == "nt", "Windows command launcher test")
class WindowsLauncherTests(unittest.TestCase):
    def test_cmd_preserves_signed_url_from_environment(self):
        signed_url = "https://example.com/file.zip?sv=1&se=2&sig=abc%2Bdef"
        received_payload = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def send_json(self, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.send_json({"ok": True})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                received_payload.update(json.loads(self.rfile.read(length)))
                self.send_json(
                    {
                        "ok": True,
                        "download": {
                            "task_id": 19,
                            "gid": None,
                            "status": "queued",
                            "directory": str(Path(tempfile.gettempdir()).resolve()),
                            "filename": None,
                            "connections": 16,
                            "speed_limit_kbps": 0,
                        },
                    }
                )

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as root:
                settings_path = Path(root) / "settings.json"
                settings_path.write_text(
                    json.dumps(
                        {
                            "api_port": server.server_port,
                            "api_token": "x" * 43,
                            "download_dir": root,
                        }
                    ),
                    encoding="utf-8",
                )
                config_path = Path(root) / "wrapper_config.json"
                config_path.write_text(
                    json.dumps({"auto_start_cove": False}),
                    encoding="utf-8",
                )
                environment = os.environ.copy()
                environment["COVE_TEST_DOWNLOAD_URL"] = signed_url
                launcher = Path(__file__).resolve().parents[1] / "cove-api.cmd"
                completed = subprocess.run(
                    [
                        str(launcher),
                        "--settings",
                        str(settings_path),
                        "--config",
                        str(config_path),
                        "add",
                        "--url-env",
                        "COVE_TEST_DOWNLOAD_URL",
                    ],
                    capture_output=True,
                    check=False,
                    env=environment,
                    text=True,
                    timeout=10,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["ok"])
        self.assertEqual(received_payload["url"], signed_url)


class CoveStartupTests(unittest.TestCase):
    def test_does_not_launch_when_rpc_is_already_ready(self):
        client = SimpleNamespace(health=lambda: {"ok": True})
        with patch.object(cove_api.subprocess, "Popen") as popen:
            self.assertFalse(cove_api.ensure_cove_running(client, {"auto_start_cove": True}))
        popen.assert_not_called()

    def test_launches_and_waits_for_rpc(self):
        with tempfile.TemporaryDirectory() as root:
            executable = Path(root) / "Cove.exe"
            executable.touch()

            class StartingClient:
                def __init__(self):
                    self.calls = 0

                def health(self):
                    self.calls += 1
                    if self.calls == 1:
                        raise cove_api.CoveApiError("cove_not_running", "offline", exit_code=3)
                    return {"ok": True}

            config = {
                "auto_start_cove": True,
                "cove_executable": str(executable),
                "cove_startup_timeout_seconds": 2,
            }
            with patch.object(cove_api.subprocess, "Popen") as popen, patch.object(cove_api.time, "sleep"):
                self.assertTrue(cove_api.ensure_cove_running(StartingClient(), config))
            popen.assert_called_once()


class ValidationDriftTests(unittest.TestCase):
    def test_rejects_whitespace_in_url_like_the_server(self):
        with self.assertRaises(cove_api.CoveApiError) as caught:
            cove_api.validate_url("https://example.com/a b")
        self.assertEqual(caught.exception.code, "invalid_url")


class ListCommandTests(unittest.TestCase):
    def test_limit_keeps_the_newest_tasks(self):
        class FakeClient:
            def request(self, method, path, payload=None):
                return {
                    "downloads": [
                        {"task_id": i, "status": "completed"} for i in range(1, 151)
                    ]
                }

        result = cove_api.command_list(SimpleNamespace(limit=100), FakeClient())
        task_ids = [d["task_id"] for d in result["downloads"]]
        self.assertEqual(len(task_ids), 100)
        self.assertIn(150, task_ids)
        self.assertNotIn(1, task_ids)


class TransientErrorTests(unittest.TestCase):
    def test_bridge_timeout_maps_to_retryable_exit_code(self):
        import io
        from urllib import error as urlerror

        body = json.dumps(
            {"ok": False, "error": {"code": "bridge_timeout", "message": "busy"}}
        ).encode("utf-8")
        http_error = urlerror.HTTPError(
            "http://127.0.0.1:17681/api/v1/downloads", 503, "Service Unavailable",
            {}, io.BytesIO(body),
        )

        settings = cove_api.LoadedSettings(
            Path("settings.json"), {"api_port": 17681, "api_token": "x" * 43}
        )
        client = cove_api.CoveHttpClient(settings, 1.0)
        with patch.object(cove_api.urlrequest, "urlopen", side_effect=http_error):
            with self.assertRaises(cove_api.CoveApiError) as caught:
                client.request("GET", "/downloads")
        self.assertEqual(caught.exception.code, "bridge_timeout")
        self.assertEqual(caught.exception.exit_code, 3)


class ControlCommandTests(unittest.TestCase):
    def test_cancel_uses_task_id_endpoint_and_keeps_files(self):
        class FakeClient:
            def __init__(self):
                self.call = None

            def request(self, method, path, payload=None):
                self.call = (method, path, payload)
                return {"download": {"task_id": 42, "gid": None, "status": "removed"}}

        client = FakeClient()
        result = cove_api.command_cancel(SimpleNamespace(task_id="42"), client)
        self.assertEqual(client.call, ("POST", "/downloads/42/cancel", {}))
        self.assertTrue(result["partial_file_kept"])
        self.assertEqual(result["task_id"], 42)


if __name__ == "__main__":
    unittest.main()
