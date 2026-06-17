"""Tests for clipboard URL extraction."""
from cove.clipboard import extract_urls


def test_strips_trailing_punctuation_and_brackets():
    text = (
        "see <https://example.com/a.zip> and (https://example.com/b.iso) "
        "or https://example.com/c.7z]"
    )
    urls = extract_urls(text)
    assert "https://example.com/a.zip" in urls
    assert "https://example.com/b.iso" in urls
    assert "https://example.com/c.7z" in urls


def test_dedups_and_handles_empty():
    assert extract_urls("") == []
    urls = extract_urls("https://x.com/f https://x.com/f")
    assert urls == ["https://x.com/f"]


def test_keeps_query_strings():
    urls = extract_urls("https://example.com/get?id=123&t=zip")
    assert urls == ["https://example.com/get?id=123&t=zip"]
