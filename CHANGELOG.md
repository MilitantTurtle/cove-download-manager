# Changelog

## 1.9.1 - 2026-07-16

### Added

- YouTube watch, Shorts, live, and embedded-page downloads through the browser
  extension and Cove's native messaging bridge, using `yt-dlp`.
- Improved in-page video detection for active playback, embedded frames, HLS,
  and direct old Reddit video pages.
- An extension setting to enable or disable the in-page download pill.
- Bundled `yt-dlp.exe` in native, Wine, and GitHub Windows builds so the new
  video extraction path works without a separate installation.

### Changed

- Browser-initiated video downloads now use safer page-title-based filenames.
- Chrome extension metadata is now version 1.3.0 and Firefox is version 1.4.0.
- Firefox extension minimums are now desktop 140 and Android 142.
- Documentation now identifies the packaged AI wrapper as Windows-only and
  directs Linux integrations to the cross-platform direct local API method.
- MP3 post-download conversion was removed to stay aligned with upstream; an
  audio-download mode can be added separately later if needed.

### Fixed

- Browser extension popup content is built with safe DOM APIs rather than
  interpolated HTML.
- Improved video-pill visibility, stream refresh, handoff reliability, and
  unavailable-video reporting.

### Validation

- Full Python suite: 152 tests and 7 subtests passed.
- Extension JavaScript and both manifests passed syntax validation.

## 1.9.0 - 2026-07-14

### Added

- Official authenticated local API on `127.0.0.1` for adding, listing,
  inspecting, pausing, resuming, and safely cancelling downloads.
- Optional dependency-free AI command-line client with stable JSON output,
  automatic Cove startup, safe settings discovery, and generic operating
  instructions for both wrapper and direct-API integrations.
- Per-download API controls for absolute destination, expected filename,
  connection count, and speed limit.

### Changed

- Settings now scroll vertically and size themselves to the available screen,
  keeping lower controls accessible on shorter displays.
- Global speed-limit controls now explain immediate application, support KB/s
  and MB/s presentation, and retain consistent light/dark hover styling.
- Per-file connections are capped at stock aria2's supported maximum of 16;
  legacy settings and queued tasks are migrated defensively.
- Windows portable builds select adjacent `cove-app-data` storage on their
  first launch, before configuration modules are imported.
- Release, installer, updater, support, and package metadata now target the
  MilitantTurtle fork.

### Fixed

- AI filename guidance preserves expected names across Hugging Face Xet/CAS
  redirects instead of leaving content-hash filenames.
- The Windows AI wrapper can receive ampersand-delimited signed URLs through
  an environment variable without command-shell truncation.

### Validation

- Windows portable isolation and signed-URL downloads were exercised locally.
- Windows installer/portable, AppImage, and Debian packages were built by
  GitHub Actions. Linux packages were not runtime-tested for this release.
