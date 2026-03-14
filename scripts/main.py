"""Orchestration entry point for the daily digest pipeline."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .fetcher import fetch_all_feeds
from .archive import load_archive, save_archive
from .claude_client import call_claude, MODEL
from .renderer import build_html

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

MIN_ARTICLES = 5
ROOT_DIR = Path(__file__).parent.parent

# ─────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────

def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    print("=" * 52)
    print(f"  SOVEREIGN NEWS CURATOR  |  Model: {MODEL}")
    print("=" * 52)

    articles = fetch_all_feeds()

    total_articles = len(articles["global"]) + len(articles["local"])
    if total_articles < MIN_ARTICLES:
        print(f"ERROR: Only {total_articles} articles fetched (minimum {MIN_ARTICLES}). Aborting.")
        sys.exit(1)

    archive_context = load_archive()
    if archive_context:
        days = archive_context.count("\n")
        print(f"\n[Archive] Loaded {days} days of historical context")
    else:
        print("\n[Archive] No historical context yet (first run)")

    digest = call_claude(articles, archive_context)

    now = datetime.now(timezone.utc)
    save_archive(digest, now.strftime("%Y-%m-%d"))

    article_count = {"global": len(articles["global"]), "local": len(articles["local"])}
    html = build_html(digest, now, article_count)

    out = ROOT_DIR / "index.html"
    out.write_text(html, encoding="utf-8")

    g = len(digest.get("global", []))
    local_count = len(digest.get("local", []))
    print("\n[Done] index.html written")
    print(f"       Global stories : {g}")
    print(f"       Local stories  : {local_count}")
    print("=" * 52)


if __name__ == "__main__":
    main()
