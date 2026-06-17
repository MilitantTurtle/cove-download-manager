"""Tests for category routing and the categorize() function."""
from cove.config import categorize, CategoryDirs, Settings


def test_categorize_video_extensions():
    for ext in ("mp4", "mkv", "webm", "mov", "avi"):
        assert categorize(f"https://example.com/file.{ext}") == "Videos"


def test_categorize_archive_extensions():
    for ext in ("zip", "rar", "7z", "tar", "gz"):
        assert categorize(f"https://example.com/file.{ext}") == "Archives"


def test_categorize_document_extensions():
    for ext in ("pdf", "doc", "docx", "epub"):
        assert categorize(f"https://example.com/file.{ext}") == "Documents"


def test_categorize_music_extensions():
    for ext in ("mp3", "flac", "wav", "ogg"):
        assert categorize(f"https://example.com/file.{ext}") == "Music"


def test_categorize_program_extensions():
    for ext in ("exe", "msi", "deb", "appimage"):
        assert categorize(f"https://example.com/file.{ext}") == "Programs"


def test_categorize_image_extensions():
    for ext in ("jpg", "png", "gif", "webp"):
        assert categorize(f"https://example.com/file.{ext}") == "Images"


def test_categorize_unknown_extension():
    assert categorize("https://example.com/file.xyz") == "Other"


def test_categorize_no_extension():
    assert categorize("https://example.com/download") == "Other"


def test_categorize_case_insensitive():
    assert categorize("https://example.com/file.MKV") == "Videos"
    assert categorize("https://example.com/file.ZIP") == "Archives"


def test_categorize_with_query_string():
    assert categorize("https://example.com/file.mp4?token=abc") == "Videos"


def test_category_dirs_defaults_empty():
    cd = CategoryDirs()
    assert cd.Videos == ""
    assert cd.Documents == ""


def test_settings_category_dirs_serialization():
    s = Settings()
    s.category_dirs.Videos = "/tmp/videos"
    s.auto_sort_by_category = True
    from dataclasses import asdict
    d = asdict(s)
    assert d["category_dirs"]["Videos"] == "/tmp/videos"
    assert d["auto_sort_by_category"] is True
