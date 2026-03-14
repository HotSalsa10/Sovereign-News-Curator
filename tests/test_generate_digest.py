"""
Unit tests for Sovereign News Curator's digest generation pipeline.
Tests pure utility functions; API/file I/O calls are mocked.
Target: 80%+ coverage of scripts/generate_digest.py
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from scripts.generate_digest import (
    strip_html,
    extract_json,
    ar,
    safe,
    build_story_cards,
    build_toc,
    get_categories,
    count_words,
    load_archive,
)


# ────────────────────────────────────────────────────────────────
# Tests: strip_html()
# ────────────────────────────────────────────────────────────────

def test_strip_html_removes_tags():
    """HTML tags should be completely removed."""
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_preserves_text():
    """Non-tagged text should pass through unchanged."""
    assert strip_html("Plain text") == "Plain text"


def test_strip_html_empty_string():
    """Empty string should return empty string."""
    assert strip_html("") == ""


def test_strip_html_none_input():
    """None input should return empty string (safe)."""
    assert strip_html(None) == ""


def test_strip_html_nested_tags():
    """Nested tags should all be removed."""
    html = "<div><span><a href='#'>Link</a></span></div>Text"
    assert strip_html(html) == "LinkText"


def test_strip_html_self_closing_tags():
    """Self-closing tags should be removed."""
    assert strip_html("Line 1<br/>Line 2") == "Line 1Line 2"


def test_strip_html_with_attributes():
    """Tag attributes should be removed with tags."""
    assert strip_html('<p class="intro" id="p1">Content</p>') == "Content"


# ────────────────────────────────────────────────────────────────
# Tests: extract_json()
# ────────────────────────────────────────────────────────────────

def test_extract_json_valid_json():
    """Valid JSON object should be extracted and parsed."""
    text = '{"key": "value"}'
    result = extract_json(text)
    assert result == {"key": "value"}


def test_extract_json_with_markdown_fence():
    """JSON wrapped in markdown code fence should be extracted."""
    text = "```json\n{\"result\": \"success\"}\n```"
    result = extract_json(text)
    assert result == {"result": "success"}


def test_extract_json_with_extra_text():
    """JSON embedded in surrounding text should be extracted."""
    text = "Here is the result:\n```\n{\"status\": \"ok\"}\n```\nEnd of response."
    result = extract_json(text)
    assert result == {"status": "ok"}


def test_extract_json_complex_object():
    """Nested JSON objects should be parsed correctly."""
    json_str = '{"data": [{"id": 1, "name": "test"}], "meta": {"count": 1}}'
    result = extract_json(json_str)
    assert result["data"][0]["name"] == "test"
    assert result["meta"]["count"] == 1


def test_extract_json_escaped_quotes():
    """Escaped quotes in JSON strings should be handled."""
    text = r'{"message": "He said \"hello\""}'
    result = extract_json(text)
    assert 'He said' in result["message"]


def test_extract_json_no_valid_json_raises():
    """Text without valid JSON should raise ValueError."""
    with pytest.raises(ValueError):
        extract_json("Just some text with no JSON")


# ────────────────────────────────────────────────────────────────
# Tests: ar() — Arabic numeral conversion
# ────────────────────────────────────────────────────────────────

def test_ar_single_digit():
    """Single digits should convert to Arabic-Indic numerals."""
    assert ar(0) == "٠"
    assert ar(5) == "٥"
    assert ar(9) == "٩"


def test_ar_multi_digit():
    """Multi-digit numbers should have each digit converted."""
    assert ar(12) == "١٢"
    assert ar(2026) == "٢٠٢٦"


def test_ar_zero():
    """Zero should convert to Arabic zero."""
    assert ar(0) == "٠"


def test_ar_large_number():
    """Large numbers should convert all digits."""
    assert ar(999999) == "٩٩٩٩٩٩"


# ────────────────────────────────────────────────────────────────
# Tests: safe() — HTML escaping
# ────────────────────────────────────────────────────────────────

def test_safe_escapes_ampersand():
    """Ampersands should be escaped."""
    assert safe("Tom & Jerry") == "Tom &amp; Jerry"


def test_safe_escapes_quotes():
    """Quotes should be escaped for HTML attributes."""
    assert safe('He said "hello"') == 'He said &quot;hello&quot;'


def test_safe_escapes_angle_brackets():
    """Angle brackets should be escaped."""
    assert safe("<script>") == "&lt;script&gt;"


def test_safe_escapes_single_quotes():
    """Single quotes should be escaped for attributes."""
    assert safe("It's") == "It&#x27;s"


def test_safe_plain_text():
    """Plain text without special chars should pass through."""
    assert safe("Hello World") == "Hello World"


def test_safe_handles_none():
    """None should be converted to string."""
    result = safe(None)
    assert isinstance(result, str)


# ────────────────────────────────────────────────────────────────
# Tests: get_categories()
# ────────────────────────────────────────────────────────────────

def test_get_categories_empty_digest():
    """Empty digest should return empty list."""
    result = get_categories({})
    assert result == []


def test_get_categories_single_story():
    """Single story with category should be extracted."""
    digest = {
        "global": [{"category": "سياسة"}],
        "local": []
    }
    result = get_categories(digest)
    assert "سياسة" in result


def test_get_categories_deduplication():
    """Duplicate categories should appear only once."""
    digest = {
        "global": [{"category": "أمن"}, {"category": "أمن"}],
        "local": [{"category": "أمن"}]
    }
    result = get_categories(digest)
    assert result.count("أمن") == 1


def test_get_categories_multiple():
    """Multiple categories should all be returned."""
    digest = {
        "global": [{"category": "سياسة"}, {"category": "اقتصاد"}],
        "local": [{"category": "صحة"}]
    }
    result = get_categories(digest)
    assert len(result) == 3


def test_get_categories_sorted():
    """Categories should be returned sorted."""
    digest = {
        "global": [{"category": "ز"}, {"category": "أ"}],
        "local": []
    }
    result = get_categories(digest)
    assert result == sorted(result)


# ────────────────────────────────────────────────────────────────
# Tests: count_words()
# ────────────────────────────────────────────────────────────────

def test_count_words_empty_digest():
    """Empty digest should return 0 words."""
    assert count_words({}) == 0


def test_count_words_single_summary():
    """Single summary should be counted correctly."""
    digest = {
        "global": [{"summary": "One two three"}],
        "local": []
    }
    assert count_words(digest) == 3


def test_count_words_multiple_stories():
    """Words should be counted across all stories."""
    digest = {
        "global": [
            {"summary": "One two"},
            {"summary": "Three four five"}
        ],
        "local": [
            {"summary": "Six"}
        ]
    }
    assert count_words(digest) == 6


def test_count_words_missing_summary():
    """Stories without summary field should not crash."""
    digest = {
        "global": [{"headline": "Test"}],
        "local": []
    }
    # Should not raise; empty string splits to 1 item
    result = count_words(digest)
    assert isinstance(result, int)


# ────────────────────────────────────────────────────────────────
# Tests: build_toc()
# ────────────────────────────────────────────────────────────────

def test_build_toc_empty_digest():
    """Empty digest should produce empty TOC."""
    result = build_toc({})
    assert result == ""


def test_build_toc_single_global_story():
    """Single global story should appear in TOC."""
    digest = {
        "global": [{"headline": "Test Headline"}],
        "local": []
    }
    result = build_toc(digest)
    assert "Test Headline" in result
    assert "الأخبار العالمية" in result


def test_build_toc_single_local_story():
    """Single local story should appear in TOC."""
    digest = {
        "global": [],
        "local": [{"headline": "خبر محلي"}]
    }
    result = build_toc(digest)
    assert "خبر محلي" in result
    assert "أخبار المملكة" in result


def test_build_toc_both_sections():
    """TOC should separate global and local sections."""
    digest = {
        "global": [{"headline": "Global"}],
        "local": [{"headline": "Local"}]
    }
    result = build_toc(digest)
    assert "الأخبار العالمية" in result
    assert "أخبار المملكة" in result
    assert "Global" in result
    assert "Local" in result


def test_build_toc_html_escaping():
    """Headline with special chars should be escaped."""
    digest = {
        "global": [{"headline": 'Test "quoted"'}],
        "local": []
    }
    result = build_toc(digest)
    assert "&quot;" in result


# ────────────────────────────────────────────────────────────────
# Tests: build_story_cards()
# ────────────────────────────────────────────────────────────────

def test_build_story_cards_empty_stories():
    """Empty stories should return empty-state message."""
    result = build_story_cards([], "global")
    assert "لا أستطيع حالياً" in result


def test_build_story_cards_single_story():
    """Single story should generate one card."""
    stories = [{
        "headline": "Test",
        "summary": "Summary text",
        "spin": "Media bias",
        "sources": ["BBC"],
        "category": "سياسة",
        "is_developing": False,
        "context": None,
        "source_count": 1
    }]
    result = build_story_cards(stories, "global")
    assert "Test" in result
    assert "Summary text" in result


def test_build_story_cards_developing_badge():
    """Story with is_developing=True should show badge."""
    stories = [{
        "headline": "Breaking",
        "summary": "Developing story",
        "spin": None,
        "sources": ["Reuters"],
        "category": "أمن",
        "is_developing": True,
        "context": "Previous context",
        "source_count": 1
    }]
    result = build_story_cards(stories, "global")
    assert "متطور" in result
    assert "badge-dev" in result


def test_build_story_cards_top_story_badge():
    """Story with highest source_count should get hot badge."""
    stories = [
        {
            "headline": "Top Story",
            "summary": "Most covered",
            "spin": None,
            "sources": ["BBC", "Reuters", "AP"],
            "category": "سياسة",
            "is_developing": False,
            "context": None,
            "source_count": 3
        },
        {
            "headline": "Other Story",
            "summary": "Less covered",
            "spin": None,
            "sources": ["BBC"],
            "category": "اقتصاد",
            "is_developing": False,
            "context": None,
            "source_count": 1
        }
    ]
    result = build_story_cards(stories, "global")
    assert "الأكثر تداولاً" in result


def test_build_story_cards_no_spin():
    """Story without spin should not show spin section."""
    stories = [{
        "headline": "Test",
        "summary": "No bias detected",
        "spin": None,
        "sources": ["BBC"],
        "category": "صحة",
        "is_developing": False,
        "context": None,
        "source_count": 1
    }]
    result = build_story_cards(stories, "global")
    assert "اكشف التحيز" not in result


def test_build_story_cards_html_escaping():
    """Headline with special chars should be escaped."""
    stories = [{
        "headline": 'Say <"Hello">',
        "summary": "Content & more",
        "spin": None,
        "sources": ["BBC"],
        "category": None,
        "is_developing": False,
        "context": None,
        "source_count": 1
    }]
    result = build_story_cards(stories, "global")
    assert "&lt;" in result and "&gt;" in result
    assert "&amp;" in result


# ────────────────────────────────────────────────────────────────
# Tests: load_archive()
# ────────────────────────────────────────────────────────────────

def test_load_archive_no_directory():
    """Missing archive directory should return empty string."""
    with patch("pathlib.Path.exists", return_value=False):
        result = load_archive()
        assert result == ""


def test_load_archive_empty_directory():
    """Empty archive directory should return empty string."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        with patch("scripts.generate_digest.ROOT_DIR", tmppath):
            result = load_archive()
            assert result == ""


