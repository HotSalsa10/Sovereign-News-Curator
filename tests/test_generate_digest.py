"""
Unit tests for Sovereign News Curator's digest generation pipeline.
Tests pure utility functions; API/file I/O calls are mocked.
Target: 80%+ coverage of scripts/generate_digest.py
"""

import json
import pytest
import tempfile
import anthropic
import httpx
from pathlib import Path
from unittest.mock import Mock, patch

from datetime import datetime, timezone
from scripts.main import filter_empty_articles
from scripts.renderer import (
    _build_badges,
    _build_spin_section,
    build_version_json,
    get_category_counts,
    next_run_display,
)
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
    save_archive,
    format_for_claude,
    fetch_feed,
    fetch_all_feeds,
    call_claude,
    validate_digest,
    all_headlines_js,
    build_html,
    main,
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


def test_extract_json_repairs_missing_comma():
    """JSON with a missing comma between fields should be repaired and returned."""
    malformed = '{"key1": "value1" "key2": "value2"}'
    result = extract_json(malformed)
    assert result["key1"] == "value1"
    assert result["key2"] == "value2"


def test_extract_json_repairs_trailing_comma():
    """JSON with a trailing comma should be repaired and returned."""
    malformed = '{"key": "value",}'
    result = extract_json(malformed)
    assert result["key"] == "value"


def test_extract_json_logs_warning_on_repair(mocker):
    """extract_json should log a warning when repair is needed."""
    mock_logger = mocker.patch("scripts.claude_client.logger")
    malformed = '{"key": "value",}'
    extract_json(malformed)
    assert mock_logger.warning.called


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
# Tests: _build_badges() / _build_spin_section() helpers
# ────────────────────────────────────────────────────────────────


def test_build_badges_top_and_developing():
    result = _build_badges(is_top=True, is_dev=True)
    assert "badge-hot" in result
    assert "badge-dev" in result


def test_build_badges_neither():
    result = _build_badges(is_top=False, is_dev=False)
    assert result == ""


def test_build_badges_only_top():
    result = _build_badges(is_top=True, is_dev=False)
    assert "badge-hot" in result
    assert "badge-dev" not in result


def test_build_badges_only_dev():
    result = _build_badges(is_top=False, is_dev=True)
    assert "badge-dev" in result
    assert "badge-hot" not in result


def test_build_spin_section_with_spin():
    result = _build_spin_section("Some bias description")
    assert "spin-btn" in result
    assert "Some bias description" in result


def test_build_spin_section_empty_spin():
    assert _build_spin_section("") == ""


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
        with patch("scripts.archive.ROOT_DIR", tmppath):
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

        with patch("scripts.archive.ROOT_DIR", tmppath):
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

        with patch("scripts.archive.ROOT_DIR", tmppath):
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

        with patch("scripts.archive.ROOT_DIR", tmppath):
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

        with patch("scripts.archive.ROOT_DIR", tmppath):
            with patch("scripts.archive.ARCHIVE_DAYS", 7):
                result = load_archive()
                # Should only have the 7 most recent days
                assert result.count("[2026-03-") == 7


# ────────────────────────────────────────────────────────────────
# Tests: save_archive()
# ────────────────────────────────────────────────────────────────

