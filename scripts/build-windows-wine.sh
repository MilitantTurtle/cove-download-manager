#!/usr/bin/env bash
# Cross-build Setup.exe + Portable.exe from Linux via Wine.
#
# Output:
#   release/Cove-Download-Manager-<version>-Setup.exe
#   release/Cove-Download-Manager-<version>-Portable.exe
#
# Prereqs:
#   - wine in $PATH
#   - a wine prefix at $HOME/.wine-covebuild with Python 3.12 + PySide6 +
#     requests + PyInstaller (shared with the rest of the cove tooling).
#     A fresh box can prep one with:
#       export WINEPREFIX=$HOME/.wine-covebuild WINEARCH=win64
#       wineboot -i
#       # download python-3.12.x-amd64.exe and run with:
#       wine python-3.12.x-amd64.exe /quiet PrependPath=1 \
#            InstallAllUsers=0 Include_test=0
#       wine python -m pip install pyside6 requests pyinstaller
#   - Inno Setup 6 — installed automatically into the same prefix on first run.
#
# Aria2 is bundled (Windows has no system aria2). The script downloads
# aria2-1.37.0 from GitHub releases.
#
# Env vars:
#   VERSION=X.Y.Z   override the version (defaults to cove/__init__.py)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP="cove-download-manager"
DISPLAY_NAME="Cove Download Manager"
VERSION="${VERSION:-$(grep -E '^__version__' cove/__init__.py | cut -d'"' -f2)}"
RELEASE_DIR="$ROOT/release"
mkdir -p "$RELEASE_DIR"

export WINEPREFIX="${WINEPREFIX:-$HOME/.wine-covebuild}"
export WINEARCH="${WINEARCH:-win64}"
export WINEDEBUG="${WINEDEBUG:--all}"

WIN_PY="${WIN_PY:-C:\\users\\$USER\\AppData\\Local\\Programs\\Python\\Python312\\python.exe}"
PY_UNIX="$WINEPREFIX/drive_c/users/$USER/AppData/Local/Programs/Python/Python312/python.exe"
[ -x "$PY_UNIX" ] || { echo "Wine Python not found at $PY_UNIX"; echo "See the prereqs comment at the top of this script."; exit 1; }

# Make sure the wine Python has the runtime deps cove imports (PySide6,
# requests). pip is idempotent — already-installed packages are no-ops.
echo "==> Ensuring wine Python has cove's runtime deps"
wine "$WIN_PY" -m pip install --quiet --upgrade -r requirements.txt
wine "$WIN_PY" -m pip install --quiet pyinstaller pillow

# ---------------------------------------------------------------- 1. aria2c.exe
ARIA_DIR="$ROOT/build/aria2-win"
ARIA_VERSION="1.37.0"
if [ ! -f "$ARIA_DIR/aria2c.exe" ]; then
    echo "==> Downloading aria2 ${ARIA_VERSION} (Windows x64)"
    rm -rf "$ARIA_DIR"
    mkdir -p "$ARIA_DIR"
    TMP=$(mktemp -d)
    curl -fL --retry 3 --silent --show-error \
        -o "$TMP/aria2.zip" \
        "https://github.com/aria2/aria2/releases/download/release-${ARIA_VERSION}/aria2-${ARIA_VERSION}-win-64bit-build1.zip"
    (cd "$TMP" && unzip -q aria2.zip)
    SRC=$(find "$TMP" -maxdepth 2 -type d -name 'aria2-*' | head -1)
    [ -n "$SRC" ] || { echo "aria2 extract failed"; exit 1; }
    cp -r "$SRC"/. "$ARIA_DIR/"
    rm -rf "$TMP"
fi
ARIA_EXE="$ARIA_DIR/aria2c.exe"
[ -f "$ARIA_EXE" ] || { echo "aria2c.exe missing after extract"; exit 1; }

# ---------------------------------------------------------------- 2. Icon (.ico)
echo "==> Generating cove_icon.ico"
wine "$WIN_PY" -c "
from PIL import Image
Image.open(r'cove_icon.png').save(
    r'cove_icon.ico',
    sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)],
)" >/dev/null

# ---------------------------------------------------------------- 3. Clean
rm -rf "$ROOT/build/win-onedir" "$ROOT/build/win-onefile" "$ROOT/dist"

ASSET_DATA="cove_icon.png;cove"

