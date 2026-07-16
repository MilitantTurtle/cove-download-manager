# Firefox Extension for Cove Download Manager - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Firefox WebExtension that intercepts browser downloads and sends them to Cove via native messaging, plus the Cove-side native messaging host to receive them.

**Architecture:** MV2 WebExtension communicates with a Python native messaging host (`cove/native_messaging.py`) over stdin/stdout. The host reads Cove's `settings.json` to get the aria2 RPC secret/port, then calls `Aria2RPC.add_uri()` to queue downloads. The extension uses `downloads.onCreated` + `downloads.onChanged` for interception, context menus for explicit "Download with Cove", and a popup for status. `Aria2RPC.add_uri()` is extended to support custom headers (Cookie, Referer) for authenticated downloads.

**Tech Stack:** JavaScript (WebExtension APIs, MV2), Python 3.9+ (native messaging host), aria2 JSON-RPC

---

## File Map

### Cove-side (Python)

| File | Responsibility |
|------|---------------|
| `cove/native_messaging.py` (create) | Native messaging host - reads stdin messages, dispatches to aria2 RPC, writes stdout responses |
| `cove/aria2.py` (modify lines 214-232) | Extend `add_uri()` with optional `headers` parameter |
| `scripts/install-native-host.sh` (create) | Register native messaging host manifest with Firefox on Linux |

### Extension-side (JavaScript)

| File | Responsibility |
|------|---------------|
| `extension/manifest.json` (create) | MV2 manifest with permissions, background script, popup, options |
| `extension/background.js` (create) | Download interception, context menus, native messaging client, badge updates |
| `extension/popup/popup.html` (create) | Toolbar popup markup |
| `extension/popup/popup.css` (create) | Popup styles matching Cove's dark theme |
| `extension/popup/popup.js` (create) | Popup logic - fetch status from native host, render download list |
| `extension/options/options.html` (create) | Options page markup |
| `extension/options/options.css` (create) | Options page styles |
| `extension/options/options.js` (create) | Options logic - file type filters, size threshold, domain lists |
| `extension/icons/` (create) | Extension icons (16, 32, 48, 96, 128px) |

### Tests

| File | Responsibility |
|------|---------------|
| `tests/test_native_messaging.py` (create) | Unit tests for message read/write, download handling, URL validation |
| `tests/test_aria2_headers.py` (create) | Unit test for add_uri headers parameter |

---

## Task 1: Extend `Aria2RPC.add_uri()` with headers support

**Files:**
- Modify: `cove/aria2.py:214-232`
- Create: `tests/test_aria2_headers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_aria2_headers.py
"""Test that Aria2RPC.add_uri() forwards custom headers to aria2."""
import json
from unittest.mock import MagicMock, patch

from cove.aria2 import Aria2RPC
from cove.config import Settings


def _make_rpc() -> Aria2RPC:
    s = Settings()
    s.rpc_port = 16800
    s.rpc_secret = "test-secret"
    return Aria2RPC(s)


def test_add_uri_without_headers():
    """Baseline: no headers param sends opts without 'header' key."""
    rpc = _make_rpc()
    with patch.object(rpc, "_call", return_value="gid-abc") as mock:
        gid = rpc.add_uri(["https://example.com/f.zip"], "/tmp", 4)
        assert gid == "gid-abc"
        args = mock.call_args[0]
        opts = args[1][1]
        assert "header" not in opts


def test_add_uri_with_headers():
    """Headers list is forwarded as aria2's 'header' option."""
    rpc = _make_rpc()
    with patch.object(rpc, "_call", return_value="gid-def") as mock:
        headers = ["Cookie: session=abc123", "Referer: https://example.com/page"]
        gid = rpc.add_uri(
            ["https://example.com/f.zip"], "/tmp", 4, headers=headers
        )
        assert gid == "gid-def"
        args = mock.call_args[0]
        opts = args[1][1]
        assert opts["header"] == headers


def test_add_uri_with_empty_headers():
    """Empty headers list is not forwarded."""
    rpc = _make_rpc()
    with patch.object(rpc, "_call", return_value="gid-ghi") as mock:
        gid = rpc.add_uri(
            ["https://example.com/f.zip"], "/tmp", 4, headers=[]
        )
        args = mock.call_args[0]
        opts = args[1][1]
        assert "header" not in opts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_aria2_headers.py -v`
Expected: `test_add_uri_with_headers` FAILS with `TypeError: add_uri() got an unexpected keyword argument 'headers'`

- [ ] **Step 3: Implement - extend add_uri with headers parameter**

In `cove/aria2.py`, modify the `add_uri` method:

```python
    def add_uri(
        self,
        uris: list[str],
        out_dir: str,
        connections: int,
        speed_limit_kbps: int = 0,
        filename: str | None = None,
        headers: list[str] | None = None,
    ) -> str:
        opts: dict[str, str] = {
            "dir": out_dir,
            "split": str(connections),
            "max-connection-per-server": str(connections),
            "continue": "true",
        }
        if speed_limit_kbps > 0:
            opts["max-download-limit"] = f"{speed_limit_kbps}K"
        if filename:
            opts["out"] = filename
        if headers:
            opts["header"] = headers
        return self._call("aria2.addUri", [uris, opts])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_aria2_headers.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add cove/aria2.py tests/test_aria2_headers.py
git commit -m "feat: add headers support to Aria2RPC.add_uri()"
```

---

## Task 2: Create the native messaging host

