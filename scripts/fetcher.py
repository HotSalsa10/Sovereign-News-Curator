"""RSS feed fetching utilities."""

import concurrent.futures
import logging
import re
import socket

import feedparser

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

ARTICLES_PER_FEED = 3
FEED_TIMEOUT = 10  # seconds per feed request
USER_AGENT = "Sovereign-News-Curator/1.0 (+https://github.com/HotSalsa10/Sovereign-News-Curator)"

GLOBAL_FEEDS = [
    {"name": "BBC World News",        "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Al Jazeera English",    "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "The Guardian World",    "url": "https://www.theguardian.com/world/rss"},
    {"name": "France 24 English",     "url": "https://www.france24.com/en/rss"},
    {"name": "DW World",              "url": "https://rss.dw.com/rdf/rss-en-world"},
    {"name": "NPR World",             "url": "https://feeds.npr.org/1004/rss.xml"},
    {"name": "Reuters World",         "url": "https://feeds.reuters.com/reuters/worldNews"},
    {"name": "Xinhua World",          "url": "http://www.xinhuanet.com/english/rss/worldrss.xml"},
    {"name": "Sky News World",        "url": "https://feeds.skynews.com/feeds/rss/world.xml"},
    {"name": "The Independent World", "url": "https://www.independent.co.uk/news/world/rss"},
    {"name": "NHK World News",        "url": "https://www3.nhk.or.jp/nhkworld/data/en/news/backstory/rss.xml"},
    {"name": "ABC News Australia",    "url": "https://www.abc.net.au/news/feed/10498/rss.xml"},
    {"name": "New York Times World",  "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    {"name": "Fox News World",        "url": "https://moxie.foxnews.com/google-publisher/world.xml"},
    {"name": "CBS News World",        "url": "https://www.cbsnews.com/latest/rss/world"},
]

LOCAL_FEEDS = [
    {"name": "عكاظ",                  "url": "https://www.okaz.com.sa/rss/home.rss"},
    {"name": "الوطن",                 "url": "https://www.alwatan.com.sa/rssFeed/1"},
    {"name": "الجزيرة السعودية",      "url": "https://www.al-jazirah.com/rss/ln.xml"},
    {"name": "مكة",                   "url": "https://makkahnewspaper.com/rssFeed/0"},
]

# ─────────────────────────────────────────────
# FUNCTIONS
# ─────────────────────────────────────────────

def strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text or '').strip()


def fetch_feed(feed: dict[str, str]) -> list[dict[str, str]]:
    try:
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(FEED_TIMEOUT)
        try:
            parsed = feedparser.parse(feed["url"], agent=USER_AGENT)
        finally:
            socket.setdefaulttimeout(old_timeout)
        articles = []
        for entry in parsed.entries[:ARTICLES_PER_FEED]:
            title = strip_html(entry.get("title", "")).strip()
            summary = strip_html(
                entry.get("summary") or
                entry.get("description") or
                (entry.get("content") or [{}])[0].get("value", "")
            )[:250].strip()
            if not title:
                continue
            articles.append({
                "source": feed["name"],
                "title": title,
                "summary": summary or "(No summary)",
            })
        logger.info("[OK]   %s: %d articles", feed["name"], len(articles))
        return articles
    except (OSError, TimeoutError) as e:
        logger.warning("[FAIL] %s: %s", feed["name"], e)
        return []
    except Exception as e:
        logger.error("[FAIL] %s: Unexpected error: %s", feed["name"], e)
        return []


def fetch_all_feeds() -> dict[str, list[dict[str, str]]]:
    total_feeds = len(GLOBAL_FEEDS) + len(LOCAL_FEEDS)
    logger.info("Fetching %d feeds in parallel...", total_feeds)
    all_feeds = [("global", f) for f in GLOBAL_FEEDS] + [("local", f) for f in LOCAL_FEEDS]
    results: dict[str, list[dict[str, str]]] = {"global": [], "local": []}
    with concurrent.futures.ThreadPoolExecutor(max_workers=total_feeds) as executor:
        future_to_cat = {executor.submit(fetch_feed, f): cat for cat, f in all_feeds}
        for future in concurrent.futures.as_completed(future_to_cat):
            results[future_to_cat[future]].extend(future.result())
    logger.info("RSS total: %d global, %d local", len(results["global"]), len(results["local"]))
    return results
