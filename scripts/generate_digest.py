"""
Sovereign News Curator — Daily Digest Generator
Model: claude-sonnet-4-6

Thin re-export shim. Implementation lives in sub-modules:
  fetcher.py       — RSS feed fetching
  archive.py       — Living Context Engine (load/save)
  claude_client.py — Claude API integration
  renderer.py      — HTML generation
  main.py          — Pipeline orchestration
"""

from .fetcher import (  # noqa: F401
    ARTICLES_PER_FEED,
    GLOBAL_FEEDS,
    LOCAL_FEEDS,
    strip_html,
    fetch_feed,
    fetch_all_feeds,
)
from .archive import (  # noqa: F401
    ARCHIVE_DAYS,
    ROOT_DIR,
    load_archive,
    save_archive,
)
from .claude_client import (  # noqa: F401
    MODEL,
    MAX_RETRIES,
    SYSTEM_PROMPT,
    format_for_claude,
    extract_json,
    validate_digest,
    call_claude,
)
from .renderer import (  # noqa: F401
    ar,
    safe,
    build_story_cards,
    build_toc,
    get_categories,
    count_words,
    all_headlines_js,
    build_html,
)
from .main import MIN_ARTICLES, main  # noqa: F401

if __name__ == "__main__":
    main()
