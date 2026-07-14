"""Single entry-point dispatch for every way Cove is launched.

Both `python -m cove` (cove/__main__.py) and the frozen PyInstaller binaries
(`packaging/launcher.py` and `packaging/portable_launcher.py`) MUST route
through here.

Why this exists: a browser starts the native messaging host by executing the
registered command. If that command lands in the GUI instead of the stdio
host, the GUI can't complete the native-messaging handshake, the browser
reports a connection error and immediately respawns the host -- an endless
loop of download-manager windows that can take the machine down. The frozen
launcher used to import cove.app.run directly and never checked the flag,
which is exactly how that loop shipped. Centralizing the dispatch keeps the
two entry points from drifting apart again.
"""
from __future__ import annotations

import sys

NATIVE_MESSAGING_FLAG = "--native-messaging"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if NATIVE_MESSAGING_FLAG in argv:
        # Import lazily so the GUI stack (PySide6) is never loaded in host
        # mode.
        from .native_messaging import main as nm_main
        nm_main()
        return 0

    from .app import run
    return run()