**Files:**
- Create: `cove/native_messaging.py`
- Create: `tests/test_native_messaging.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_native_messaging.py
"""Tests for the native messaging host protocol and download handling."""
import io
import json
import struct
from unittest.mock import MagicMock, patch

from cove.native_messaging import (
    encode_message,
    decode_message,
    validate_url,
    handle_message,
)


def test_encode_message():
    msg = {"status": "ok"}
    encoded = encode_message(msg)
    length = struct.unpack("@I", encoded[:4])[0]
    body = json.loads(encoded[4:])
    assert length == len(encoded) - 4
    assert body == {"status": "ok"}


def test_decode_message():
    msg = {"action": "ping"}
    body = json.dumps(msg).encode("utf-8")
    data = struct.pack("@I", len(body)) + body
    result = decode_message(io.BytesIO(data))
    assert result == {"action": "ping"}


def test_decode_message_eof():
    result = decode_message(io.BytesIO(b""))
    assert result is None


def test_decode_message_too_large():
    data = struct.pack("@I", 2 * 1024 * 1024) + b"\x00"
    result = decode_message(io.BytesIO(data))
    assert result is None


def test_validate_url_http():
    assert validate_url("https://example.com/file.zip") is True
    assert validate_url("http://example.com/file.zip") is True


def test_validate_url_ftp():
    assert validate_url("ftp://example.com/file.zip") is True


def test_validate_url_blocked_schemes():
    assert validate_url("file:///etc/passwd") is False
    assert validate_url("javascript:alert(1)") is False
    assert validate_url("data:text/html,<h1>hi</h1>") is False


def test_validate_url_garbage():
    assert validate_url("") is False
    assert validate_url("not a url") is False


def test_handle_ping():
    result = handle_message({"action": "ping"}, rpc=None, settings=None)
    assert result["status"] == "ok"
    assert "version" in result


def test_handle_download():
    mock_rpc = MagicMock()
    mock_rpc.add_uri.return_value = "gid-123"
    mock_settings = MagicMock()
    mock_settings.download_dir = "/tmp/downloads"
    mock_settings.connections_per_server = 16

    msg = {
        "action": "download",
        "url": "https://example.com/file.zip",
        "filename": "file.zip",
        "referrer": "https://example.com/page",
        "cookies": "session=abc",
    }
    result = handle_message(msg, rpc=mock_rpc, settings=mock_settings)
    assert result["status"] == "ok"
    assert result["gid"] == "gid-123"

    call_args = mock_rpc.add_uri.call_args
    assert call_args[0][0] == ["https://example.com/file.zip"]
    headers = call_args[1]["headers"]
    assert "Cookie: session=abc" in headers
    assert "Referer: https://example.com/page" in headers


def test_handle_download_invalid_url():
    result = handle_message(
        {"action": "download", "url": "file:///etc/passwd"},
        rpc=MagicMock(),
        settings=MagicMock(),
    )
    assert result["status"] == "error"


def test_handle_download_missing_url():
    result = handle_message(
        {"action": "download"},
        rpc=MagicMock(),
        settings=MagicMock(),
    )
    assert result["status"] == "error"


def test_handle_unknown_action():
    result = handle_message({"action": "unknown"}, rpc=None, settings=None)
    assert result["status"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_native_messaging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cove.native_messaging'`

- [ ] **Step 3: Implement the native messaging host**

```python
# cove/native_messaging.py
"""Native messaging host for Firefox extension integration.

Communicates via stdin/stdout using the WebExtension native messaging
protocol (4-byte little-endian length prefix + JSON body). Reads Cove's
settings to connect to aria2 RPC and queue downloads.

Usage:
    python -m cove.native_messaging
"""
from __future__ import annotations

import io
import json
import struct
import sys
from typing import Any

from . import __version__
from .aria2 import Aria2RPC, Aria2Error
from .config import Settings

MAX_MESSAGE_SIZE = 1024 * 1024  # 1 MB


def decode_message(stream: io.BufferedIOBase) -> dict | None:
    raw_length = stream.read(4)
    if not raw_length or len(raw_length) < 4:
        return None
    length = struct.unpack("@I", raw_length)[0]
    if length > MAX_MESSAGE_SIZE:
        return None
    data = stream.read(length)
    if len(data) < length:
        return None
    return json.loads(data)


def encode_message(msg: dict) -> bytes:
    body = json.dumps(msg).encode("utf-8")
    return struct.pack("@I", len(body)) + body


def validate_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    lower = url.lower().strip()
    if lower.startswith(("http://", "https://", "ftp://")):
        return True
    return False


def handle_message(
    msg: dict,
    rpc: Aria2RPC | None,
    settings: Settings | None,
) -> dict:
    action = msg.get("action", "")

    if action == "ping":
        return {"status": "ok", "version": __version__}

    if action == "download":
        url = msg.get("url", "")
        if not validate_url(url):
            return {"status": "error", "message": f"Invalid or blocked URL: {url!r}"}
        if rpc is None or settings is None:
            return {"status": "error", "message": "Cove is not configured"}

        headers: list[str] = []
        cookies = msg.get("cookies", "")
        if cookies:
            headers.append(f"Cookie: {cookies}")
        referrer = msg.get("referrer", "")
        if referrer:
            headers.append(f"Referer: {referrer}")
        user_agent = msg.get("userAgent", "")
        if user_agent:
            headers.append(f"User-Agent: {user_agent}")

        out_dir = msg.get("directory") or settings.download_dir
        filename = msg.get("filename") or None

        try:
            gid = rpc.add_uri(
                [url],
                out_dir,
                settings.connections_per_server,
                headers=headers if headers else None,
                filename=filename,
            )
            return {"status": "ok", "gid": gid, "message": "Download added to Cove"}
        except Aria2Error as e:
            return {"status": "error", "message": str(e)}

    if action == "status":
        if rpc is None:
            return {"status": "error", "message": "Cove is not configured"}
        try:
            active = rpc.tell_active()
            return {"status": "ok", "downloads": active}
        except Aria2Error as e:
            return {"status": "error", "message": str(e)}

    return {"status": "error", "message": f"Unknown action: {action!r}"}


def main() -> None:
    settings = Settings.load()
    rpc = Aria2RPC(settings)
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    while True:
        msg = decode_message(stdin)
        if msg is None:
            break
        response = handle_message(msg, rpc, settings)
        stdout.write(encode_message(response))
        stdout.flush()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add `__main__.py` support for `python -m cove.native_messaging`**

Create `cove/native_messaging/__init__.py` - wait, simpler: the file is already `cove/native_messaging.py` as a module. To run via `python -m cove.native_messaging`, we need it as a package. Instead, keep it as a single file and the `if __name__` block handles direct execution. For `python -m` invocation, add to the script registration later. The native host manifest will point to a wrapper script.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_native_messaging.py -v`
Expected: All 12 tests PASS

