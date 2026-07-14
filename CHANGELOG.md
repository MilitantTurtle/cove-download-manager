# Changelog

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