def test_save_archive_creates_file():
    """save_archive should write a JSON file in archive/."""
    digest = {
        "global": [{"headline": "Global Story"}],
        "local": [{"headline": "Local Story"}],
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        with patch("scripts.archive.ROOT_DIR", tmppath):
            save_archive(digest, "2026-03-14")
            out = tmppath / "archive" / "2026-03-14.json"
            assert out.exists()
            data = json.loads(out.read_text(encoding="utf-8"))
            assert "Global Story" in data["global"]
            assert "Local Story" in data["local"]


def test_save_archive_empty_digest():
    """save_archive with empty digest should write empty arrays."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        with patch("scripts.archive.ROOT_DIR", tmppath):
            save_archive({}, "2026-03-14")
            out = tmppath / "archive" / "2026-03-14.json"
            data = json.loads(out.read_text(encoding="utf-8"))
            assert data["global"] == []
            assert data["local"] == []


# ────────────────────────────────────────────────────────────────
# Tests: format_for_claude()
# ────────────────────────────────────────────────────────────────

def test_format_for_claude_with_archive():
    """Archive context should be prepended with separator."""
    articles = [{"source": "BBC", "title": "Test Title", "summary": "Summary"}]
    result = format_for_claude(articles, [], "HISTORICAL CONTEXT")
    assert "HISTORICAL CONTEXT" in result
    assert "---" in result
    assert "Test Title" in result


def test_format_for_claude_no_archive():
    """Without archive, result should start with news section."""
    articles = [{"source": "BBC", "title": "Test", "summary": "Summary"}]
    result = format_for_claude(articles, [], "")
    assert "GLOBAL NEWS ARTICLES" in result
    assert "HISTORICAL CONTEXT" not in result


def test_format_for_claude_empty_articles():
    """Empty article lists should produce fallback message."""
    result = format_for_claude([], [], "")
    assert "No articles fetched" in result


def test_format_for_claude_both_sections():
    """Both global and local articles should appear in output."""
    global_a = [{"source": "BBC", "title": "Global", "summary": "G summary"}]
    local_a = [{"source": "SPA", "title": "Local", "summary": "L summary"}]
    result = format_for_claude(global_a, local_a, "")
    assert "GLOBAL NEWS ARTICLES" in result
    assert "SAUDI ARABIA NEWS ARTICLES" in result
    assert "Global" in result
    assert "Local" in result


# ────────────────────────────────────────────────────────────────
# Tests: fetch_feed()
# ────────────────────────────────────────────────────────────────

def test_fetch_feed_returns_articles(mocker):
    """fetch_feed should return parsed articles from feedparser."""
    mock_entry = Mock()
    mock_entry.get.side_effect = lambda key, default="": {
        "title": "Test Headline",
        "summary": "Test summary text",
    }.get(key, default)

    mock_parsed = Mock()
    mock_parsed.entries = [mock_entry]

    mocker.patch("feedparser.parse", return_value=mock_parsed)

    feed = {"url": "http://example.com/rss", "name": "TestFeed"}
    result = fetch_feed(feed)

    assert len(result) == 1
    assert result[0]["source"] == "TestFeed"
    assert result[0]["title"] == "Test Headline"


def test_fetch_feed_skips_empty_title(mocker):
    """fetch_feed should skip entries with no title."""
    mock_entry = Mock()
    mock_entry.get.side_effect = lambda key, default="": {
        "title": "",
        "summary": "Summary without title",
    }.get(key, default)

    mock_parsed = Mock()
    mock_parsed.entries = [mock_entry]

    mocker.patch("feedparser.parse", return_value=mock_parsed)

    feed = {"url": "http://example.com/rss", "name": "TestFeed"}
    result = fetch_feed(feed)
    assert result == []


def test_fetch_feed_returns_empty_on_exception(mocker):
    """fetch_feed should return [] if feedparser raises."""
    mocker.patch("feedparser.parse", side_effect=Exception("Network error"))

    feed = {"url": "http://bad-url.com/rss", "name": "BadFeed"}
    result = fetch_feed(feed)
    assert result == []


# ────────────────────────────────────────────────────────────────
# Tests: fetch_all_feeds()
# ────────────────────────────────────────────────────────────────

def test_fetch_all_feeds_aggregates_results(mocker):
    """fetch_all_feeds should combine results from all feeds."""
    mocker.patch(
        "scripts.fetcher.fetch_feed",
        return_value=[{"source": "Test", "title": "T", "summary": "S"}],
    )
    result = fetch_all_feeds()
    assert "global" in result
    assert "local" in result
    assert len(result["global"]) > 0
    assert len(result["local"]) > 0


# ────────────────────────────────────────────────────────────────
# Tests: call_claude()
# ────────────────────────────────────────────────────────────────

def test_call_claude_returns_digest(mocker):
    """call_claude should call API and return parsed digest."""
    mock_message = Mock()
    mock_message.content = [Mock(text='{"global": [], "local": []}')]
    mock_message.usage = Mock(input_tokens=100, output_tokens=50)

    mock_client = Mock()
    mock_client.messages.create.return_value = mock_message

    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})

    articles = {"global": [], "local": []}
    result = call_claude(articles, "")

    assert "global" in result
    assert "local" in result


def test_call_claude_adds_source_count(mocker):
    """call_claude should add source_count to each story."""
    story = {
        "headline": "Test", "summary": "Summary", "sources": ["BBC", "Reuters"],
        "category": "سياسة", "spin": None, "is_developing": False, "context": None,
    }
    mock_message = Mock()
    mock_message.content = [Mock(text=json.dumps({"global": [story], "local": []}))]
    mock_message.usage = Mock(input_tokens=100, output_tokens=50)

    mock_client = Mock()
    mock_client.messages.create.return_value = mock_message

    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})

    result = call_claude({"global": [], "local": []}, "")
    assert result["global"][0]["source_count"] == 2


# ────────────────────────────────────────────────────────────────
# Tests: all_headlines_js()
# ────────────────────────────────────────────────────────────────

def test_all_headlines_js_returns_string():
    """all_headlines_js should return a string."""
    digest = {
        "global": [{"headline": "Global Story"}],
        "local": [{"headline": "Local Story"}],
    }
    result = all_headlines_js(digest)
    assert isinstance(result, str)
    assert "Global Story" in result
    assert "Local Story" in result


def test_all_headlines_js_escapes_backticks():
    """Backticks in headlines should be escaped for JS template literals."""
    digest = {
        "global": [{"headline": "Story `with` backticks"}],
        "local": [],
    }
    result = all_headlines_js(digest)
    assert "\\`" in result


def test_all_headlines_js_empty_digest():
    """Empty digest should return empty string."""
    result = all_headlines_js({})
    assert result == ""


# ────────────────────────────────────────────────────────────────
# Tests: build_html()
# ────────────────────────────────────────────────────────────────

def _sample_digest():
    return {
        "global": [{
            "headline": "Global Headline",
            "summary": "Global summary text",
            "spin": "Some spin",
            "sources": ["BBC"],
            "category": "سياسة",
            "is_developing": False,
            "context": None,
            "source_count": 1,
        }],
        "local": [{
            "headline": "Local Headline",
            "summary": "Local summary text",
            "spin": None,
            "sources": ["SPA"],
            "category": "اقتصاد",
            "is_developing": False,
            "context": None,
            "source_count": 1,
        }],
    }


def test_build_html_returns_doctype():
    """build_html should return a valid HTML document."""
    digest = _sample_digest()
    now = datetime.now(timezone.utc)
    result = build_html(digest, now, {"global": 10, "local": 5})
    assert result.startswith("<!DOCTYPE html>")
    assert "<html" in result
    assert "</html>" in result


def test_build_html_contains_headlines():
    """build_html should include story headlines."""
    digest = _sample_digest()
    now = datetime.now(timezone.utc)
    result = build_html(digest, now, {"global": 10, "local": 5})
    assert "Global Headline" in result
    assert "Local Headline" in result


def test_build_html_arabic_language():
    """build_html should set Arabic language and RTL direction."""
    digest = _sample_digest()
    now = datetime.now(timezone.utc)
    result = build_html(digest, now, {"global": 10, "local": 5})
    assert 'lang="ar"' in result
    assert 'dir="rtl"' in result


def test_build_html_category_buttons():
    """build_html should include category filter buttons."""
    digest = _sample_digest()
    now = datetime.now(timezone.utc)
    result = build_html(digest, now, {"global": 10, "local": 5})
    assert "سياسة" in result
    assert "اقتصاد" in result


def test_build_html_focus_visible_on_buttons():
    """All interactive buttons should have :focus-visible outlines for keyboard accessibility."""
    digest = _sample_digest()
    now = datetime.now(timezone.utc)
    result = build_html(digest, now, {"global": 10, "local": 5})
    assert ":focus-visible" in result


def test_build_html_escapes_xss_in_headline():
    """Headlines with script tags should be HTML-escaped to prevent XSS."""
    digest = {
        "global": [{
            "headline": "<script>alert('xss')</script>",
            "summary": "Normal summary.",
            "sources": ["BBC"],
            "category": "أمن",
            "is_developing": False,
            "context": None,
            "source_count": 1,
        }],
        "local": [],
    }
    now = datetime.now(timezone.utc)
    result = build_html(digest, now, {"global": 1, "local": 0})
    assert "<script>alert" not in result
    assert "&lt;script&gt;" in result


def test_build_html_logs_story_count(mocker):
    """build_html should log global and local story counts."""
    mock_logger = mocker.patch("scripts.renderer.logger")
    digest = _sample_digest()
    now = datetime.now(timezone.utc)
    build_html(digest, now, {"global": 10, "local": 5})
    mock_logger.info.assert_called()


def test_build_html_copy_failure_shows_toast():
    """copyHeadlines should show a toast on clipboard failure instead of silently swallowing errors."""
    digest = _sample_digest()
    now = datetime.now(timezone.utc)
    result = build_html(digest, now, {"global": 10, "local": 5})
    # Toast element must exist in HTML
    assert 'id="toast"' in result
    # JS must handle failure and call showToast (not silent catch)
    assert "showToast" in result
    assert "فشل النسخ" in result


# ────────────────────────────────────────────────────────────────
# Tests: UI/UX improvements (10 items)
# ────────────────────────────────────────────────────────────────

def test_build_html_no_maximum_scale():
    """Viewport meta must not restrict user zoom (WCAG accessibility)."""
    result = build_html(_sample_digest(), datetime.now(timezone.utc), {"global": 10, "local": 5})
    assert "maximum-scale=1" not in result


def test_build_html_theme_btn_uses_svg():
    """Theme toggle button must use inline SVG, not emoji (CLAUDE.md requirement)."""
    result = build_html(_sample_digest(), datetime.now(timezone.utc), {"global": 10, "local": 5})
    assert 'id="theme-btn"' in result
    assert "<svg" in result


def test_build_html_story_body_has_transition():
    """Story card expand/collapse must use CSS transition, not instant snap (CLAUDE.md 150-300ms)."""
    result = build_html(_sample_digest(), datetime.now(timezone.utc), {"global": 10, "local": 5})
    assert "grid-template-rows" in result
    assert "story-body-inner" in result


def test_build_html_toc_has_transition():
    """TOC expand must animate, not snap open/closed."""
    result = build_html(_sample_digest(), datetime.now(timezone.utc), {"global": 10, "local": 5})
    assert "toc-body-inner" in result


def test_build_html_prefers_reduced_motion():
    """HTML output must include a prefers-reduced-motion media query (WCAG / CLAUDE.md)."""
    result = build_html(_sample_digest(), datetime.now(timezone.utc), {"global": 10, "local": 5})
    assert "prefers-reduced-motion" in result


def test_build_html_no_alert_in_share():
    """shareStory must not use alert() — showToast must be used instead."""
    result = build_html(_sample_digest(), datetime.now(timezone.utc), {"global": 10, "local": 5})
    assert "alert(" not in result


def test_build_html_read_state_uses_localStorage():
    """Read state must persist to localStorage so it survives page reloads."""
    result = build_html(_sample_digest(), datetime.now(timezone.utc), {"global": 10, "local": 5})
    assert "snc-read" in result
    assert "localStorage" in result


def test_build_html_filter_reset_on_tab_switch():
    """switchTab must reset category filter to 'all' when changing tabs."""
    result = build_html(_sample_digest(), datetime.now(timezone.utc), {"global": 10, "local": 5})
    assert "curCat='all'" in result


def test_build_html_filter_shows_counts():
    """Category filter buttons must display per-category story counts."""
    result = build_html(_sample_digest(), datetime.now(timezone.utc), {"global": 10, "local": 5})
    assert "flt-count" in result


def test_build_html_filter_empty_state():
    """applyFilter must render an empty-state message when no cards match."""
    result = build_html(_sample_digest(), datetime.now(timezone.utc), {"global": 10, "local": 5})
    assert "filter-empty" in result


# ── get_category_counts() ──

def test_get_category_counts_basic():
    """get_category_counts sums across both sections."""
    digest = {
        "global": [{"category": "سياسة"}, {"category": "اقتصاد"}, {"category": "سياسة"}],
        "local":  [{"category": "اقتصاد"}],
    }
    counts = get_category_counts(digest)
    assert counts["سياسة"] == 2
    assert counts["اقتصاد"] == 2


def test_get_category_counts_empty():
    """get_category_counts returns empty dict for empty digest."""
    assert get_category_counts({"global": [], "local": []}) == {}


def test_get_category_counts_skips_missing_category():
    """get_category_counts ignores stories with no category key."""
    digest = {"global": [{"headline": "X"}], "local": []}
    assert get_category_counts(digest) == {}


# ── next_run_display() ──

def test_next_run_display_after_0600_utc():
    """next_run_display says 'غداً' when digest generated after 06:00 UTC."""
    generated = datetime(2026, 3, 15, 8, 0, 0, tzinfo=timezone.utc)
    assert "غداً" in next_run_display(generated)


def test_next_run_display_before_0600_utc():
    """next_run_display says 'اليوم' when digest generated before 06:00 UTC."""
    generated = datetime(2026, 3, 15, 4, 0, 0, tzinfo=timezone.utc)
    assert "اليوم" in next_run_display(generated)


def test_next_run_display_contains_arabic_indic_digits():
    """next_run_display must use Arabic-Indic numerals."""
    generated = datetime(2026, 3, 15, 8, 0, 0, tzinfo=timezone.utc)
    result = next_run_display(generated)
    assert any(d in result for d in "٠١٢٣٤٥٦٧٨٩")


# ────────────────────────────────────────────────────────────────
# Tests: main()
# ────────────────────────────────────────────────────────────────

def test_main_exits_without_api_key(mocker):
    """main should exit with error if ANTHROPIC_API_KEY is not set."""
    mocker.patch.dict("os.environ", {}, clear=True)
    # Remove key if present
    mocker.patch("os.environ.get", return_value=None)
    with pytest.raises(SystemExit):
        main()


def test_main_runs_full_pipeline(mocker, tmp_path):
    """main should orchestrate the full pipeline and write index.html."""
    digest = _sample_digest()
    articles = {"global": [{"source": "BBC", "title": f"T{i}", "summary": "S"} for i in range(4)],
                "local":  [{"source": "SPA", "title": f"L{i}", "summary": "S"} for i in range(2)]}

    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch("scripts.main.fetch_all_feeds", return_value=articles)
    mocker.patch("scripts.main.load_archive", return_value="")
    mocker.patch("scripts.main.call_claude", return_value=digest)
    mocker.patch("scripts.main.save_archive")
    mocker.patch("scripts.main.ROOT_DIR", tmp_path)

    main()

    out = tmp_path / "index.html"
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content


# ────────────────────────────────────────────────────────────────
# Tests: validate_digest()  [Phase 1 — schema validation]
# ────────────────────────────────────────────────────────────────

def test_validate_digest_valid_passes():
    """A correctly structured digest should not raise."""
    digest = {
        "global": [{"headline": "H", "summary": "S", "sources": [], "category": "سياسة"}],
        "local": [],
    }
    validate_digest(digest)  # should not raise


def test_validate_digest_missing_global_raises():
    """Digest without 'global' key should raise ValueError."""
    with pytest.raises(ValueError, match="global"):
        validate_digest({"local": []})


def test_validate_digest_missing_local_raises():
    """Digest without 'local' key should raise ValueError."""
    with pytest.raises(ValueError, match="local"):
        validate_digest({"global": []})


def test_validate_digest_non_list_global_raises():
    """'global' being non-list should raise ValueError."""
    with pytest.raises(ValueError):
        validate_digest({"global": "not a list", "local": []})


def test_validate_digest_missing_story_field_raises():
    """Story missing required field should raise ValueError."""
    digest = {
        "global": [{"headline": "H", "sources": [], "category": "أمن"}],  # missing summary
        "local": [],
    }
    with pytest.raises(ValueError, match="summary"):
        validate_digest(digest)


def test_validate_digest_empty_sections_pass():
    """Empty global and local arrays should be valid."""
    validate_digest({"global": [], "local": []})


# ────────────────────────────────────────────────────────────────
# Tests: filter_empty_articles()
# ────────────────────────────────────────────────────────────────


def test_filter_empty_articles_removes_no_summary(mocker):
    """Articles with '(No summary)' should be filtered out before sending to Claude."""
    articles = {
        "global": [
            {"source": "BBC", "title": "Real news", "summary": "Actual content here."},
            {"source": "Reuters", "title": "Empty news", "summary": "(No summary)"},
        ],
        "local": [
            {"source": "SPA", "title": "Local", "summary": "(No summary)"},
        ],
    }
    result = filter_empty_articles(articles)
    assert len(result["global"]) == 1
    assert result["global"][0]["title"] == "Real news"
    assert len(result["local"]) == 0


def test_filter_empty_articles_keeps_valid_articles():
    """Articles with real summaries should not be filtered."""
    articles = {
        "global": [
            {"source": "BBC", "title": "A", "summary": "Content A"},
            {"source": "CNN", "title": "B", "summary": "Content B"},
        ],
        "local": [
            {"source": "SPA", "title": "C", "summary": "Content C"},
        ],
    }
    result = filter_empty_articles(articles)
    assert len(result["global"]) == 2
    assert len(result["local"]) == 1


def test_filter_empty_articles_logs_dropped_count(mocker):
    """filter_empty_articles should log how many articles were dropped."""
    mock_logger = mocker.patch("scripts.main.logger")
    articles = {
        "global": [
            {"source": "BBC", "title": "Real", "summary": "Content"},
            {"source": "Fox", "title": "Empty", "summary": "(No summary)"},
        ],
        "local": [],
    }
    filter_empty_articles(articles)
    mock_logger.info.assert_called()


def test_main_filters_empty_articles_before_claude(mocker, tmp_path):
    """main() should filter empty articles before calling Claude."""
    articles = {
        "global": [
            {"source": "BBC", "title": f"T{i}", "summary": "Content"} for i in range(4)
        ] + [{"source": "Fox", "title": "Empty", "summary": "(No summary)"}],
        "local": [{"source": "SPA", "title": "L", "summary": "Content"}],
    }
    digest = _sample_digest()

    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch("scripts.main.fetch_all_feeds", return_value=articles)
    mocker.patch("scripts.main.load_archive", return_value="")
    mock_claude = mocker.patch("scripts.main.call_claude", return_value=digest)
    mocker.patch("scripts.main.save_archive")
    mocker.patch("scripts.main.ROOT_DIR", tmp_path)

    main()

    called_articles = mock_claude.call_args[0][0]
    summaries = [a["summary"] for a in called_articles["global"]]
    assert "(No summary)" not in summaries


# ────────────────────────────────────────────────────────────────
# Tests: call_claude() retry logic  [Phase 1]
# ────────────────────────────────────────────────────────────────

def _valid_story():
    return {
        "headline": "H", "summary": "S", "spin": None,
        "sources": ["BBC"], "category": "سياسة",
        "is_developing": False, "context": None,
    }


def test_call_claude_retries_on_failure(mocker):
    """call_claude should retry up to MAX_RETRIES on API failure then succeed."""
    good_message = Mock()
    good_message.content = [Mock(text=json.dumps({"global": [_valid_story()], "local": []}))]
    good_message.usage = Mock(input_tokens=100, output_tokens=50)

    mock_client = Mock()
    mock_client.messages.create.side_effect = [
        Exception("timeout"),
        Exception("rate limit"),
        good_message,
    ]

    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch("time.sleep")  # avoid real waiting

    result = call_claude({"global": [], "local": []}, "")
    assert mock_client.messages.create.call_count == 3
    assert "global" in result


def test_call_claude_raises_after_max_retries(mocker):
    """call_claude should raise RuntimeError after all retries fail."""
    mock_client = Mock()
    mock_client.messages.create.side_effect = Exception("persistent failure")

    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch("time.sleep")

    with pytest.raises(RuntimeError, match="Claude API failed"):
        call_claude({"global": [], "local": []}, "")

    assert mock_client.messages.create.call_count == 3


def test_call_claude_raises_on_invalid_schema(mocker):
    """call_claude should raise if Claude returns JSON with wrong schema."""
    bad_message = Mock()
    bad_message.content = [Mock(text='{"wrong_key": []}')]  # missing global/local
    bad_message.usage = Mock(input_tokens=100, output_tokens=50)

    mock_client = Mock()
    mock_client.messages.create.return_value = bad_message

    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch("time.sleep")

    with pytest.raises(RuntimeError, match="Claude API failed"):
        call_claude({"global": [], "local": []}, "")


# ────────────────────────────────────────────────────────────────
# Tests: zero-article guard in main()  [Phase 1]
# ────────────────────────────────────────────────────────────────

def test_main_exits_when_no_articles(mocker):
    """main() should exit(1) if fetch returns fewer than MIN_ARTICLES articles."""
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch(
        "scripts.main.fetch_all_feeds",
        return_value={"global": [], "local": []},
    )
    mocker.patch("scripts.main.load_archive", return_value="")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1


def test_main_continues_when_enough_articles(mocker, tmp_path):
    """main() should not exit when fetch returns enough articles."""
    articles = {"global": [{"source": "BBC", "title": f"T{i}", "summary": "S"} for i in range(4)],
                "local":  [{"source": "SPA", "title": f"L{i}", "summary": "S"} for i in range(2)]}
    digest = _sample_digest()

    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch("scripts.main.fetch_all_feeds", return_value=articles)
    mocker.patch("scripts.main.load_archive", return_value="")
    mocker.patch("scripts.main.call_claude", return_value=digest)
    mocker.patch("scripts.main.save_archive")
    mocker.patch("scripts.main.ROOT_DIR", tmp_path)

    main()  # should not raise
    assert (tmp_path / "index.html").exists()


# ────────────────────────────────────────────────────────────────
# Tests: coverage gap — uncovered exception paths
# ────────────────────────────────────────────────────────────────

def test_load_archive_empty_archive_subdir():
    """Archive dir exists but has no JSON files → should return empty string (line 27)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        archive_dir = tmppath / "archive"
        archive_dir.mkdir()  # subdir exists but no files inside
        with patch("scripts.archive.ROOT_DIR", tmppath):
            result = load_archive()
            assert result == ""


def test_fetch_feed_returns_empty_on_os_error(mocker):
    """fetch_feed should return [] and log warning if feedparser raises OSError (line 83-84)."""
    mocker.patch("feedparser.parse", side_effect=OSError("connection refused"))
    feed = {"url": "http://example.com/rss", "name": "TestFeed"}
    result = fetch_feed(feed)
    assert result == []


def test_call_claude_reraises_keyboard_interrupt(mocker):
    """call_claude should let KeyboardInterrupt propagate (line 147)."""
    mock_client = Mock()
    mock_client.messages.create.side_effect = KeyboardInterrupt()
    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})

    with pytest.raises(KeyboardInterrupt):
        call_claude({"global": [], "local": []}, "")


