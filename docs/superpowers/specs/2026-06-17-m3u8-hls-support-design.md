# M3U8/HLS Stream Download Support

**Date:** 2026-06-17
**Status:** Approved
**Approach:** Subprocess Worker in Queue (Approach A)

## Summary

Add support for downloading HLS (HTTP Live Streaming) video streams by
detecting M3U8 URLs and delegating to ffmpeg as a subprocess. Downloads
appear in the same queue and UI as regular aria2 downloads with minor
display differences. No new UI elements, dialogs, or settings required.

## Background

HLS streams split video into small .ts segments listed in an M3U8 playlist.
aria2 cannot parse M3U8 playlists or reassemble segments. ffmpeg handles
all HLS complexity natively: playlist parsing, segment fetching, adaptive
bitrate selection, decryption, and remuxing into mp4.

## Design

### URL Detection

Detection runs in `queue.py:add_url()` before task creation.

**By extension:** URL path ends in `.m3u8` (stripped of query params).

**By content-type probe:** HEAD request returns `application/vnd.apple.mpegurl`
or `application/x-mpegURL`.

A new `backend` field on `DownloadTask` is set to `"ffmpeg"` when HLS is
detected. Default remains `"aria2"` for all other URLs.

**ffmpeg availability:** If `shutil.which("ffmpeg")` returns None when an
M3U8 URL is submitted, show an error dialog and do not create the task.

### Input Method

Manual paste only. User copies the M3U8 URL from browser dev tools or page
source and submits it through the existing Add Download dialog or Ctrl+V
paste. The filename defaults to the URL's last path segment with a `.mp4`
extension.

### Output Format

Always MP4. ffmpeg remuxes with `-c copy -bsf:a aac_adtstoasc` (no
re-encoding, fast).

### Quality Selection

Always best quality. ffmpeg auto-selects the highest bitrate variant from
master playlists. No quality picker UI.

### Task Lifecycle

When `_launch()` sees `t.backend == "ffmpeg"`, it calls `_launch_hls(t)`:

**Spawn:** `ffmpeg -y -i <url> -c copy -bsf:a aac_adtstoasc <output_path>`
via `QProcess`.

**Progress tracking:** A 500ms timer reads ffmpeg's stderr and parses
`time=HH:MM:SS.ms` against total duration (from the first `Duration:` line
or an initial probe). This yields a percentage for the progress bar.

**Status mapping:**
- Process running: `"active"`
- Exit code 0: `"completed"`
- Non-zero exit: `"error"` with stderr as error message

**PID tracking:** Running QProcess instances stored in
`_hls_procs: dict[int, QProcess]` keyed by task ID. No aria2 GID involved.

**Cancel:** Sends SIGTERM to ffmpeg (writes valid partial file on graceful
termination).

**Pause:** Not supported for HLS tasks. Pause button disabled/hidden.

**Queue integration:** HLS tasks count toward `max_concurrent` slots and
wait in the queue like aria2 tasks.

### Progress Display

HLS tasks appear in the existing download tree:

| Column   | HLS behavior                                        |
|----------|-----------------------------------------------------|
| Name     | Filename with `.mp4` extension                      |
| Status   | `queued`, `active`, `completed`, `error` as normal  |
| Progress | Percentage based on time position (`42%`)           |
| Size     | Elapsed / total time (e.g. `1:23 / 5:40`) or `--`  |
| Speed    | ffmpeg's speed multiplier (e.g. `2.1x`)             |

Context menu: same options, except Pause is disabled for HLS tasks.
Remove, Open File, Open Folder work normally.

### Inapplicable Features

These existing features do not apply to HLS tasks:

- **Speed limit:** ffmpeg manages its own downloads. Global speed limit
  only affects aria2 tasks.
- **Connections/segments:** ffmpeg handles connection management. Segment
  indicator (`[8x]`) not shown.
- **Intelligent segmenting:** Skipped for HLS URLs.

### Category

HLS downloads auto-categorize as "Videos" since output is always mp4.

### Error Handling

- **Invalid/expired M3U8:** ffmpeg exits non-zero. Task goes to `"error"`
  with stderr in tooltip.
- **DRM/encrypted streams:** ffmpeg fails on Widevine etc. Error surfaces
  naturally.
- **Network interruption:** ffmpeg retries internally. If it gives up,
  task goes to `"error"`. User can retry via context menu.
- **Output file exists:** `-y` flag overwrites, matching aria2's behavior.
- **App shutdown:** SIGTERM sent to running ffmpeg processes.

### DB Schema

Add `backend TEXT DEFAULT 'aria2'` column to the downloads table. Migration
uses the existing ALTER TABLE + try/except pattern for idempotency.

### Extension: Media Stream Detection (Firefox only)

The Firefox extension uses the webRequest API to detect HLS streams on
pages the user visits, then lets them send detected URLs to Cove.

**Detection:** `webRequest.onHeadersReceived` listener watches all network
responses. A match fires on any of:
- Content-Type: `application/vnd.apple.mpegurl` or `application/x-mpegURL`
- Content-Type: `video/mp2t` (TS segments - extract the referrer M3U8)
- URL path ends in `.m3u8`

**Storage:** Detected streams stored per-tab in memory as
`tabId -> [{url, type, timestamp}]`. Cleared on tab navigation
(`webNavigation.onBeforeNavigate`) or tab close (`tabs.onRemoved`).

**Badge:** Extension icon shows a numeric badge with the count of detected
streams on the active tab. Badge clears when the tab navigates or closes.

**Popup UI:** The existing popup gains a "Detected Streams" section visible
when streams are found on the current tab. Each entry shows the truncated
URL and a "Download" button. Clicking "Download" sends the URL to Cove via
the existing native messaging `add_download` message. Same flow as regular
intercepted downloads from there.

**Permissions:** Add `webRequest` to `manifest.json` permissions. Firefox
MV2 supports this fully. No `webRequestBlocking` needed (observe only).

**Scope:** Firefox only. Chrome uses MV3 which has a different, more
limited webRequest model (`declarativeNetRequest`). Chrome support deferred
until the Chrome extension clears review.

### Files Changed

- `cove/queue.py` - URL detection, `_launch_hls()`, ffmpeg progress
  parsing, backend dispatch in `_launch()` and `_poll_active()`
- `cove/db.py` - Migration for `backend` column
- `cove/main_window.py` - Disable pause for HLS tasks, adapt Size/Speed
  column display
- `cove/config.py` - Add "Videos" to category if not present (for
  auto-categorization)
- `extension/manifest.json` - Add `webRequest` permission
- `extension/background.js` - webRequest listener, per-tab stream storage,
  badge updates
- `extension/popup/popup.html` - Detected streams section
- `extension/popup/popup.js` - Stream list rendering, download button
  handler

### Not In Scope

- Chrome extension stream detection (MV3 declarativeNetRequest)
- Quality selection UI
- MKV output format option
- yt-dlp integration
- Subtitle track extraction
- In-page "Download This Video" overlay button
