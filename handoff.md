# Handoff - Fix GitHub issues #4 and #5

## Task
Fix two open GitHub issues:
- Issue #5: No desktop notification when a download fails (or completes)
- Issue #4: Extension cancels browser download but never falls back when Cove app is not running

## Files changed
- `cove/main_window.py` - Desktop notifications via QSystemTrayIcon
- `extension/background.js` - Send-first, cancel-only-on-confirmed-acceptance ordering

## Changes

### Issue #5 - Desktop notifications (cove/main_window.py)

Added `QSystemTrayIcon` to imports.

In `MainWindow.__init__` (end of method):
- Initialize `self._tray` via `QSystemTrayIcon` if the system tray is available, reusing the window icon
- Initialize `self._notified_status: dict[int, str]` to track last-notified state per task

New method `_maybe_notify(task)`:
- When status is not a terminal state: pops the task from `_notified_status` so a retried task can re-notify on next failure
- Returns early if already notified for this task+status combination (prevents firing on every progress tick)
- Shows `Critical` tray message (8s) on error, with filename and error string
- Shows `Information` tray message (5s) on completion

`_on_task_changed` now calls `_maybe_notify` before rendering.

`_on_task_removed` cleans up `_notified_status[tid]` so re-added downloads can notify again.

### Issue #4 - Send-first ordering (extension/background.js)

`interceptDownload()` architectural fix:
- `markIntercepted(url)` is called synchronously at entry to block concurrent same-URL events
- Cookies and filename are gathered while the browser download is still running
- The full download payload is sent to the native host WITHOUT cancelling the browser download first
- On `"ok"` response: add to `interceptedIds`, cancel browser download, erase, show notification
- On any failure: `recentIntercepted.delete(url)` clears the dedup mark so the browser's original download proceeds unimpeded and future intercepts are not blocked
- No ping, no fallback `browser.downloads.download()` - the original browser download is never lost

Context menu handler (`contextMenus.onClicked`):
- No pre-existing browser download exists here (user right-clicked a link), so the fallback `browser.downloads.download()` is correct
- `markIntercepted(url)` before the fallback prevents the new browser download from being re-intercepted

## Verification
- `python3 -c "import ast; ast.parse(...)"` on main_window.py: OK
- `node --check extension/background.js`: OK
- No new dependencies introduced