- [ ] **Step 6: Commit**

```bash
git add cove/native_messaging.py tests/test_native_messaging.py
git commit -m "feat: add native messaging host for Firefox extension"
```

---

## Task 3: Create the native host registration script

**Files:**
- Create: `scripts/install-native-host.sh`

- [ ] **Step 1: Write the install script**

```bash
#!/usr/bin/env bash
# Install the native messaging host manifest for Firefox.
# Usage: ./scripts/install-native-host.sh [extension-id]

set -euo pipefail

EXT_ID="${1:-cove-dm@cove-download-manager.net}"
HOST_NAME="cove_download_manager"
MANIFEST_DIR="$HOME/.mozilla/native-messaging-hosts"

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

mkdir -p "$MANIFEST_DIR"

# Write a wrapper script that invokes the native messaging host.
WRAPPER="$MANIFEST_DIR/$HOST_NAME"
cat > "$WRAPPER" << WRAPPER_EOF
#!/usr/bin/env bash
exec $PYTHON -c "from cove.native_messaging import main; main()"
WRAPPER_EOF
chmod +x "$WRAPPER"

# Write the native messaging host manifest.
cat > "$MANIFEST_DIR/$HOST_NAME.json" << EOF
{
  "name": "$HOST_NAME",
  "description": "Cove Download Manager native messaging host",
  "path": "$WRAPPER",
  "type": "stdio",
  "allowed_extensions": ["$EXT_ID"]
}
EOF

echo "Installed native messaging host:"
echo "  Manifest: $MANIFEST_DIR/$HOST_NAME.json"
echo "  Wrapper:  $WRAPPER"
echo "  Extension ID: $EXT_ID"
```

- [ ] **Step 2: Make it executable and verify syntax**

Run: `chmod +x scripts/install-native-host.sh && bash -n scripts/install-native-host.sh`
Expected: No output (syntax OK)

- [ ] **Step 3: Commit**

```bash
git add scripts/install-native-host.sh
git commit -m "feat: add native messaging host install script for Firefox"
```

---

## Task 4: Create extension manifest and icons

**Files:**
- Create: `extension/manifest.json`
- Create: `extension/icons/` (generate from `cove_icon.png`)

- [ ] **Step 1: Create the extension directory structure**

Run:
```bash
mkdir -p extension/icons extension/popup extension/options
```

- [ ] **Step 2: Generate extension icons from cove_icon.png**

Run:
```bash
for size in 16 32 48 96 128; do
  convert cove_icon.png -resize ${size}x${size} extension/icons/icon-${size}.png
done
```

If `convert` (ImageMagick) is not available, use Python:
```bash
python3 -c "
from PIL import Image
img = Image.open('cove_icon.png')
for s in [16, 32, 48, 96, 128]:
    img.resize((s, s), Image.LANCZOS).save(f'extension/icons/icon-{s}.png')
"
```

- [ ] **Step 3: Write manifest.json**

```json
{
  "manifest_version": 2,
  "name": "Cove Download Manager",
  "version": "1.0.0",
  "description": "Intercept downloads and send them to Cove Download Manager.",
  "author": "Sin",

  "browser_specific_settings": {
    "gecko": {
      "id": "cove-dm@cove-download-manager.net",
      "strict_min_version": "91.0"
    }
  },

  "permissions": [
    "downloads",
    "cookies",
    "contextMenus",
    "nativeMessaging",
    "notifications",
    "storage",
    "<all_urls>"
  ],

  "background": {
    "scripts": ["background.js"],
    "persistent": true
  },

  "browser_action": {
    "default_popup": "popup/popup.html",
    "default_icon": {
      "16": "icons/icon-16.png",
      "32": "icons/icon-32.png",
      "48": "icons/icon-48.png"
    },
    "default_title": "Cove Download Manager"
  },

  "options_ui": {
    "page": "options/options.html",
    "browser_style": false
  },

  "icons": {
    "48": "icons/icon-48.png",
    "96": "icons/icon-96.png",
    "128": "icons/icon-128.png"
  },

  "commands": {
    "toggle-intercept": {
      "suggested_key": { "default": "Alt+Shift+D" },
      "description": "Toggle download interception on/off"
    }
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add extension/
git commit -m "feat: add Firefox extension manifest and icons"
```

