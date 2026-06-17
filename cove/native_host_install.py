"""Auto-install native messaging host registration for Firefox-based browsers.

Called once on app startup. Refreshes whatever the platform needs so the
Cove extension can connect without manual setup.

POSIX (Linux/macOS): all Firefox-based browsers (Firefox, Zen, LibreWolf,
Waterfox, Floorp) read native-messaging-host manifests from
~/.mozilla/native-messaging-hosts/ (hardcoded in libxul). Some forks also
check their own config dir, so we write there too when it exists. For
Flatpak browsers, the sandbox hides the real ~/.mozilla/ behind an
ephemeral overlay, so we apply a user-level flatpak override granting
read-only access to the manifest directory and the org.freedesktop.Flatpak
portal so the wrapper can re-exec on the host via flatpak-spawn.

Windows: Firefox does NOT read any manifest directory. It discovers native
hosts only through the registry key
HKEY_CURRENT_USER\\SOFTWARE\\Mozilla\\NativeMessagingHosts\\<host>, whose
default value is the absolute path to the manifest JSON. Firefox launches
the manifest's `path` directly without arguments, so we point it at a .bat
wrapper that injects the --native-messaging flag the app needs.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

HOST_NAME = "cove_download_manager"
EXTENSION_ID = "cove-dm@cove-download-manager.net"

# Firefox on Windows discovers native messaging hosts ONLY through this
# registry key (the ~/.mozilla manifest directory is never consulted there).
_WIN_REGISTRY_KEY = r"SOFTWARE\Mozilla\NativeMessagingHosts"

_FORK_CONFIG_DIRS = [".librewolf", ".waterfox", ".floorp"]

_KNOWN_FLATPAK_IDS = {
    "org.mozilla.firefox",
    "app.zen_browser.zen",
    "io.github.nicoth.zen",
    "io.gitlab.librewolf-community",
    "net.waterfox.waterfox",
    "one.nicothin.nicothin",
}


def _host_command_parts() -> list[str]:
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return [appimage, "--native-messaging"]

    python = sys.executable or "python3"
    return [python, "-c", "from cove.native_messaging import main; main()"]


def _wrapper_script(parts: list[str]) -> str:
    quoted = " ".join(f'"{p}"' for p in parts)
    return (
        "#!/usr/bin/env bash\n"
        f"target=({quoted})\n"
        "if [ -e /.flatpak-info ] && command -v flatpak-spawn >/dev/null 2>&1; then\n"
        '    exec flatpak-spawn --host "${target[@]}"\n'
        "fi\n"
        'exec "${target[@]}"\n'
    )


def _manifest(wrapper_path: str) -> dict:
    return {
        "name": HOST_NAME,
        "description": "Cove Download Manager native messaging host",
        "path": wrapper_path,
        "type": "stdio",
        "allowed_extensions": [EXTENSION_ID],
    }


def _write_manifest(hosts_dir: Path, wrapper_content: str) -> None:
    hosts_dir.mkdir(parents=True, exist_ok=True)

    wrapper_path = hosts_dir / HOST_NAME
    wrapper_path.write_text(wrapper_content)
    wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IEXEC)

    manifest_path = hosts_dir / f"{HOST_NAME}.json"
    manifest_path.write_text(
        json.dumps(_manifest(str(wrapper_path)), indent=2) + "\n"
    )


def _browser_dirs() -> list[Path]:
    home = Path.home()
    dirs: list[Path] = []

    # Primary: all Firefox-based browsers check ~/.mozilla/
    dirs.append(home / ".mozilla" / "native-messaging-hosts")

    # Fork-specific dirs (patched libxul builds)
    for name in _FORK_CONFIG_DIRS:
        candidate = home / name / "native-messaging-hosts"
        if (home / name).is_dir():
            dirs.append(candidate)

    return dirs


def _apply_flatpak_overrides(manifest_dir: str) -> None:
    if not shutil.which("flatpak"):
        return

    flatpak_root = Path.home() / ".var" / "app"
    if not flatpak_root.is_dir():
        return

    for app_dir in flatpak_root.iterdir():
        if not app_dir.is_dir():
            continue
        app_id = app_dir.name
        if app_id not in _KNOWN_FLATPAK_IDS:
            continue
        try:
            subprocess.run(
                [
                    "flatpak", "override", "--user",
                    "--talk-name=org.freedesktop.Flatpak",
                    f"--filesystem={manifest_dir}:ro",
                    app_id,
                ],
                check=False,
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass


def _install_posix() -> list[str]:
    """Install manifests and apply Flatpak overrides (Linux/macOS).

    Returns list of directories where manifests were written.
    """
    parts = _host_command_parts()
    wrapper = _wrapper_script(parts)
    installed: list[str] = []

    for hosts_dir in _browser_dirs():
        if not hosts_dir.parent.exists():
            continue

        _write_manifest(hosts_dir, wrapper)
        installed.append(str(hosts_dir))

    if installed:
        try:
            _apply_flatpak_overrides(installed[0])
        except Exception:
            pass

    return installed


def _windows_host_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Local"
    return root / "Cove" / "native-messaging-hosts"


def _windows_command_parts() -> list[str]:
    if getattr(sys, "frozen", False):
        # Frozen build: the exe IS the host; re-launch it in host mode.
        return [sys.executable, "--native-messaging"]

    python = sys.executable or "python"
    return [python, "-m", "cove", "--native-messaging"]


def _windows_launcher(parts: list[str]) -> str:
    # Firefox launches the manifest `path` directly and cannot pass args, so
    # the .bat injects --native-messaging. %* forwards Firefox's own args
    # (manifest path + extension id), which the host ignores. CRLF required.
    quoted = " ".join(f'"{p}"' for p in parts)
    return "@echo off\r\n" + quoted + " %*\r\n"


def _install_windows() -> list[str]:
    """Register the native messaging host on Windows.

    Writes the manifest JSON + a .bat launcher under %LOCALAPPDATA%, then
    points the HKCU Mozilla NativeMessagingHosts registry key at the
    manifest. Returns the directory the manifest was written to.
    """
    import winreg

    hosts_dir = _windows_host_dir()
    hosts_dir.mkdir(parents=True, exist_ok=True)

    launcher_path = hosts_dir / f"{HOST_NAME}.bat"
    launcher_path.write_text(_windows_launcher(_windows_command_parts()))

    manifest_path = hosts_dir / f"{HOST_NAME}.json"
    manifest_path.write_text(
        json.dumps(_manifest(str(launcher_path)), indent=2) + "\n"
    )

    key = winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        f"{_WIN_REGISTRY_KEY}\\{HOST_NAME}",
        0,
        winreg.KEY_WRITE,
    )
    try:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, str(manifest_path))
    finally:
        winreg.CloseKey(key)

    return [str(hosts_dir)]


def install_native_hosts() -> list[str]:
    """Register the native messaging host for the current platform.

    Returns list of directories/locations that were written.
    """
    if sys.platform == "win32":
        return _install_windows()
    return _install_posix()
