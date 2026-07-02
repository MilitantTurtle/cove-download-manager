"""AppImage env scrubbing for external program launches.

Regression test for the bug where "Open File" / "Open Folder" launched
dolphin/mpv with the AppImage's LD_LIBRARY_PATH, so they loaded the
bundle's outdated liblzma and crashed with `version XZ_5.4 not found`.
"""

import os
from unittest import mock

from cove.system_open import child_env, _SCRUB_VARS


def test_child_env_is_none_outside_appimage(monkeypatch):
    monkeypatch.delenv("APPDIR", raising=False)
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert child_env() is None


def test_child_env_strips_loader_vars_inside_appimage(monkeypatch):
    monkeypatch.setenv("APPDIR", "/tmp/.mount_CoveXXXX")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/.mount_CoveXXXX/usr/lib:")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = child_env()
    assert env is not None
    assert "LD_LIBRARY_PATH" not in env
    for key in _SCRUB_VARS:
        assert key not in env
    assert env["PATH"] == "/usr/bin"
    # os.environ itself must be untouched (aria2c still needs bundle libs)
    assert os.environ["LD_LIBRARY_PATH"] == "/tmp/.mount_CoveXXXX/usr/lib:"


def test_child_env_triggers_on_appimage_var_alone(monkeypatch):
    monkeypatch.delenv("APPDIR", raising=False)
    monkeypatch.setenv("APPIMAGE", "/x/Cove.AppImage")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/x/usr/lib")
    env = child_env()
    assert env is not None and "LD_LIBRARY_PATH" not in env


def test_open_path_spawns_xdg_open_with_clean_env(monkeypatch, tmp_path):
    from cove import main_window

    monkeypatch.setenv("APPDIR", "/tmp/.mount_CoveXXXX")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/.mount_CoveXXXX/usr/lib:")
    monkeypatch.setattr(main_window.sys, "platform", "linux")
    monkeypatch.setattr(main_window.os, "name", "posix")
    monkeypatch.setattr(main_window.shutil, "which", lambda _: "/usr/bin/xdg-open")
    with mock.patch.object(main_window.subprocess, "Popen") as popen:
        assert main_window._open_path(tmp_path) is True
    args, kwargs = popen.call_args
    assert args[0][0] == "xdg-open"
    assert kwargs["env"] is not None
    assert "LD_LIBRARY_PATH" not in kwargs["env"]


def test_reveal_in_folder_spawns_with_clean_env(monkeypatch, tmp_path):
    from cove import main_window

    monkeypatch.setenv("APPDIR", "/tmp/.mount_CoveXXXX")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/.mount_CoveXXXX/usr/lib:")
    monkeypatch.setattr(main_window.sys, "platform", "linux")
    monkeypatch.setattr(main_window.os, "name", "posix")
    monkeypatch.setattr(main_window.shutil, "which", lambda _: "/usr/bin/xdg-open")
    f = tmp_path / "file.bin"
    f.write_bytes(b"x")
    with mock.patch.object(main_window.subprocess, "Popen") as popen:
        assert main_window._reveal_in_folder(f) is True
    args, kwargs = popen.call_args
    assert args[0] == ["xdg-open", str(tmp_path)]
    assert "LD_LIBRARY_PATH" not in kwargs["env"]