---

## Task 5: Build the background script - native messaging client

**Files:**
- Create: `extension/background.js`

- [ ] **Step 1: Write the native messaging connection wrapper**

This is the core of the extension. It handles:
- Connecting to the native messaging host
- Sending/receiving messages
- Reconnecting on disconnect

```javascript
// extension/background.js

const HOST_NAME = "cove_download_manager";

let port = null;
let pendingCallbacks = new Map();
let callId = 0;

function connect() {
  if (port) return;
  try {
    port = browser.runtime.connectNative(HOST_NAME);
    port.onMessage.addListener(onNativeMessage);
    port.onDisconnect.addListener(onDisconnect);
  } catch (e) {
    port = null;
  }
}

function onDisconnect() {
  port = null;
  for (const [id, cb] of pendingCallbacks) {
    cb({ status: "error", message: "Native host disconnected" });
  }
  pendingCallbacks.clear();
  updateBadge();
}

function onNativeMessage(msg) {
  if (msg._callId !== undefined && pendingCallbacks.has(msg._callId)) {
    pendingCallbacks.get(msg._callId)(msg);
    pendingCallbacks.delete(msg._callId);
  }
}

function sendNativeMessage(msg) {
  return new Promise((resolve) => {
    connect();
    if (!port) {
      resolve({ status: "error", message: "Cannot connect to Cove" });
      return;
    }
    // Native messaging host doesn't use _callId, so for simplicity
    // we use sendNativeMessage (one-shot) instead of port for request/response.
    browser.runtime.sendNativeMessage(HOST_NAME, msg).then(resolve, (err) => {
      resolve({ status: "error", message: err.message || String(err) });
    });
  });
}

// ---- Default settings ----

const DEFAULT_SETTINGS = {
  enabled: true,
  minSizeBytes: 1024 * 1024, // 1 MB
  interceptExtensions: [
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".msi", ".dmg", ".iso", ".img",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".mp3", ".flac", ".aac", ".ogg", ".wav",
    ".pdf", ".torrent",
    ".deb", ".rpm", ".appimage",
  ],
  excludedDomains: [],
};

let settings = { ...DEFAULT_SETTINGS };

async function loadSettings() {
  const stored = await browser.storage.local.get("settings");
  if (stored.settings) {
    settings = { ...DEFAULT_SETTINGS, ...stored.settings };
  }
}

async function saveSettings(newSettings) {
  settings = { ...DEFAULT_SETTINGS, ...newSettings };
  await browser.storage.local.set({ settings });
}

// ---- Download interception ----

function getExtension(url) {
  try {
    const pathname = new URL(url).pathname;
    const dot = pathname.lastIndexOf(".");
    if (dot === -1) return "";
    return pathname.substring(dot).toLowerCase().split(/[?#]/)[0];
  } catch {
    return "";
  }
}

function isDomainExcluded(url) {
  try {
    const hostname = new URL(url).hostname;
    return settings.excludedDomains.some(
      (d) => hostname === d || hostname.endsWith("." + d)
    );
  } catch {
    return false;
  }
}

function shouldIntercept(downloadItem) {
  if (!settings.enabled) return false;
  const url = downloadItem.url;
  if (!url || url.startsWith("blob:") || url.startsWith("data:")) return false;
  if (isDomainExcluded(url)) return false;

  const ext = getExtension(url);
  if (ext && settings.interceptExtensions.includes(ext)) return true;

  if (
    downloadItem.totalBytes &&
    downloadItem.totalBytes >= settings.minSizeBytes
  ) {
    return true;
  }

  return false;
}

// Track downloads we've seen but are waiting for metadata on.
const pendingDownloads = new Map();

browser.downloads.onCreated.addListener((downloadItem) => {
  if (!settings.enabled) return;
  if (downloadItem.url.startsWith("blob:") || downloadItem.url.startsWith("data:")) return;
  if (isDomainExcluded(downloadItem.url)) return;

  const ext = getExtension(downloadItem.url);
  if (ext && settings.interceptExtensions.includes(ext)) {
    interceptDownload(downloadItem);
    return;
  }

  // Can't decide yet - wait for onChanged to get fileSize/filename.
  pendingDownloads.set(downloadItem.id, downloadItem);
});

browser.downloads.onChanged.addListener((delta) => {
  if (!pendingDownloads.has(delta.id)) return;
  const item = pendingDownloads.get(delta.id);

  if (delta.totalBytes) {
    item.totalBytes = delta.totalBytes.current;
  }
  if (delta.filename) {
    item.filename = delta.filename.current;
  }

  // Check filename extension now that we have it.
  if (delta.filename) {
    const name = delta.filename.current || "";
    const dot = name.lastIndexOf(".");
    if (dot !== -1) {
      const ext = name.substring(dot).toLowerCase();
      if (settings.interceptExtensions.includes(ext)) {
        pendingDownloads.delete(delta.id);
        interceptDownload(item);
        return;
      }
    }
  }

  // Check size threshold.
  if (
    item.totalBytes &&
    item.totalBytes >= settings.minSizeBytes
  ) {
    pendingDownloads.delete(delta.id);
    interceptDownload(item);
    return;
  }

  // If download completed or errored without matching, stop tracking.
  if (delta.state && (delta.state.current === "complete" || delta.state.current === "interrupted")) {
    pendingDownloads.delete(delta.id);
  }
});

async function interceptDownload(downloadItem) {
  pendingDownloads.delete(downloadItem.id);

  // Cancel the browser download.
  try {
    await browser.downloads.cancel(downloadItem.id);
    await browser.downloads.erase({ id: downloadItem.id });
  } catch {
    // Already completed or cancelled.
  }

  // Gather cookies for the download URL.
  let cookieStr = "";
  try {
    const url = new URL(downloadItem.url);
    const cookies = await browser.cookies.getAll({ url: downloadItem.url });
    cookieStr = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch {
    // No cookies available.
  }

  // Extract filename from the download item.
  let filename = null;
  if (downloadItem.filename) {
    const parts = downloadItem.filename.replace(/\\/g, "/").split("/");
    filename = parts[parts.length - 1] || null;
  }

  const result = await sendNativeMessage({
    action: "download",
    url: downloadItem.url,
    filename: filename,
    referrer: downloadItem.referrer || "",
    cookies: cookieStr,
    fileSize: downloadItem.totalBytes || 0,
  });

  if (result.status === "ok") {
    showNotification("Download sent to Cove", filename || downloadItem.url);
    updateBadge();
  } else {
    showNotification("Cove error", result.message || "Failed to send download");
  }
}

// ---- Context menu ----

browser.contextMenus.create({
  id: "download-with-cove",
  title: "Download with Cove",
  contexts: ["link", "image", "video", "audio"],
});

browser.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "download-with-cove") return;

  const url = info.linkUrl || info.srcUrl;
  if (!url) return;

  let cookieStr = "";
  try {
    const cookies = await browser.cookies.getAll({ url });
    cookieStr = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch {
    // No cookies.
  }

  let filename = null;
  try {
    const pathname = new URL(url).pathname;
    const parts = pathname.split("/");
    const last = parts[parts.length - 1];
    if (last && last.includes(".")) filename = decodeURIComponent(last);
  } catch {
    // Invalid URL.
  }

  const result = await sendNativeMessage({
    action: "download",
    url: url,
    filename: filename,
    referrer: info.pageUrl || "",
    cookies: cookieStr,
  });

  if (result.status === "ok") {
    showNotification("Download sent to Cove", filename || url);
  } else {
    showNotification("Cove error", result.message || "Failed to send download");
  }
});

// ---- Keyboard shortcut ----

browser.commands.onCommand.addListener((command) => {
  if (command === "toggle-intercept") {
    settings.enabled = !settings.enabled;
    saveSettings(settings);
    updateBadge();
    showNotification(
      "Cove Interception",
      settings.enabled ? "Download interception enabled" : "Download interception disabled"
    );
  }
});

// ---- Badge ----

function updateBadge() {
  if (!settings.enabled) {
    browser.browserAction.setBadgeText({ text: "OFF" });
    browser.browserAction.setBadgeBackgroundColor({ color: "#6b6b80" });
  } else {
    browser.browserAction.setBadgeText({ text: "" });
  }
}

// ---- Notifications ----

function showNotification(title, message) {
  browser.notifications.create({
    type: "basic",
    iconUrl: "icons/icon-96.png",
    title: title,
    message: message,
  });
}

// ---- Message handler for popup/options ----

browser.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "getSettings") {
    sendResponse(settings);
    return;
  }
  if (msg.type === "saveSettings") {
    saveSettings(msg.settings).then(() => {
      updateBadge();
      sendResponse({ ok: true });
    });
    return true; // async
  }
  if (msg.type === "getStatus") {
    sendNativeMessage({ action: "status" }).then(sendResponse);
    return true; // async
  }
  if (msg.type === "ping") {
    sendNativeMessage({ action: "ping" }).then(sendResponse);
    return true;
  }
});

// ---- Init ----

loadSettings().then(updateBadge);
```

