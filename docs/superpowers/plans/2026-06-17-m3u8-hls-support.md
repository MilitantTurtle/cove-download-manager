# M3U8/HLS Stream Download Support - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Download HLS video streams by detecting M3U8 URLs, spawning ffmpeg as a subprocess, and tracking progress in the existing queue UI. Additionally, the Firefox extension detects M3U8 streams via webRequest and offers them for download.

**Architecture:** URL detection in queue.py routes M3U8 URLs to a new `_launch_hls()` code path that spawns ffmpeg via QProcess instead of calling aria2. A progress parser reads ffmpeg's stderr to drive the existing progress bar. The Firefox extension adds a webRequest listener that stores detected streams per-tab and surfaces them in the popup.

**Tech Stack:** Python 3.13, PySide6 (QProcess), ffmpeg, sqlite3, Firefox WebExtension API (webRequest)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `cove/hls.py` | Create | M3U8 URL detection, ffmpeg progress parsing, ffmpeg command builder |
| `cove/queue.py` | Modify | Backend dispatch in `_launch()`, HLS subprocess management, poll routing |
| `cove/db.py` | Modify | Add `backend` column migration |
| `cove/main_window.py` | Modify | HLS-aware progress/size/speed display, disable pause for HLS |
| `cove/config.py` | Modify | Add `.m3u8` to CATEGORY_MAP as Videos |
| `tests/test_hls.py` | Create | Tests for URL detection, progress parsing |
| `extension/manifest.json` | Modify | Add `webRequest` permission |
| `extension/background.js` | Modify | webRequest listener, per-tab stream storage, badge |
| `extension/popup/popup.html` | Modify | Detected streams section |
| `extension/popup/popup.js` | Modify | Stream list rendering, download button handler |

---

### Task 1: URL Detection & Progress Parser Module

**Files:**
- Create: `cove/hls.py`
- Create: `tests/test_hls.py`

- [ ] **Step 1: Write failing tests for is_hls_url()**

```python
# tests/test_hls.py
from cove.hls import is_hls_url, parse_ffmpeg_progress, ffmpeg_command


class TestIsHlsUrl:
    def test_m3u8_extension(self):
        assert is_hls_url("https://example.com/stream/master.m3u8") is True

    def test_m3u8_with_query_params(self):
        assert is_hls_url("https://cdn.example.com/live/index.m3u8?token=abc123&exp=999") is True

    def test_m3u8_case_insensitive(self):
        assert is_hls_url("https://example.com/video.M3U8") is True

    def test_regular_url(self):
        assert is_hls_url("https://example.com/file.zip") is False

    def test_mp4_url(self):
        assert is_hls_url("https://example.com/video.mp4") is False

    def test_empty_url(self):
        assert is_hls_url("") is False

    def test_m3u8_in_path_not_extension(self):
        assert is_hls_url("https://example.com/m3u8/other.txt") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_hls.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cove.hls'`

- [ ] **Step 3: Implement is_hls_url()**

```python
# cove/hls.py
"""HLS/M3U8 stream support — URL detection, ffmpeg command, progress parsing."""

from __future__ import annotations

from urllib.parse import urlparse


def is_hls_url(url: str) -> bool:
    """Return True if the URL points to an M3U8 playlist."""
    if not url:
        return False
    path = urlparse(url).path
    return path.lower().endswith(".m3u8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_hls.py::TestIsHlsUrl -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Write failing tests for parse_ffmpeg_progress()**

Add to `tests/test_hls.py`:

```python
class TestParseFfmpegProgress:
    def test_time_and_speed(self):
        line = "frame=  120 fps=30 size=   1024kB time=00:01:23.45 bitrate= 500kbits/s speed=2.10x"
        result = parse_ffmpeg_progress(line)
        assert result["time_secs"] == 83.45
        assert result["speed"] == "2.10x"

    def test_duration_line(self):
        line = "  Duration: 00:05:40.00, start: 0.000000, bitrate: 3000 kb/s"
        result = parse_ffmpeg_progress(line)
        assert result["duration_secs"] == 340.0

    def test_no_match(self):
        result = parse_ffmpeg_progress("some random ffmpeg output")
        assert result == {}

    def test_time_zero(self):
        line = "frame=    0 fps=0.0 size=       0kB time=00:00:00.00 speed=N/A"
        result = parse_ffmpeg_progress(line)
        assert result["time_secs"] == 0.0
        assert result["speed"] == "N/A"

    def test_percentage_calculation(self):
        line = "time=00:01:00.00 speed=1.50x"
        result = parse_ffmpeg_progress(line, duration_secs=120.0)
        assert result["pct"] == 50
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `python -m pytest tests/test_hls.py::TestParseFfmpegProgress -v`
Expected: FAIL