COMMON_ARGS=(
    --noconfirm --clean --log-level WARN
    --windowed
    --icon cove_icon.ico
    --paths .
    --add-data "$ASSET_DATA"
    --add-binary "${ARIA_EXE};."
    --hidden-import cove
    --hidden-import cove.app
    --hidden-import cove.api_server
    --hidden-import requests
    --collect-submodules requests
    --exclude-module PySide6.QtWebEngineCore
    --exclude-module PySide6.QtWebEngineWidgets
    --exclude-module PySide6.QtQml
    --exclude-module PySide6.QtQuick
    --exclude-module PySide6.QtPdf
    --exclude-module PySide6.Qt3DCore
    --exclude-module PySide6.QtCharts
    --exclude-module PySide6.QtDataVisualization
    --exclude-module PySide6.QtMultimedia
    --exclude-module PySide6.QtMultimediaWidgets
    --exclude-module tkinter
    packaging/launcher.py
)

# ---------------------------------------------------------------- 4. one-dir
echo "==> PyInstaller (one-dir for installer)"
wine "$WIN_PY" -m PyInstaller \
    --name "$APP" \
    --distpath "$ROOT/build/win-onedir/dist" \
    --workpath "$ROOT/build/win-onedir/work" \
    "${COMMON_ARGS[@]}"

ONEDIR="$ROOT/build/win-onedir/dist/$APP"
[ -d "$ONEDIR" ] || { echo "onedir output missing: $ONEDIR"; exit 1; }
cp -f cove_icon.png "$ONEDIR/"
[ -f README.md ] && cp -f README.md "$ONEDIR/"
[ -f LICENSE ]   && cp -f LICENSE   "$ONEDIR/"

# ---------------------------------------------------------------- 5. one-file
echo "==> PyInstaller (one-file portable)"
wine "$WIN_PY" -m PyInstaller \
    --name "$APP-portable" \
    --onefile \
    --distpath "$ROOT/build/win-onefile/dist" \
    --workpath "$ROOT/build/win-onefile/work" \
    "${COMMON_ARGS[@]}"

PORT_SRC="$ROOT/build/win-onefile/dist/$APP-portable.exe"
[ -f "$PORT_SRC" ] || { echo "portable output missing: $PORT_SRC"; exit 1; }

# ---------------------------------------------------------------- 6. Inno Setup
ISCC_UNIX="$WINEPREFIX/drive_c/Program Files (x86)/Inno Setup 6/ISCC.exe"
if [ ! -x "$ISCC_UNIX" ]; then
    echo "==> Installing Inno Setup 6 under wine"
    IS_TMP="$ROOT/build/innosetup.exe"
    curl -fL --retry 3 --silent --show-error \
        -o "$IS_TMP" "https://github.com/jrsoftware/issrc/releases/download/is-6_7_1/innosetup-6.7.1.exe"
    wine "$IS_TMP" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- 2>&1 | tail -3 || true
    rm -f "$IS_TMP"
fi
[ -x "$ISCC_UNIX" ] || { echo "ISCC.exe missing at $ISCC_UNIX"; exit 1; }

echo "==> Building Setup.exe with Inno Setup"
SRC_WIN=$(winepath -w "$ONEDIR")
OUT_WIN=$(winepath -w "$RELEASE_DIR")
ICON_WIN=$(winepath -w "$ROOT/cove_icon.ico")

wine "$ISCC_UNIX" \
    "/DAppVersion=$VERSION" \
    "/DSourceDir=$SRC_WIN" \
    "/DOutputDir=$OUT_WIN" \
    "/DIconFile=$ICON_WIN" \
    packaging/installer.iss

# ---------------------------------------------------------------- 7. Stage portable
PORT_DEST="$RELEASE_DIR/${DISPLAY_NAME// /-}-${VERSION}-Portable.exe"
rm -f "$PORT_DEST"
cp -f "$PORT_SRC" "$PORT_DEST"

# SHA-256 sidecars for both Windows artifacts.
SETUP_DEST="$RELEASE_DIR/${DISPLAY_NAME// /-}-${VERSION}-Setup.exe"
for f in "$SETUP_DEST" "$PORT_DEST"; do
    [ -f "$f" ] && (cd "$(dirname "$f")" && sha256sum "$(basename "$f")" > "$(basename "$f").sha256")
done

echo
echo "Done:"
ls -lh "$RELEASE_DIR"/*.exe "$RELEASE_DIR"/*.exe.sha256 2>/dev/null || true
