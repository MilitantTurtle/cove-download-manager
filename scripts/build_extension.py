#!/usr/bin/env python3
"""Build per-browser extension bundles from the shared extension/ source.

Approach A (see docs/superpowers/specs/2026-06-17-chrome-extension-support
-design.md): one shared codebase, the manifest swapped per browser.

  dist/firefox/  copy of extension/ (manifest.json is the MV2 manifest)
  dist/chrome/   copy of extension/ with manifest.chrome.json -> manifest.json

Each is also zipped as dist/cove-<browser>-<version>.zip. The private
signing key (chrome-key.pem) is never copied into a bundle.

Usage: python scripts/build_extension.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "extension"
DIST = ROOT / "dist"

# Files/dirs in extension/ that must never ship in a bundle.
_EXCLUDE = {"manifest.chrome.json", "chrome-key.pem"}


def _copy_shared(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in SRC.iterdir():
        if item.name in _EXCLUDE:
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _zip_dir(src_dir: Path, zip_path: Path) -> None:
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
        for path in sorted(src_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(src_dir))


def build() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)

    # Firefox: manifest.json is already the MV2 manifest.
    firefox = DIST / "firefox"
    _copy_shared(firefox)
    ff_version = json.loads((firefox / "manifest.json").read_text())["version"]
    _zip_dir(firefox, DIST / f"cove-firefox-{ff_version}.zip")

    # Chrome: swap in the MV3 manifest as manifest.json.
    chrome = DIST / "chrome"
    _copy_shared(chrome)
    mv3 = json.loads((SRC / "manifest.chrome.json").read_text())
    (chrome / "manifest.json").write_text(json.dumps(mv3, indent=2) + "\n")
    _zip_dir(chrome, DIST / f"cove-chrome-{mv3['version']}.zip")

    print(f"firefox: {firefox}  (v{ff_version})")
    print(f"chrome:  {chrome}  (v{mv3['version']})")
    for z in sorted(DIST.glob("*.zip")):
        print(f"zip:     {z}")


if __name__ == "__main__":
    build()