- [ ] **Step 7: Implement parse_ffmpeg_progress()**

Add to `cove/hls.py`:

```python
import re

_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
_SPEED_RE = re.compile(r"speed=\s*(\S+)")
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)")


def _hms_to_secs(h: str, m: str, s: str, cs: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs.ljust(2, "0")[:2]) / 100


def parse_ffmpeg_progress(line: str, duration_secs: float = 0.0) -> dict:
    """Parse a line of ffmpeg stderr for progress info.

    Returns a dict that may contain:
      time_secs, speed, duration_secs, pct
    """
    result: dict = {}

    dur = _DURATION_RE.search(line)
    if dur:
        result["duration_secs"] = _hms_to_secs(*dur.groups())
        return result

    tm = _TIME_RE.search(line)
    if tm:
        secs = _hms_to_secs(*tm.groups())
        result["time_secs"] = secs
        sp = _SPEED_RE.search(line)
        result["speed"] = sp.group(1) if sp else ""
        if duration_secs > 0:
            result["pct"] = min(100, int(secs * 100 / duration_secs))
        return result

    return result
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_hls.py -v`
Expected: All 12 tests PASS

- [ ] **Step 9: Write test and implement ffmpeg_command()**

Add to `tests/test_hls.py`:

```python
class TestFfmpegCommand:
    def test_basic_command(self):
        cmd = ffmpeg_command("https://example.com/stream.m3u8", "/tmp/out.mp4")
        assert cmd == [
            "ffmpeg", "-y", "-i", "https://example.com/stream.m3u8",
            "-c", "copy", "-bsf:a", "aac_adtstoasc", "/tmp/out.mp4",
        ]
```

Add to `cove/hls.py`:

```python
def ffmpeg_command(url: str, output_path: str) -> list[str]:
    """Build the ffmpeg command for an HLS download."""
    return [
        "ffmpeg", "-y", "-i", url,
        "-c", "copy", "-bsf:a", "aac_adtstoasc", output_path,
    ]
```

- [ ] **Step 10: Run all tests and verify**

Run: `python -m pytest tests/test_hls.py -v`
Expected: All 13 tests PASS

- [ ] **Step 11: Commit**

```bash
git add cove/hls.py tests/test_hls.py
git commit -m "feat: add HLS URL detection and ffmpeg progress parser"
```

---

### Task 2: DB Migration & DownloadTask Backend Field

**Files:**
- Modify: `cove/db.py` (migration list, ~L29-49)
- Modify: `cove/queue.py` (DownloadTask dataclass ~L27-45, add_url ~L286, _load_persisted ~L147)

- [ ] **Step 1: Add backend column migration to db.py**

Read `cove/db.py` and find `_MIGRATIONS`. Add a new migration list entry:

```python
# Add to the end of _MIGRATIONS list:
[
    "ALTER TABLE downloads ADD COLUMN backend TEXT DEFAULT 'aria2'",
],
```

- [ ] **Step 2: Add backend field to DownloadTask**

In `cove/queue.py`, add `backend` to the `DownloadTask` dataclass after the existing fields:

```python
    backend: str = "aria2"  # "aria2" or "ffmpeg"
```

- [ ] **Step 3: Persist backend in add_url()**

In `cove/queue.py:add_url()`, find the INSERT statement. Add `backend` to the column list and values. Before the INSERT, add HLS detection:

