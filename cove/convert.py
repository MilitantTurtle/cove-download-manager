"""MP3 post-conversion helpers: output naming and ffmpeg argv construction.

Pure functions only - process management lives in the queue manager,
mirroring how hls.py provides the command and queue.py runs it.
"""

from __future__ import annotations

import os
from pathlib import Path


def build_output_path(source: Path) -> Path:
    """Return `<stem>.mp3` next to the source, appending ` (n)` on collision
    so an existing file is never overwritten."""
    candidate = source.with_suffix(".mp3")
    n = 0
    while candidate.exists():
        n += 1
        candidate = source.with_name(f"{source.stem} ({n}).mp3")
    return candidate


def temp_output_path(source: Path, token: int | str) -> Path:
    """Conversion-owned scratch file next to the source. Unique per task
    token, so -y can only ever clobber this conversion's own leftovers."""
    return source.with_name(f".cove-convert-{token}.tmp.mp3")


def reserve_output_path(source: Path) -> Path:
    """Atomically claim the final `.mp3` path with O_CREAT|O_EXCL, walking
    the ` (n)` suffixes on collision. The returned path exists as an empty
    placeholder owned by the caller; os.replace() a finished file onto it."""
    candidate = source.with_suffix(".mp3")
    n = 0
    while True:
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            n += 1
            candidate = source.with_name(f"{source.stem} ({n}).mp3")
            continue
        os.close(fd)
        return candidate


def _meta(key: str, value: str) -> str:
    """Format one -metadata argv entry, collapsing newlines that would
    corrupt the tag value."""
    clean = value.replace("\r", " ").replace("\n", " ").strip()
    return f"{key}={clean}"


def ffmpeg_mp3_command(source: Path, output: Path, source_url: str | None = None) -> list[str]:
    """List-form ffmpeg argv converting `source` to MP3 at `output`.

    Never invoked through a shell. `output` must be a fresh path from
    build_output_path; -y only clobbers ffmpeg's own partial output on retry.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(source),
        "-vn", "-map_metadata", "0",
        "-c:a", "libmp3lame", "-q:a", "2",
        "-metadata", _meta("title", source.stem),
    ]
    if source_url:
        cmd += ["-metadata", _meta("comment", f"Source: {source_url}")]
    cmd += ["-id3v2_version", "3", str(output)]
    return cmd