- [ ] **Step 2: Manually test in Firefox**

Run: `cd extension && web-ext run --verbose`

If `web-ext` is not installed: `npx web-ext run --verbose`

Verify:
1. Extension loads without errors in `about:debugging#/runtime/this-firefox`
2. Context menu "Download with Cove" appears on right-click of a link
3. Badge shows "OFF" when interception is disabled

- [ ] **Step 3: Commit**

```bash
git add extension/background.js
git commit -m "feat: add background script with download interception and context menu"
```

---

## Task 6: Build the popup UI

**Files:**
- Create: `extension/popup/popup.html`
- Create: `extension/popup/popup.css`
- Create: `extension/popup/popup.js`

- [ ] **Step 1: Write popup.html**

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <link rel="stylesheet" href="popup.css">
</head>
<body>
  <div class="header">
    <img src="../icons/icon-32.png" alt="" class="logo">
    <span class="title">Cove</span>
    <button id="toggle-btn" class="toggle-btn" title="Toggle interception">ON</button>
  </div>

  <div id="status-bar" class="status-bar">
    <span id="connection-status">Checking...</span>
  </div>

  <div id="downloads-list" class="downloads-list">
    <div class="empty-state">No active downloads</div>
  </div>

  <div class="footer">
    <button id="open-options" class="footer-btn">Settings</button>
  </div>

  <script src="popup.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write popup.css matching Cove's dark theme**