```python
from .hls import is_hls_url

# In add_url(), before the INSERT:
backend = "ffmpeg" if is_hls_url(url) else "aria2"

if backend == "ffmpeg":
    import shutil
    if not shutil.which("ffmpeg"):
        self.error.emit("ffmpeg is required for HLS/M3U8 downloads")
        return None
    # Force .mp4 extension for HLS downloads
    if filename and not filename.lower().endswith(".mp4"):
        filename = filename.rsplit(".", 1)[0] + ".mp4" if "." in filename else filename + ".mp4"
    elif not filename:
        from urllib.parse import urlparse
        path = urlparse(url).path.rsplit("/", 1)[-1]
        filename = (path.rsplit(".", 1)[0] if "." in path else "stream") + ".mp4"
```

Add `backend` to the INSERT column list and the `DownloadTask(...)` constructor call.

- [ ] **Step 4: Load backend from DB in _load_persisted()**

In `_load_persisted()`, read `backend` from the row dict with a default:

```python
backend=row.get("backend", "aria2"),
```

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add cove/db.py cove/queue.py
git commit -m "feat: add backend field to DownloadTask and DB migration"
```

---

### Task 3: HLS Subprocess Management in Queue

**Files:**
- Modify: `cove/queue.py` (~L542 _launch, ~L699 _poll_active)

- [ ] **Step 1: Add HLS process tracking dict**

In `DownloadQueue.__init__()`, add:

```python
self._hls_procs: dict[int, QProcess] = {}
self._hls_duration: dict[int, float] = {}
self._hls_stderr: dict[int, str] = {}
```

Add import at the top of queue.py:

```python
from PySide6.QtCore import QProcess
from .hls import ffmpeg_command, parse_ffmpeg_progress, is_hls_url
```

- [ ] **Step 2: Implement _launch_hls()**

Add this method to `DownloadQueue`:

```python
def _launch_hls(self, t: DownloadTask) -> None:
    """Spawn ffmpeg to download an HLS stream."""
    output_path = os.path.join(t.out_dir, t.filename or "stream.mp4")
    cmd = ffmpeg_command(t.url, output_path)

    proc = QProcess(self)
    proc.setProcessChannelMode(QProcess.MergedChannels)
    self._hls_procs[t.id] = proc
    self._hls_duration[t.id] = 0.0
    self._hls_stderr[t.id] = ""

    def on_stderr():
        data = proc.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._hls_stderr[t.id] = data
        for line in data.splitlines():
            info = parse_ffmpeg_progress(line, self._hls_duration.get(t.id, 0.0))
            if "duration_secs" in info:
                self._hls_duration[t.id] = info["duration_secs"]
            if "time_secs" in info:
                t.completed_bytes = int(info["time_secs"])
                t.download_speed = 0
                t.error = info.get("speed", "")
                if "pct" in info:
                    dur = self._hls_duration[t.id]
                    t.total_bytes = int(dur) if dur else 0
                self.task_changed.emit(t.id)

    def on_finished(exit_code, exit_status):
        self._hls_procs.pop(t.id, None)
        self._hls_duration.pop(t.id, None)
        stderr = self._hls_stderr.pop(t.id, "")
        if exit_code == 0:
            t.status = "completed"
            t.finished_at = time.time()
            if self._hls_duration.get(t.id):
                t.completed_bytes = t.total_bytes
        else:
            t.status = "error"
            last_lines = "\n".join(stderr.splitlines()[-5:])
            t.error = last_lines or f"ffmpeg exited with code {exit_code}"
        self._persist(t)
        self.task_changed.emit(t.id)
        self._maybe_start_next()

    proc.readyReadStandardOutput.connect(on_stderr)
    proc.finished.connect(on_finished)
    proc.start(cmd[0], cmd[1:])
```

- [ ] **Step 3: Add backend dispatch in _launch()**

In `_launch()`, add dispatch at the top of the method body, after setting status to "active":

```python
if t.backend == "ffmpeg":
    self._launch_hls(t)
    return
