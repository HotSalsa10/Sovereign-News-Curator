"""RSS feed fetching utilities."""

import concurrent.futures
import re

import feedparser

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

ARTICLES_PER_FEED = 3

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
    {"name": "Arab News",             "url": "https://www.arabnews.com/rss.xml"},
    {"name": "Saudi Gazette",         "url": "https://saudigazette.com.sa/feed"},
    {"name": "Al Arabiya English",    "url": "https://english.alarabiya.net/tools/rss"},
    {"name": "The National",          "url": "https://www.thenationalnews.com/rss"},
    {"name": "Middle East Eye",       "url": "https://www.middleeasteye.net/rss"},
    {"name": "Asharq Al-Awsat",       "url": "https://english.aawsat.com/feed"},
    {"name": "Gulf News Saudi",       "url": "https://gulfnews.com/rss/world/gulf/saudi-arabia"},
    {"name": "Al-Monitor",            "url": "https://www.al-monitor.com/rss"},
]

# ─────────────────────────────────────────────
# FUNCTIONS
# ─────────────────────────────────────────────

def strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text or '').strip()


def fetch_feed(feed: dict) -> list[dict]:
    try:
        parsed = feedparser.parse(feed["url"])
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
        print(f"  [OK]   {feed['name']}: {len(articles)} articles")
        return articles
    except Exception as e:
        print(f"  [FAIL] {feed['name']}: {e}")
        return []


def fetch_all_feeds() -> dict:
    print(f"\n[RSS] Fetching {len(GLOBAL_FEEDS) + len(LOCAL_FEEDS)} feeds in parallel...")
    all_feeds = [("global", f) for f in GLOBAL_FEEDS] + [("local", f) for f in LOCAL_FEEDS]
    results: dict[str, list] = {"global": [], "local": []}
    with concurrent.futures.ThreadPoolExecutor(max_workers=23) as executor:
        future_to_cat = {executor.submit(fetch_feed, f): cat for cat, f in all_feeds}
        for future in concurrent.futures.as_completed(future_to_cat):
            results[future_to_cat[future]].extend(future.result())
    print(f"\n[RSS] Total: {len(results['global'])} global, {len(results['local'])} local")
    return results