```css
/* Cove extension popup - dark theme matching the desktop app */

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  width: 340px;
  min-height: 200px;
  max-height: 500px;
  background-color: #0b0b10;
  color: #ececf1;
  font-family: "Segoe UI", "Cantarell", sans-serif;
  font-size: 13px;
}

.header {
  display: flex;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid #1a1a22;
  gap: 8px;
}

.logo {
  width: 22px;
  height: 22px;
}

.title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #ececf1;
}

.toggle-btn {
  background-color: rgba(80, 230, 207, 0.14);
  color: #50e6cf;
  border: 1px solid rgba(80, 230, 207, 0.35);
  border-radius: 12px;
  padding: 3px 12px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1.5px;
  cursor: pointer;
}

.toggle-btn[data-enabled="false"] {
  background-color: rgba(255, 255, 255, 0.04);
  color: #6b6b80;
  border-color: #1a1a22;
}

.status-bar {
  padding: 6px 14px;
  font-size: 11px;
  color: #6b6b80;
  border-bottom: 1px solid #1a1a22;
}

.status-bar.connected {
  color: #50e6cf;
}

.status-bar.error {
  color: #ff5f6d;
}

.downloads-list {
  max-height: 300px;
  overflow-y: auto;
}

.empty-state {
  padding: 30px 14px;
  text-align: center;
  color: #6b6b80;
  font-size: 12px;
}

.download-item {
  padding: 10px 14px;
  border-bottom: 1px solid #1a1a22;
}

.download-filename {
  font-size: 12px;
  color: #ececf1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 6px;
}

.download-progress {
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background-color: #181822;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background-color: #50e6cf;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.download-speed {
  font-size: 11px;
  color: #9a9aae;
  white-space: nowrap;
}

.download-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 11px;
  color: #6b6b80;
}

.footer {
  display: flex;
  padding: 8px 14px;
  border-top: 1px solid #1a1a22;
  justify-content: flex-end;
}

.footer-btn {
  background: transparent;
  color: #9a9aae;
  border: none;
  font-size: 12px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}

.footer-btn:hover {
  color: #50e6cf;
  background-color: #13131b;
}

/* Scrollbar */
.downloads-list::-webkit-scrollbar {
  width: 6px;
}
.downloads-list::-webkit-scrollbar-track {
  background: transparent;
}
.downloads-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
}
.downloads-list::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.12);
}
```

- [ ] **Step 3: Write popup.js**

```javascript
// extension/popup/popup.js

const toggleBtn = document.getElementById("toggle-btn");
const connectionStatus = document.getElementById("connection-status");
const statusBar = document.getElementById("status-bar");
const downloadsList = document.getElementById("downloads-list");

function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + units[i];
}

function formatSpeed(bytesPerSec) {
  return formatBytes(bytesPerSec) + "/s";
}

async function checkConnection() {
  const result = await browser.runtime.sendMessage({ type: "ping" });
  if (result && result.status === "ok") {
    connectionStatus.textContent = "Connected - Cove v" + result.version;
    statusBar.className = "status-bar connected";
  } else {
    connectionStatus.textContent = "Not connected to Cove";
    statusBar.className = "status-bar error";
  }
}

async function loadSettings() {
  const s = await browser.runtime.sendMessage({ type: "getSettings" });
  toggleBtn.textContent = s.enabled ? "ON" : "OFF";
  toggleBtn.dataset.enabled = s.enabled;
}

toggleBtn.addEventListener("click", async () => {
  const s = await browser.runtime.sendMessage({ type: "getSettings" });
  s.enabled = !s.enabled;
  await browser.runtime.sendMessage({ type: "saveSettings", settings: s });
  toggleBtn.textContent = s.enabled ? "ON" : "OFF";
  toggleBtn.dataset.enabled = s.enabled;
});

document.getElementById("open-options").addEventListener("click", () => {
  browser.runtime.openOptionsPage();
});

function renderDownloads(downloads) {
  if (!downloads || downloads.length === 0) {
    downloadsList.innerHTML = '<div class="empty-state">No active downloads</div>';
    return;
  }

  downloadsList.innerHTML = downloads
    .map((dl) => {
      const files = dl.files || [];
      const filename = files[0]?.path?.split("/").pop() || "Unknown";
      const total = parseInt(dl.totalLength || 0);
      const completed = parseInt(dl.completedLength || 0);
      const speed = parseInt(dl.downloadSpeed || 0);
      const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

      return `
        <div class="download-item">
          <div class="download-filename" title="${filename}">${filename}</div>
          <div class="download-progress">
            <div class="progress-bar">
              <div class="progress-fill" style="width: ${pct}%"></div>
            </div>
            <span class="download-speed">${formatSpeed(speed)}</span>
          </div>
          <div class="download-meta">
            <span>${pct}% - ${formatBytes(completed)} / ${formatBytes(total)}</span>
          </div>
        </div>
      `;
    })
    .join("");
}

async function refreshDownloads() {
  const result = await browser.runtime.sendMessage({ type: "getStatus" });
  if (result && result.status === "ok") {
    renderDownloads(result.downloads);
  }
}

// Init
checkConnection();
loadSettings();
refreshDownloads();

// Refresh downloads every 2 seconds while popup is open.
setInterval(refreshDownloads, 2000);
```

- [ ] **Step 4: Test the popup in Firefox**

Run: `cd extension && npx web-ext run`

Verify:
1. Click the Cove toolbar icon - popup opens
2. Shows "Connected" or "Not connected" status
3. ON/OFF toggle works and updates badge
4. Settings button opens options page

- [ ] **Step 5: Commit**

```bash
git add extension/popup/
git commit -m "feat: add extension popup with download status display"
```

