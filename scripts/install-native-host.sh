#!/usr/bin/env bash
# Install the native messaging host manifest for Firefox-based browsers.
# Supports native and Flatpak installs of Firefox, Zen, LibreWolf, Waterfox, Floorp.
# Usage: ./scripts/install-native-host.sh [extension-id]

set -euo pipefail

EXT_ID="${1:-cove-dm@cove-download-manager.net}"
HOST_NAME="cove_download_manager"

# Find the Python that has cove installed.
PYTHON="$(command -v python3 || command -v python)"
if [ -z "$PYTHON" ]; then
    echo "Error: python3 not found" >&2
    exit 1
fi

# Verify cove is importable.
if ! "$PYTHON" -c "import cove.native_messaging" 2>/dev/null; then
    echo "Error: cove.native_messaging not importable by $PYTHON" >&2
    echo "Install cove first: pip install -e ." >&2
    exit 1
fi

BROWSER_CONFIGS=(.mozilla .zen .librewolf .waterfox .floorp)

BROWSER_DIRS=()
for cfg in "${BROWSER_CONFIGS[@]}"; do
    BROWSER_DIRS+=("$HOME/$cfg/native-messaging-hosts")
done

# Flatpak browsers sandbox the home directory, so their config lives
# under ~/.var/app/<app-id>/<config>/. Scan for any installed Flatpak
# browser that has a known config dir.
if [ -d "$HOME/.var/app" ]; then
    for app_dir in "$HOME/.var/app"/*/; do
        [ -d "$app_dir" ] || continue
        for cfg in "${BROWSER_CONFIGS[@]}"; do
            if [ -d "${app_dir}${cfg}" ]; then
                BROWSER_DIRS+=("${app_dir}${cfg}/native-messaging-hosts")
            fi
        done
    done
fi

installed=0
for MANIFEST_DIR in "${BROWSER_DIRS[@]}"; do
    PARENT_DIR="$(dirname "$MANIFEST_DIR")"
    if [ ! -d "$PARENT_DIR" ]; then
        continue
    fi

    mkdir -p "$MANIFEST_DIR"

    WRAPPER="$MANIFEST_DIR/$HOST_NAME"
    cat > "$WRAPPER" << WRAPPER_EOF
#!/usr/bin/env bash
exec $PYTHON -c "from cove.native_messaging import main; main()"
WRAPPER_EOF
    chmod +x "$WRAPPER"

    cat > "$MANIFEST_DIR/$HOST_NAME.json" << EOF
{
  "name": "$HOST_NAME",
  "description": "Cove Download Manager native messaging host",
  "path": "$WRAPPER",
  "type": "stdio",
  "allowed_extensions": ["$EXT_ID"]
}
EOF

    echo "Installed: $MANIFEST_DIR"
    installed=$((installed + 1))
done

if [ "$installed" -eq 0 ]; then
    echo "No supported browser profile directories found." >&2
    echo "Checked: ${BROWSER_DIRS[*]}" >&2
    exit 1
fi

echo "Done. Extension ID: $EXT_ID"
