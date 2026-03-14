"""Orchestration entry point for the daily digest pipeline."""

import logging
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    logger.info("=" * 52)
    logger.info("  SOVEREIGN NEWS CURATOR  |  Model: %s", MODEL)
    logger.info("=" * 52)

    articles = fetch_all_feeds()

    total_articles = len(articles["global"]) + len(articles["local"])
    if total_articles < MIN_ARTICLES:
        logger.error(
            "Only %d articles fetched (minimum %d). Aborting.",
            total_articles,
            MIN_ARTICLES,
        )
        sys.exit(1)

    archive_context = load_archive()
    if archive_context:
        days = archive_context.count("\n")
        logger.info("Archive: loaded %d days of historical context", days)
    else:
        logger.info("Archive: no historical context yet (first run)")

    digest = call_claude(articles, archive_context)

    now = datetime.now(timezone.utc)
    save_archive(digest, now.strftime("%Y-%m-%d"))

    article_count = {"global": len(articles["global"]), "local": len(articles["local"])}
    html = build_html(digest, now, article_count)

    out = ROOT_DIR / "index.html"
    out.write_text(html, encoding="utf-8")

    g = len(digest.get("global", []))
    local_count = len(digest.get("local", []))
    logger.info("Done. index.html written")
    logger.info("Global stories : %d", g)
    logger.info("Local stories  : %d", local_count)
    logger.info("=" * 52)


if __name__ == "__main__":
    main()