---

## Task 7: Build the options page

**Files:**
- Create: `extension/options/options.html`
- Create: `extension/options/options.css`
- Create: `extension/options/options.js`

- [ ] **Step 1: Write options.html**

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <link rel="stylesheet" href="options.css">
</head>
<body>
  <div class="container">
    <h1>Cove Download Manager</h1>
    <p class="subtitle">Extension Settings</p>

    <section>
      <h2>Interception</h2>

      <div class="field">
        <label>
          <input type="checkbox" id="enabled" checked>
          Enable automatic download interception
        </label>
      </div>

      <div class="field">
        <label for="min-size">Minimum file size to intercept</label>
        <div class="input-row">
          <input type="number" id="min-size" min="0" value="1">
          <select id="min-size-unit">
            <option value="1048576" selected>MB</option>
            <option value="1024">KB</option>
            <option value="1073741824">GB</option>
          </select>
        </div>
        <p class="hint">Files smaller than this will be handled by Firefox. Set to 0 to intercept all sizes.</p>
      </div>
    </section>

    <section>
      <h2>File Types</h2>
      <div class="field">
        <label for="extensions">File extensions to intercept (comma-separated)</label>
        <textarea id="extensions" rows="3" spellcheck="false"></textarea>
        <p class="hint">Example: .zip, .exe, .mp4, .iso</p>
        <button id="reset-extensions" class="btn-secondary">Reset to defaults</button>
      </div>
    </section>

    <section>
      <h2>Excluded Domains</h2>
      <div class="field">
        <label for="excluded-domains">Domains where interception is disabled (one per line)</label>
        <textarea id="excluded-domains" rows="3" spellcheck="false"
          placeholder="drive.google.com&#10;dropbox.com"></textarea>
        <p class="hint">Downloads from these domains will always be handled by Firefox.</p>
      </div>
    </section>

    <section>
      <h2>Connection</h2>
      <div class="field" id="connection-test">
        <button id="test-connection" class="btn-accent">Test Connection to Cove</button>
        <span id="test-result"></span>
      </div>
    </section>

    <div class="actions">
      <span id="save-status"></span>
      <button id="save" class="btn-accent">Save</button>
    </div>
  </div>

  <script src="options.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write options.css**

```css
/* Cove extension options - matches desktop theme */

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background-color: #0b0b10;
  color: #ececf1;
  font-family: "Segoe UI", "Cantarell", sans-serif;
  font-size: 14px;
  padding: 40px;
}

.container {
  max-width: 600px;
  margin: 0 auto;
}

h1 {
  font-size: 22px;
  font-weight: 600;
  color: #ececf1;
  margin-bottom: 4px;
}

.subtitle {
  color: #9a9aae;
  font-size: 13px;
  margin-bottom: 32px;
}

h2 {
  font-size: 11px;
  font-weight: 500;
  color: #6b6b80;
  letter-spacing: 2px;
  text-transform: uppercase;
  margin-bottom: 14px;
}

section {
  background-color: #13131b;
  border: 1px solid #1a1a22;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
}

.field {
  margin-bottom: 16px;
}

.field:last-child {
  margin-bottom: 0;
}

label {
  display: block;
  font-size: 13px;
  color: #ececf1;
  margin-bottom: 6px;
}

input[type="checkbox"] {
  margin-right: 8px;
  accent-color: #50e6cf;
}

input[type="number"],
select,
textarea {
  background-color: #181822;
  color: #ececf1;
  border: 1px solid #1a1a22;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  font-family: monospace;
  width: 100%;
}

input[type="number"] {
  width: 80px;
}

select {
  width: auto;
}

textarea {
  resize: vertical;
}

input:focus,
select:focus,
textarea:focus {
  outline: none;
  border-color: #50e6cf;
  background-color: #1f1f2b;
}

.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.hint {
  font-size: 11px;
  color: #6b6b80;
  margin-top: 4px;
}

.btn-accent {
  background-color: #50e6cf;
  color: #07120f;
  border: none;
  border-radius: 8px;
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn-accent:hover {
  background-color: #6cebd6;
}

.btn-secondary {
  background-color: #181822;
  color: #9a9aae;
  border: 1px solid #1a1a22;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 12px;
  cursor: pointer;
  margin-top: 8px;
}

.btn-secondary:hover {
  background-color: #1f1f2b;
  color: #ececf1;
  border-color: #23232d;
}

.actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  margin-top: 20px;
}

#save-status {
  font-size: 12px;
  color: #50e6cf;
}

#test-result {
  font-size: 12px;
  margin-left: 12px;
}

#test-result.ok {
  color: #50e6cf;
}

#test-result.error {
  color: #ff5f6d;
}

#connection-test {
  display: flex;
  align-items: center;
}
```

- [ ] **Step 3: Write options.js**