```

This goes right after `self.task_changed.emit(t.id)` (the status change notification), before the existing aria2 logic.

- [ ] **Step 4: Route _poll_active() around HLS tasks**

In `_poll_active()`, the filter already checks `t.gid`. HLS tasks have `gid=None`, so they're skipped by the existing filter. No change needed for polling - progress comes from the QProcess stderr callback.

Verify: the existing filter is `t.gid and t.status in {"active", "paused"}`. HLS tasks have `gid=None`, so they won't be polled via aria2. Correct.

- [ ] **Step 5: Handle cancel for HLS tasks**

Find the cancel/remove method that calls `rpc.remove`. Add an HLS branch:

In `remove_task()`, before the `if gid:` block, add:

```python
if tid in self._hls_procs:
    proc = self._hls_procs.pop(tid, None)
    self._hls_duration.pop(tid, None)
    self._hls_stderr.pop(tid, None)
    if proc and proc.state() != QProcess.NotRunning:
        proc.terminate()
```

- [ ] **Step 6: Handle app shutdown**

Find the `shutdown()` or `stop()` method that stops the queue. Add HLS cleanup:

```python
for proc in list(self._hls_procs.values()):
    if proc.state() != QProcess.NotRunning:
        proc.terminate()
self._hls_procs.clear()
```

- [ ] **Step 7: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 8: Compile check**

Run: `python -m py_compile cove/queue.py`
Expected: No errors

- [ ] **Step 9: Commit**

```bash
git add cove/queue.py
git commit -m "feat: add HLS subprocess management with ffmpeg in queue"
```

---

### Task 4: UI Adaptations for HLS Downloads

**Files:**
- Modify: `cove/main_window.py` (~L840 _render, ~L715 context menu)
- Modify: `cove/config.py` (~L42 CATEGORY_MAP)

- [ ] **Step 1: Add .m3u8 to CATEGORY_MAP**

In `cove/config.py`, add to the `CATEGORY_MAP` dict:

```python
".m3u8": "Videos",
```

- [ ] **Step 2: Adapt _render() for HLS progress display**

In `_render()` (cove/main_window.py ~L840), the progress bar section calculates `pct = int(completed * 100 / task.total_bytes)`. For HLS tasks, `total_bytes` holds duration in seconds and `completed_bytes` holds elapsed seconds. The percentage math works the same way.

For the Size column, add an HLS branch before the existing size formatting:

```python
if task.backend == "ffmpeg":
    if task.total_bytes > 0:
        elapsed = task.completed_bytes
        total = task.total_bytes
        item.setText(COL_SIZE, f"{elapsed // 60}:{elapsed % 60:02d} / {total // 60}:{total % 60:02d}")
    else:
        item.setText(COL_SIZE, "--")
```

For the Speed column, HLS tasks store the ffmpeg speed string in `task.error` (repurposed during active state). Add before existing speed formatting:

```python
if task.backend == "ffmpeg" and task.status == "active":
    item.setText(COL_SPEED, task.error or "")  # ffmpeg speed like "2.1x"
```

Note: `task.error` is repurposed to hold the speed string while the task is active. When the task completes or errors, `task.error` is set to the real error message or `None`.

- [ ] **Step 3: Disable Pause in context menu for HLS tasks**

In `_open_context_menu()`, find where the Pause action is added (L748). Wrap it:

```python
if t.backend != "ffmpeg":
    menu.addAction("Pause", ...)
```

Do the same for Resume (L756) - HLS tasks can't be paused so they can't be resumed either.

- [ ] **Step 4: Compile check**

Run: `python -m py_compile cove/main_window.py && python -m py_compile cove/config.py`
Expected: No errors

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add cove/main_window.py cove/config.py
git commit -m "feat: HLS-aware progress display and category mapping"
```

---

### Task 5: Firefox Extension - webRequest Stream Detection

**Files:**
- Modify: `extension/manifest.json`
- Modify: `extension/background.js`

- [ ] **Step 1: Add webRequest permission to manifest.json**

In `extension/manifest.json`, add `"webRequest"` to the `permissions` array:

```json
"permissions": [
    "downloads",
    "cookies",
    "contextMenus",
    "nativeMessaging",
    "notifications",
    "storage",
    "webRequest",
    "<all_urls>"
],
```

