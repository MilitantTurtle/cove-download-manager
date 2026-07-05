"""Tests for cove.convert - MP3 output naming and ffmpeg argv construction."""

from pathlib import Path

from cove.convert import (
    build_output_path,
    ffmpeg_mp3_command,
    reserve_output_path,
    temp_output_path,
)


def test_output_path_no_collision(tmp_path):
    src = tmp_path / "video.mp4"
    assert build_output_path(src) == tmp_path / "video.mp3"


def test_output_path_collision_suffixes(tmp_path):
    src = tmp_path / "video.mp4"
    (tmp_path / "video.mp3").touch()
    assert build_output_path(src) == tmp_path / "video (1).mp3"
    (tmp_path / "video (1).mp3").touch()
    assert build_output_path(src) == tmp_path / "video (2).mp3"


def test_reserve_output_path_claims_atomically(tmp_path):
    src = tmp_path / "video.mp4"
    first = reserve_output_path(src)
    assert first == tmp_path / "video.mp3"
    assert first.exists()  # placeholder is created, reserving the name
    second = reserve_output_path(src)
    assert second == tmp_path / "video (1).mp3"
    third = reserve_output_path(src)
    assert third == tmp_path / "video (2).mp3"


def test_temp_output_path_is_per_token(tmp_path):
    src = tmp_path / "video.mp4"
    a = temp_output_path(src, 7)
    b = temp_output_path(src, 8)
    assert a != b
    assert a.parent == tmp_path
    assert a.name.endswith(".tmp.mp3")


def test_ffmpeg_command_exact_args():
    src = Path("/dl/clip.mp4")
    out = Path("/dl/clip.mp3")
    cmd = ffmpeg_mp3_command(src, out, source_url="https://example.com/v.mp4")
    assert cmd == [
        "ffmpeg", "-y", "-i", "/dl/clip.mp4",
        "-vn", "-map_metadata", "0",
        "-c:a", "libmp3lame", "-q:a", "2",
        "-metadata", "title=clip",
        "-metadata", "comment=Source: https://example.com/v.mp4",
        "-id3v2_version", "3", "/dl/clip.mp3",
    ]


def test_ffmpeg_command_without_url():
    cmd = ffmpeg_mp3_command(Path("/dl/a.webm"), Path("/dl/a.mp3"))
    assert "-metadata" in cmd
    assert cmd[cmd.index("-metadata") + 1] == "title=a"
    assert not any(entry.startswith("comment=") for entry in cmd)


def test_ffmpeg_command_is_plain_argv_list():
    cmd = ffmpeg_mp3_command(Path("/dl/a b.mp4"), Path("/dl/a b.mp3"))
    assert isinstance(cmd, list)
    assert all(isinstance(entry, str) for entry in cmd)
    # Paths with spaces stay single argv entries - never shell-joined.
    assert "/dl/a b.mp4" in cmd
    assert "/dl/a b.mp3" in cmd


def test_metadata_newlines_sanitized():
    cmd = ffmpeg_mp3_command(
        Path("/dl/x.mp4"), Path("/dl/x.mp3"), source_url="https://e.com/a\nb"
    )
    comment = [e for e in cmd if e.startswith("comment=")][0]
    assert "\n" not in comment
    assert "\r" not in comment