```javascript
// extension/options/options.js

const DEFAULT_EXTENSIONS = [
  ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
  ".exe", ".msi", ".dmg", ".iso", ".img",
  ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
  ".mp3", ".flac", ".aac", ".ogg", ".wav",
  ".pdf", ".torrent",
  ".deb", ".rpm", ".appimage",
];

const enabledCheckbox = document.getElementById("enabled");
const minSizeInput = document.getElementById("min-size");
const minSizeUnit = document.getElementById("min-size-unit");
const extensionsTextarea = document.getElementById("extensions");
const excludedDomainsTextarea = document.getElementById("excluded-domains");
const saveBtn = document.getElementById("save");
const saveStatus = document.getElementById("save-status");
const resetExtensionsBtn = document.getElementById("reset-extensions");
const testConnectionBtn = document.getElementById("test-connection");
const testResult = document.getElementById("test-result");

async function loadSettings() {
  const s = await browser.runtime.sendMessage({ type: "getSettings" });

  enabledCheckbox.checked = s.enabled;
  extensionsTextarea.value = (s.interceptExtensions || []).join(", ");
  excludedDomainsTextarea.value = (s.excludedDomains || []).join("\n");

  // Convert bytes to the best unit.
  const bytes = s.minSizeBytes || 0;
  if (bytes >= 1073741824 && bytes % 1073741824 === 0) {
    minSizeInput.value = bytes / 1073741824;
    minSizeUnit.value = "1073741824";
  } else if (bytes >= 1048576 && bytes % 1048576 === 0) {
    minSizeInput.value = bytes / 1048576;
    minSizeUnit.value = "1048576";
  } else {
    minSizeInput.value = Math.round(bytes / 1024);
    minSizeUnit.value = "1024";
  }
}

saveBtn.addEventListener("click", async () => {
  const newSettings = {
    enabled: enabledCheckbox.checked,
    minSizeBytes: parseInt(minSizeInput.value) * parseInt(minSizeUnit.value),
    interceptExtensions: extensionsTextarea.value
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter((s) => s.startsWith(".")),
    excludedDomains: excludedDomainsTextarea.value
      .split("\n")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean),
  };

  await browser.runtime.sendMessage({ type: "saveSettings", settings: newSettings });
  saveStatus.textContent = "Saved";
  setTimeout(() => { saveStatus.textContent = ""; }, 2000);
});

resetExtensionsBtn.addEventListener("click", () => {
  extensionsTextarea.value = DEFAULT_EXTENSIONS.join(", ");
});

testConnectionBtn.addEventListener("click", async () => {
  testResult.textContent = "Testing...";
  testResult.className = "";
  const result = await browser.runtime.sendMessage({ type: "ping" });
  if (result && result.status === "ok") {
    testResult.textContent = "Connected - Cove v" + result.version;
    testResult.className = "ok";
  } else {
    testResult.textContent = "Failed - " + (result?.message || "Cannot reach Cove");
    testResult.className = "error";
  }
});

loadSettings();
```

- [ ] **Step 4: Test the options page in Firefox**

Run: `cd extension && npx web-ext run`

Verify:
1. Right-click extension icon -> "Manage Extension" -> Preferences
2. Options page loads with dark theme
3. Can toggle interception, change file types, add excluded domains
4. "Test Connection" shows connected/error status
5. Save persists settings

- [ ] **Step 5: Commit**

```bash
git add extension/options/
git commit -m "feat: add extension options page with filter configuration"
```

---

## Task 8: End-to-end integration test

**Files:** None new - this is a manual verification task.

- [ ] **Step 1: Install the native messaging host**

Run:
```bash
pip install -e .
./scripts/install-native-host.sh
```

Verify: `cat ~/.mozilla/native-messaging-hosts/cove_download_manager.json` shows correct manifest.

- [ ] **Step 2: Start Cove and verify aria2 is running**

Run: `cove &` (or launch from desktop)

Verify: Cove window appears, no aria2 error dialog.

- [ ] **Step 3: Load the extension in Firefox**

Run: `cd extension && npx web-ext run`

Or manually: `about:debugging` -> "This Firefox" -> "Load Temporary Add-on" -> select `extension/manifest.json`

- [ ] **Step 4: Test connection from popup**

Click the Cove toolbar icon. Verify:
- Status shows "Connected - Cove v1.3.1"
- Toggle shows "ON"

- [ ] **Step 5: Test context menu download**

1. Navigate to a page with a download link (e.g., any file hosting page)
2. Right-click a link -> "Download with Cove"
3. Verify: notification appears "Download sent to Cove"
4. Verify: download appears in Cove's main window

- [ ] **Step 6: Test automatic interception**

1. Click a `.zip` or `.iso` download link normally
2. Verify: Firefox's download dialog does NOT appear
3. Verify: notification appears "Download sent to Cove"
4. Verify: download appears in Cove's main window

- [ ] **Step 7: Test size-based interception**

1. Set minimum size to 1 MB in options
2. Click a small file link (< 1MB, not in the extension list)
3. Verify: Firefox handles the download normally
4. Click a large file link (> 1MB)
5. Verify: Cove intercepts it

- [ ] **Step 8: Test excluded domains**

1. Add a domain to the excluded list in options
2. Try to download a file from that domain
3. Verify: Firefox handles the download normally (not intercepted)

- [ ] **Step 9: Final commit with any fixes**

```bash
git add -A
git commit -m "feat: complete Firefox extension MVP with native messaging integration"
```

---

## Summary

| Task | Component | Files |
|------|-----------|-------|
| 1 | aria2 headers support | `cove/aria2.py`, `tests/test_aria2_headers.py` |
| 2 | Native messaging host | `cove/native_messaging.py`, `tests/test_native_messaging.py` |
| 3 | Host registration script | `scripts/install-native-host.sh` |
| 4 | Extension manifest + icons | `extension/manifest.json`, `extension/icons/` |
| 5 | Background script | `extension/background.js` |
| 6 | Popup UI | `extension/popup/` |
| 7 | Options page | `extension/options/` |
| 8 | End-to-end testing | Manual verification |
