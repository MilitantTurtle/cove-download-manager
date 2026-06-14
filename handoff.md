# Handoff: Cove Download Manager - 5 New Features

## Summary

Add 5 features to Cove (PySide6 + aria2 JSON-RPC download manager, v1.3.1): keyboard shortcuts, proxy settings, download categories with auto-sort, drag-and-drop outbound, and intelligent segmenting. Also adds force-start for queued items.

## Scope

### Files changed
- `cove/db.py` - DB migration infrastructure (PRAGMA user_version), category + segments columns
- `cove/config.py` - CATEGORY_MAP, categorize(), proxy/auto-sort/intelligent-segments settings fields
- `cove/aria2.py` - Proxy URL construction and --all-proxy arg, bitfield/numPieces in tell_status
- `cove/queue.py` - DownloadTask new fields (category, segments, bitfield, num_pieces), category in add_url, force_start, server probe (_probe_and_add, _compute_segments), persist category/segments
- `cove/dialogs.py` - Proxy group in SettingsDialog, auto-sort checkbox, smart segments checkbox
- `cove/main_window.py` - Keyboard shortcuts (Ctrl+V/Space/Ctrl+A), Category column, drag-and-drop outbound (startDrag), force-start context menu, segment info in progress bar
- `cove/widgets.py` - _hex_to_bits helper, SegmentBar class (kept for potential future use)

### Out of scope
- `build/recipe/requirements.txt` - build artifact rewritten by build.sh, not part of this feature set
- Untracked files (Archive.zip, docs/, web-ext-artifacts/)
- Firefox extension changes (already committed on this branch)

## Features

### 1. Keyboard Shortcuts
- `Ctrl+V`: Quick paste URLs from clipboard directly to queue (no dialog)
- `Space`: Toggle pause/resume on selected items (WidgetShortcut scoped to tree)
- `Ctrl+A`: Select all items in tree
- Footer updated with Paste and Pause/Resume hints

### 2. Proxy Settings
- Settings fields: proxy_type (none/http/https/socks5), proxy_host, proxy_port, proxy_username, proxy_password
- SettingsDialog: QGroupBox with type combo, host/port/user/pass fields, disabled when type=none
- aria2.py: _build_proxy_url() with urllib.parse.quote for special chars, passed as --all-proxy to daemon
- Note shown: "Restart Cove to apply proxy changes"

### 3. Download Categories & Auto-Sort
- CATEGORY_MAP in config.py: 7 categories (Documents, Videos, Music, Archives, Programs, Images, Other)
- categorize() function: extension-based lookup
- Category assigned in add_url() from URL path, refined in _apply_status() when real filename known
- Optional auto-sort: creates subdirectories (e.g. ~/Downloads/Videos/) when enabled
- Category column added to tree (shifts all column indices)
- DB migration adds `category TEXT` and `segments INTEGER` columns

### 4. Drag-and-Drop Outbound
- DownloadTree.startDrag() creates QDrag with QMimeData containing file:// URLs
- Only completed downloads with existing files are draggable
- DragOnly mode on tree (inbound drops still handled by MainWindow)
- Cross-platform: QUrl.fromLocalFile handles Linux/Windows paths

### 5. Intelligent Segmenting
- HEAD request probe before download (in _probe_and_add, runs off-thread)
- Checks Accept-Ranges and Content-Length headers
- _compute_segments: 1 for <1MB or no Range, 4 for <10MB, 8 for <100MB, max for larger
- Skipped for magnet: links and when intelligent_segments is disabled
- Segment count shown inline in progress bar as "39% [8x]"
- Piece progress available as tooltip via bitfield/numPieces from aria2

### 6. Force-Start Queued Items
- force_start() method bypasses concurrent limit, calls _launch() directly
- "Start now" context menu option for queued items

## Verification

```bash
python -m py_compile cove/db.py cove/config.py cove/aria2.py cove/queue.py cove/widgets.py cove/dialogs.py cove/main_window.py
python -m pytest tests/ -q
```

## Review focus
- DB migration safety (ALTER TABLE with try/except for idempotency)
- Proxy URL construction (special character encoding)
- Thread safety of _probe_and_add (runs on QThreadPool, mutates t.segments)
- Column index shift correctness (COL_NAME=0, COL_CATEGORY=1, COL_STATUS=2, etc.)
- Category assignment timing (URL-based guess vs aria2 filename refinement)