def test_load_archive_single_file():
    """Single archive file should be loaded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        archive_dir = tmppath / "archive"
        archive_dir.mkdir()

        # Create a test archive file
        archive_file = archive_dir / "2026-03-10.json"
        archive_file.write_text(
            json.dumps({
                "global": ["Headline 1", "Headline 2"],
                "local": ["Local Headline"]
            }),
            encoding="utf-8"
        )

        with patch("scripts.generate_digest.ROOT_DIR", tmppath):
            result = load_archive()
            assert "2026-03-10" in result
            assert "Headline 1" in result


def test_load_archive_multiple_files():
    """Multiple files should be loaded in reverse order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        archive_dir = tmppath / "archive"
        archive_dir.mkdir()

        # Create multiple archive files
        for day in range(8, 11):
            archive_file = archive_dir / f"2026-03-{day:02d}.json"
            archive_file.write_text(
                json.dumps({
                    "global": [f"Day {day} Headline"],
                    "local": []
                }),
                encoding="utf-8"
            )

        with patch("scripts.generate_digest.ROOT_DIR", tmppath):
            result = load_archive()
            # Should contain the newest file references
            assert "2026-03-10" in result


def test_load_archive_corrupt_file():
    """Corrupt JSON file should be skipped without crashing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        archive_dir = tmppath / "archive"
        archive_dir.mkdir()

        # Create a corrupt file
        corrupt_file = archive_dir / "2026-03-09.json"
        corrupt_file.write_text("{ invalid json }", encoding="utf-8")

        # Create a valid file
        valid_file = archive_dir / "2026-03-10.json"
        valid_file.write_text(
            json.dumps({"global": ["Valid"], "local": []}),
            encoding="utf-8"
        )

        with patch("scripts.generate_digest.ROOT_DIR", tmppath):
            result = load_archive()
            # Should not crash, should contain valid file
            assert "Valid" in result


def test_load_archive_max_7_days():
    """Should load at most 7 days of history."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        archive_dir = tmppath / "archive"
        archive_dir.mkdir()

        # Create 10 days of files
        for day in range(1, 11):
            archive_file = archive_dir / f"2026-03-{day:02d}.json"
            archive_file.write_text(
                json.dumps({
                    "global": [f"Day {day}"],
                    "local": []
                }),
                encoding="utf-8"
            )

        with patch("scripts.generate_digest.ROOT_DIR", tmppath):
            with patch("scripts.generate_digest.ARCHIVE_DAYS", 7):
                result = load_archive()
                # Should only have the 7 most recent days
                assert result.count("[2026-03-") == 7
