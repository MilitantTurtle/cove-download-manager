"""Tests for the shared entry dispatch.

Regression guard for the fork-bomb bug: the frozen PyInstaller launcher
(packaging/launcher.py) imported cove.app.run directly and ignored
--native-messaging, so a browser spawning the native host got a GUI window
instead of a stdio host. The browser then errored and respawned the host in
a loop, opening download-manager windows until the machine died.

Both `python -m cove` and the frozen launcher must route through
cove.entry.main so native-messaging mode is never skipped.
"""
import sys
from unittest.mock import MagicMock, patch

from cove import entry


def test_native_messaging_flag_routes_to_host_not_gui(monkeypatch):
    nm = MagicMock()
    monkeypatch.setattr("cove.native_messaging.main", nm)
    fake_app = MagicMock()

    with patch.dict(sys.modules, {"cove.app": fake_app}):
        rc = entry.main(["cove", "--native-messaging", "chrome-extension://x/"])

    assert rc == 0
    nm.assert_called_once()
    fake_app.run.assert_not_called()


def test_native_messaging_never_imports_gui(monkeypatch):
    # cove.app imports PySide6, which is absent in dev. If entry tried to
    # import it in host mode, this would raise. Returning cleanly proves the
    # GUI is never loaded when the native-messaging flag is present.
    monkeypatch.setattr("cove.native_messaging.main", MagicMock())
    sys.modules.pop("cove.app", None)

    rc = entry.main(["cove", "--native-messaging"])

    assert rc == 0


def test_no_flag_routes_to_gui(monkeypatch):
    nm = MagicMock()
    monkeypatch.setattr("cove.native_messaging.main", nm)
    fake_app = MagicMock()
    fake_app.run.return_value = 0

    with patch.dict(sys.modules, {"cove.app": fake_app}):
        rc = entry.main(["cove"])

    assert rc == 0
    fake_app.run.assert_called_once()
    nm.assert_not_called()