- [ ] **Step 2: Add stream detection to background.js**

Add the following at module scope in `extension/background.js`, after the existing download interception code:

```javascript
// ---- HLS/M3U8 stream detection ----

const HLS_CONTENT_TYPES = [
  "application/vnd.apple.mpegurl",
  "application/x-mpegurl",
  "audio/mpegurl",
  "audio/x-mpegurl",
];

const detectedStreams = new Map(); // tabId -> [{url, type, timestamp}]

function isHlsResponse(details) {
  const url = details.url || "";
  if (url.split("?")[0].toLowerCase().endsWith(".m3u8")) return true;
  const headers = details.responseHeaders || [];
  for (const h of headers) {
    if (h.name.toLowerCase() === "content-type") {
      const ct = (h.value || "").toLowerCase().split(";")[0].trim();
      if (HLS_CONTENT_TYPES.includes(ct)) return true;
    }
  }
  return false;
}

if (browser.webRequest) {
  browser.webRequest.onHeadersReceived.addListener(
    (details) => {
      if (!isHlsResponse(details)) return;
      const tabId = details.tabId;
      if (tabId < 0) return; // ignore non-tab requests

      if (!detectedStreams.has(tabId)) {
        detectedStreams.set(tabId, []);
      }
      const streams = detectedStreams.get(tabId);
      // Deduplicate by URL
      if (streams.some((s) => s.url === details.url)) return;
      streams.push({
        url: details.url,
        type: "m3u8",
        timestamp: Date.now(),
      });
      updateStreamBadge(tabId);
    },
    { urls: ["<all_urls>"] },
    ["responseHeaders"]
  );
}

function updateStreamBadge(tabId) {
  browser.tabs.query({ active: true, currentWindow: true }).then((tabs) => {
    if (tabs[0] && tabs[0].id === tabId) {
      const streams = detectedStreams.get(tabId) || [];
      const count = streams.length;
      browser.action.setBadgeText({ text: count > 0 ? String(count) : "" });
      browser.action.setBadgeBackgroundColor({ color: "#50e6cf" });
    }
  });
}

// Clear streams when tab navigates or closes
browser.tabs.onRemoved.addListener((tabId) => {
  detectedStreams.delete(tabId);
});

browser.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.url) {
    detectedStreams.delete(tabId);
    updateStreamBadge(tabId);
  }
});

// Update badge when switching tabs
browser.tabs.onActivated.addListener(({ tabId }) => {
  updateStreamBadge(tabId);
});

// Expose streams to popup
browser.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "getDetectedStreams") {
    browser.tabs.query({ active: true, currentWindow: true }).then((tabs) => {
      const tabId = tabs[0] ? tabs[0].id : -1;
      sendResponse(detectedStreams.get(tabId) || []);
    });
    return true; // async sendResponse
  }
});
```

- [ ] **Step 3: Add download handler for detected streams**

The popup will send a message to download a detected stream. Add this handler inside the existing `browser.runtime.onMessage.addListener` block, or add a new case to the existing listener:

```javascript
if (msg.action === "downloadStream") {
  sendNativeMessage({
    action: "download",
    url: msg.url,
    filename: msg.filename || "",
    referrer: msg.referrer || "",
    cookies: "",
    fileSize: 0,
    userAgent: navigator.userAgent,
  }).then(() => sendResponse({ ok: true }))
    .catch((e) => sendResponse({ error: e.message }));
  return true;
}
```

- [ ] **Step 4: Commit**

```bash
git add extension/manifest.json extension/background.js
git commit -m "feat: Firefox webRequest HLS stream detection with badge"
```

---

### Task 6: Firefox Extension - Popup Detected Streams UI

**Files:**
- Modify: `extension/popup/popup.html`
- Modify: `extension/popup/popup.js`

- [ ] **Step 1: Add detected streams section to popup.html**

Read `extension/popup/popup.html`. Add a new section after the existing downloads list, before the footer:

```html
<div id="streams-section" style="display: none;">
  <div class="section-header">Detected Streams</div>
  <div id="streams-list"></div>
</div>
```

