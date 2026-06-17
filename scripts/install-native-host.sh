#!/usr/bin/env bash
# Install the native messaging host manifest for Firefox-based browsers.
# Supports native and Flatpak installs of Firefox, Zen, LibreWolf, Waterfox, Floorp.
#
# All Firefox forks read manifests from ~/.mozilla/native-messaging-hosts/
# (hardcoded in libxul). Some forks also check their own config dir.
# For Flatpak browsers, a user override is applied so the sandbox can see
# the manifest and the wrapper can re-exec on the host.
#
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

# Primary dir (all Firefox-based browsers check this).
BROWSER_DIRS=("$HOME/.mozilla/native-messaging-hosts")

# Fork-specific dirs (forks that patched libxul to also check their own).
FORK_CONFIGS=(.librewolf .waterfox .floorp)
for cfg in "${FORK_CONFIGS[@]}"; do
    if [ -d "$HOME/$cfg" ]; then
        BROWSER_DIRS+=("$HOME/$cfg/native-messaging-hosts")
    fi
done

# Self-detecting wrapper: uses flatpak-spawn when called from inside a sandbox.
make_wrapper() {
    cat << WRAPPER_EOF
#!/usr/bin/env bash
target=("$PYTHON" "-c" "from cove.native_messaging import main; main()")
if [ -e /.flatpak-info ] && command -v flatpak-spawn >/dev/null 2>&1; then
    exec flatpak-spawn --host "\${target[@]}"
fi
exec "\${target[@]}"
WRAPPER_EOF
}

installed=0
for MANIFEST_DIR in "${BROWSER_DIRS[@]}"; do
    PARENT_DIR="$(dirname "$MANIFEST_DIR")"
    if [ ! -d "$PARENT_DIR" ]; then
        continue
    fi

    mkdir -p "$MANIFEST_DIR"

    WRAPPER="$MANIFEST_DIR/$HOST_NAME"
    make_wrapper > "$WRAPPER"
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
    exit 1
fi

# Apply Flatpak overrides so sandboxed browsers can read the manifest
# and the wrapper can re-exec on the host.
KNOWN_FLATPAK_IDS=(
    org.mozilla.firefox
    app.zen_browser.zen
    io.github.nicoth.zen
    io.gitlab.librewolf-community
    net.waterfox.waterfox
)

if [ -d "$HOME/.var/app" ] && command -v flatpak >/dev/null 2>&1; then
    PRIMARY_DIR="${BROWSER_DIRS[0]}"
    for app_id in "${KNOWN_FLATPAK_IDS[@]}"; do
        if [ -d "$HOME/.var/app/$app_id" ]; then
            flatpak override --user \
                --talk-name=org.freedesktop.Flatpak \
                "--filesystem=$PRIMARY_DIR:ro" \
                "$app_id" 2>/dev/null && \
                echo "Flatpak override applied: $app_id" || true
        fi
    done
fi

echo "Done. Extension ID: $EXT_ID"
