"""Auto-install native messaging host manifests for Firefox-based browsers.

Called once on app startup. Writes (or refreshes) the JSON manifest and
wrapper script into each browser's native-messaging-hosts directory so the
Cove extension can connect without manual setup.

Supports native and Flatpak installs of Firefox, Zen, LibreWolf, Waterfox,
and Floorp.
"""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

HOST_NAME = "cove_download_manager"
EXTENSION_ID = "cove-dm@cove-download-manager.net"

_BROWSER_CONFIG_NAMES = [".mozilla", ".zen", ".librewolf", ".waterfox", ".floorp"]


def _browser_dirs() -> list[Path]:
    """Collect every native-messaging-hosts dir that should get a manifest.

    Covers two cases:
    1. Native installs: ~/.mozilla/native-messaging-hosts, ~/.zen/..., etc.
    2. Flatpak installs: ~/.var/app/<app-id>/.mozilla/..., etc.
       Flatpak sandboxes the home directory, so a Flatpak Zen browser sees
       ~/.var/app/<id>/.zen/ instead of ~/.zen/.  We scan ~/.var/app/*/
       for any of the known browser config dirs.
    """
    home = Path.home()
    dirs: list[Path] = []

    for name in _BROWSER_CONFIG_NAMES:
        dirs.append(home / name / "native-messaging-hosts")

    flatpak_root = home / ".var" / "app"
    if flatpak_root.is_dir():
        try:
            for app_dir in flatpak_root.iterdir():
                if not app_dir.is_dir():
                    continue
                for name in _BROWSER_CONFIG_NAMES:
                    candidate = app_dir / name / "native-messaging-hosts"
                    if (app_dir / name).is_dir():
                        dirs.append(candidate)
        except OSError:
            pass

    return dirs


def _wrapper_command() -> str:
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return f'exec "{appimage}" --native-messaging'

    python = sys.executable or "python3"
    return f'exec "{python}" -c "from cove.native_messaging import main; main()"'


def _manifest(wrapper_path: str) -> dict:
    return {
        "name": HOST_NAME,
        "description": "Cove Download Manager native messaging host",
        "path": wrapper_path,
        "type": "stdio",
        "allowed_extensions": [EXTENSION_ID],
    }


def install_native_hosts() -> list[str]:
    """Install manifests into every browser dir whose parent exists.

    Returns list of directories where manifests were written.
    """
    command = _wrapper_command()
    installed: list[str] = []

    for hosts_dir in _browser_dirs():
        if not hosts_dir.parent.exists():
            continue

        hosts_dir.mkdir(parents=True, exist_ok=True)

        wrapper_path = hosts_dir / HOST_NAME
        wrapper_path.write_text(f"#!/usr/bin/env bash\n{command}\n")
        wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IEXEC)

        manifest_path = hosts_dir / f"{HOST_NAME}.json"
        manifest_path.write_text(json.dumps(_manifest(str(wrapper_path)), indent=2) + "\n")

        installed.append(str(hosts_dir))

    return installed