Add CSS for the section header and stream items. Use the same styling patterns as the existing downloads list. Add to the `<style>` block:

```css
.section-header {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #888;
  padding: 8px 12px 4px;
  border-top: 1px solid #2a2a2a;
}
.stream-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid #1e1e1e;
}
.stream-url {
  flex: 1;
  font-size: 12px;
  color: #ccc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}
.stream-download-btn {
  background: #50e6cf;
  color: #000;
  border: none;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.stream-download-btn:hover {
  background: #3dd4be;
}
```

- [ ] **Step 2: Add stream detection polling to popup.js**

Read `extension/popup/popup.js`. Add a function to query and render detected streams:

```javascript
async function refreshStreams() {
  try {
    const streams = await browser.runtime.sendMessage({ action: "getDetectedStreams" });
    const section = document.getElementById("streams-section");
    const list = document.getElementById("streams-list");

    if (!streams || streams.length === 0) {
      section.style.display = "none";
      return;
    }

    section.style.display = "block";
    list.innerHTML = "";

    for (const stream of streams) {
      const item = document.createElement("div");
      item.className = "stream-item";

      const urlSpan = document.createElement("span");
      urlSpan.className = "stream-url";
      const url = stream.url;
      const shortUrl = url.split("?")[0].split("/").slice(-2).join("/");
      urlSpan.textContent = shortUrl;
      urlSpan.title = url;

      const btn = document.createElement("button");
      btn.className = "stream-download-btn";
      btn.textContent = "Download";
      btn.addEventListener("click", () => {
        const filename = shortUrl.split("/").pop().replace(".m3u8", ".mp4") || "stream.mp4";
        browser.runtime.sendMessage({
          action: "downloadStream",
          url: stream.url,
          filename: filename,
        });
        btn.textContent = "Sent!";
        btn.disabled = true;
        setTimeout(() => {
          btn.textContent = "Download";
          btn.disabled = false;
        }, 2000);
      });

      item.appendChild(urlSpan);
      item.appendChild(btn);
      list.appendChild(item);
    }
  } catch {}
}
```

- [ ] **Step 3: Call refreshStreams() on popup open**

In `popup.js`, find the `DOMContentLoaded` or initialization code. Add `refreshStreams()` alongside the existing refresh calls:

```javascript
refreshStreams();
```

Also add it to the existing periodic refresh interval if there is one, so detected streams update while the popup is open.

- [ ] **Step 4: Commit**

```bash
git add extension/popup/popup.html extension/popup/popup.js
git commit -m "feat: detected streams UI in Firefox extension popup"
```

---

### Task 7: Integration Testing & Polish

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS (including new test_hls.py tests)

- [ ] **Step 2: Compile check all modified Python files**

Run: `python -m py_compile cove/hls.py cove/queue.py cove/db.py cove/main_window.py cove/config.py`
Expected: No errors

- [ ] **Step 3: Manual smoke test with a public M3U8 URL**

Test the full flow by pasting a public HLS test stream URL into Cove's Add Download dialog. Apple provides public test streams:

```
https://devstreaming-cdn.apple.com/videos/streaming/examples/bipbop_4x3/bipbop_4x3_variant.m3u8
```

Verify:
- URL is detected as HLS (backend=ffmpeg)
- ffmpeg spawns and downloads
- Progress bar advances
- Size shows elapsed/total time
- Speed shows ffmpeg multiplier
- File completes as .mp4
- File plays in a video player

- [ ] **Step 4: Test cancel during HLS download**

Start an HLS download, then right-click and Remove. Verify:
- ffmpeg process is terminated
- Task removed from list
- No orphan ffmpeg processes (`ps aux | grep ffmpeg`)

- [ ] **Step 5: Test extension stream detection**

Open Firefox with the extension loaded. Navigate to a page that plays HLS video. Verify:
- Extension badge shows stream count
- Popup shows detected streams with Download button
- Clicking Download sends URL to Cove
- Cove receives and starts the HLS download

- [ ] **Step 6: Final commit**

```bash
git add -A
git status
# Review staged files, then:
git commit -m "feat: M3U8/HLS stream download support with Firefox detection"
```
