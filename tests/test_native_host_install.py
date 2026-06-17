"""Tests for native messaging host registration across platforms.

Focuses on the Windows path (registry + .bat launcher), which has no
equivalent to the POSIX manifest-directory discovery and so must register
the host through HKCU\\SOFTWARE\\Mozilla\\NativeMessagingHosts.
"""
import json
import sys
from unittest.mock import MagicMock, patch

from cove import native_host_install as nhi


def test_windows_command_parts_frozen():
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", r"C:\App\cove-download-manager.exe"):
        parts = nhi._windows_command_parts()
    assert parts == [r"C:\App\cove-download-manager.exe", "--native-messaging"]


def test_windows_command_parts_dev():
    with patch.object(sys, "frozen", False, create=True), \
         patch.object(sys, "executable", r"C:\Py\python.exe"):
        parts = nhi._windows_command_parts()
    assert parts == [r"C:\Py\python.exe", "-m", "cove", "--native-messaging"]


def test_windows_launcher_injects_flag_and_forwards_args():
    bat = nhi._windows_launcher([r"C:\App\cove.exe", "--native-messaging"])
    assert "--native-messaging" in bat
    # Forwards Firefox's manifest-path / extension-id args to the host.
    assert bat.rstrip().endswith("%*")
    assert "@echo off" in bat
    # Windows batch files need CRLF line endings.
    assert "\r\n" in bat


def test_manifest_fields():
    m = nhi._manifest(r"C:\hosts\cove_download_manager.bat")
    assert m["name"] == nhi.HOST_NAME
    assert m["type"] == "stdio"
    assert m["path"] == r"C:\hosts\cove_download_manager.bat"
    assert nhi.EXTENSION_ID in m["allowed_extensions"]


def test_install_windows_writes_manifest_launcher_and_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    fake_winreg = MagicMock()
    fake_winreg.HKEY_CURRENT_USER = 0
    fake_winreg.REG_SZ = 1

    with patch.dict(sys.modules, {"winreg": fake_winreg}), \
         patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", r"C:\App\cove-download-manager.exe"):
        installed = nhi._install_windows()

    hosts_dir = tmp_path / "Cove" / "native-messaging-hosts"
    manifest = hosts_dir / "cove_download_manager.json"
    launcher = hosts_dir / "cove_download_manager.bat"

    assert manifest.is_file()
    assert launcher.is_file()
    assert str(hosts_dir) in installed

    data = json.loads(manifest.read_text())
    assert data["path"] == str(launcher)

    # The launcher must invoke the frozen exe with the native-messaging flag.
    bat = launcher.read_text()
    assert "cove-download-manager.exe" in bat
    assert "--native-messaging" in bat

    # Registry: per-host key created, default value points at the manifest.
    fake_winreg.CreateKeyEx.assert_called_once()
    set_args = fake_winreg.SetValueEx.call_args[0]
    assert set_args[-1] == str(manifest)


def test_install_dispatch_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    with patch.object(nhi, "_install_windows", return_value=["WIN"]) as win, \
         patch.object(nhi, "_install_posix", return_value=["POSIX"]) as posix:
        assert nhi.install_native_hosts() == ["WIN"]
    win.assert_called_once()
    posix.assert_not_called()


def test_install_dispatch_posix(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with patch.object(nhi, "_install_windows", return_value=["WIN"]) as win, \
         patch.object(nhi, "_install_posix", return_value=["POSIX"]) as posix:
        assert nhi.install_native_hosts() == ["POSIX"]
    posix.assert_called_once()
    win.assert_not_called()
