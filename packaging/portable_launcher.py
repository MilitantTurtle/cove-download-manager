"""PyInstaller entry point for the one-file Windows portable build.

Portable mode must be selected before importing Cove because configuration
paths are resolved at module import time. A freshly downloaded single EXE has
no adjacent data directory or marker yet, so presence-based detection alone
would incorrectly write its first-run state into the user profile.
"""
import os

os.environ["COVE_PORTABLE"] = "1"

from cove.entry import main  # noqa: E402 - portable mode must be set first


if __name__ == "__main__":
    raise SystemExit(main())
