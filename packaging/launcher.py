"""PyInstaller entry point for the cove-download-manager bundles.

PyInstaller treats the script as a top-level module, which would break
relative imports inside the package. Importing through the package keeps
them working.

All dispatch lives in cove.entry so the frozen binary handles
--native-messaging identically to `python -m cove`. Calling cove.app.run
directly here (skipping the flag check) caused a fork-bomb of GUI windows
when a browser spawned the native messaging host -- never do that again.
"""
from cove.entry import main

if __name__ == "__main__":
    raise SystemExit(main())