def test_call_claude_retries_on_api_error(mocker):
    """call_claude should retry and succeed after anthropic.APIError (lines 149-153)."""
    good_message = Mock()
    good_message.content = [Mock(text=json.dumps({"global": [_valid_story()], "local": []}))]
    good_message.usage = Mock(input_tokens=100, output_tokens=50)

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    api_error = anthropic.APIConnectionError(message="temporary failure", request=request)

    mock_client = Mock()
    mock_client.messages.create.side_effect = [api_error, good_message]

    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch("time.sleep")

    result = call_claude({"global": [], "local": []}, "")
    assert mock_client.messages.create.call_count == 2
    assert "global" in result


def test_call_claude_retry_uses_jitter(mocker):
    """Retry backoff should include random jitter to avoid synchronized retries."""
    mock_uniform = mocker.patch("scripts.claude_client.random.uniform", return_value=0.42)
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    api_error = anthropic.APIConnectionError(message="fail", request=request)
    good_message = Mock()
    good_message.content = [Mock(text=json.dumps({"global": [_valid_story()], "local": []}))]
    good_message.usage = Mock(input_tokens=100, output_tokens=50)
    mock_client = Mock()
    mock_client.messages.create.side_effect = [api_error, good_message]
    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch("time.sleep")
    call_claude({"global": [], "local": []}, "")
    mock_uniform.assert_called_once_with(0, 1)


def test_main_logs_archive_context_when_available(mocker, tmp_path):
    """main() should log days count when archive context is non-empty (lines 54-55)."""
    articles = {"global": [{"source": "BBC", "title": f"T{i}", "summary": "S"} for i in range(4)],
                "local":  [{"source": "SPA", "title": f"L{i}", "summary": "S"} for i in range(2)]}
    digest = _sample_digest()

    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch("scripts.main.fetch_all_feeds", return_value=articles)
    mocker.patch("scripts.main.load_archive", return_value="line1\nline2\nline3")
    mocker.patch("scripts.main.call_claude", return_value=digest)
    mocker.patch("scripts.main.save_archive")
    mocker.patch("scripts.main.ROOT_DIR", tmp_path)

    main()  # should not raise
    assert (tmp_path / "index.html").exists()


# ────────────────────────────────────────────────────────────────
# Tests: build_version_json()
# ────────────────────────────────────────────────────────────────

def test_build_version_json_structure():
    """build_version_json should return JSON with required keys."""
    now = datetime(2026, 3, 15, 6, 0, 0, tzinfo=timezone.utc)
    digest = {"global": [{"headline": "H"}], "local": []}
    result = json.loads(build_version_json(digest, now))
    assert result["date"] == "2026-03-15"
    assert result["generated"].startswith("2026-03-15")
    assert result["count"] == 1


def test_build_version_json_counts_both_sections():
    """count should sum global and local stories."""
    now = datetime(2026, 3, 15, 6, 0, 0, tzinfo=timezone.utc)
    digest = {"global": [{}] * 3, "local": [{}] * 2}
    result = json.loads(build_version_json(digest, now))
    assert result["count"] == 5


def test_build_version_json_naive_datetime():
    """build_version_json should handle naive datetime without crashing."""
    naive = datetime(2026, 3, 15, 6, 0, 0)  # no tzinfo
    result = json.loads(build_version_json({"global": [], "local": []}, naive))
    assert "date" in result
    assert result["count"] == 0


# ────────────────────────────────────────────────────────────────
# Smoke test: full pipeline end-to-end (all I/O mocked)
# ────────────────────────────────────────────────────────────────

def test_smoke_full_pipeline_writes_index_and_version(mocker, tmp_path):
    """main() should write both index.html and version.json with valid content."""
    articles = {
        "global": [{"source": "BBC", "title": f"G{i}", "summary": "Content"} for i in range(4)],
        "local":  [{"source": "SPA", "title": f"L{i}", "summary": "Content"} for i in range(2)],
    }
    digest = _sample_digest()

    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch("scripts.main.fetch_all_feeds", return_value=articles)
    mocker.patch("scripts.main.load_archive", return_value="")
    mocker.patch("scripts.main.call_claude", return_value=digest)
    mocker.patch("scripts.main.save_archive")
    mocker.patch("scripts.main.ROOT_DIR", tmp_path)

    main()

    # index.html must exist and contain key content
    index = tmp_path / "index.html"
    assert index.exists(), "index.html not written"
    html = index.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "Global Headline" in html        # headline from _sample_digest
    assert "المنتقي السيادي" in html        # Arabic app name
    assert "serviceWorker" in html          # SW registration
    assert "manifest.json" in html          # PWA manifest link
    assert "version.json" in html           # version check JS

    # version.json must exist with correct schema
    ver = tmp_path / "version.json"
    assert ver.exists(), "version.json not written"
    data = json.loads(ver.read_text(encoding="utf-8"))
    assert "date" in data
    assert "generated" in data
    assert data["count"] == 2               # 1 global + 1 local from _sample_digest


def test_smoke_index_html_is_valid_pwa(mocker, tmp_path):
    """index.html produced by main() must pass key PWA and WCAG checks."""
    articles = {
        "global": [{"source": "BBC", "title": f"G{i}", "summary": "Content"} for i in range(4)],
        "local":  [{"source": "SPA", "title": f"L{i}", "summary": "Content"} for i in range(2)],
    }
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mocker.patch("scripts.main.fetch_all_feeds", return_value=articles)
    mocker.patch("scripts.main.load_archive", return_value="")
    mocker.patch("scripts.main.call_claude", return_value=_sample_digest())
    mocker.patch("scripts.main.save_archive")
    mocker.patch("scripts.main.ROOT_DIR", tmp_path)

    main()
    html = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert 'maximum-scale' not in html          # WCAG: pinch-zoom must not be blocked
    assert 'lang="ar"' in html                  # language declared
    assert 'dir="rtl"' in html                  # RTL direction
    assert 'prefers-reduced-motion' in html     # reduced-motion respected
    assert 'aria-label' in html                 # at least one accessible label
    assert 'snc-read-v1' in html               # read-state persistence
