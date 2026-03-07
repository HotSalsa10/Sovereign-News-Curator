"""
Sovereign News Curator — Daily Digest Generator
Fetches RSS feeds, calls Claude 3.5 Sonnet, outputs index.html
"""

import os
import re
import sys
import concurrent.futures
from datetime import datetime, timezone, timedelta

import feedparser
import anthropic
import markdown as md_lib

# ─────────────────────────────────────────────
# RSS FEED SOURCES (18 total)
# ─────────────────────────────────────────────

GLOBAL_FEEDS = [
    {"name": "BBC World News",       "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Al Jazeera English",   "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "The Guardian World",   "url": "https://www.theguardian.com/world/rss"},
    {"name": "France 24 English",    "url": "https://www.france24.com/en/rss"},
    {"name": "DW World",             "url": "https://rss.dw.com/rdf/rss-en-world"},
    {"name": "NPR World",            "url": "https://feeds.npr.org/1004/rss.xml"},
    {"name": "Reuters World",        "url": "https://feeds.reuters.com/reuters/worldNews"},
    {"name": "AP Top News",          "url": "https://rsshub.app/apnews/topics/apf-topnews"},
    {"name": "Sky News World",       "url": "https://feeds.skynews.com/feeds/rss/world.xml"},
    {"name": "The Independent World","url": "https://www.independent.co.uk/news/world/rss"},
]

LOCAL_FEEDS = [
    {"name": "Arab News",            "url": "https://www.arabnews.com/rss.xml"},
    {"name": "Saudi Gazette",        "url": "https://saudigazette.com.sa/feed"},
    {"name": "Al Arabiya English",   "url": "https://english.alarabiya.net/tools/rss"},
    {"name": "The National",         "url": "https://www.thenationalnews.com/rss"},
    {"name": "Middle East Eye",      "url": "https://www.middleeasteye.net/rss"},
    {"name": "Asharq Al-Awsat",      "url": "https://english.aawsat.com/feed"},
    {"name": "Gulf News Saudi",      "url": "https://gulfnews.com/rss/world/gulf/saudi-arabia"},
    {"name": "Al-Monitor",           "url": "https://www.al-monitor.com/rss"},
]

ARTICLES_PER_FEED = 5  # 18 feeds × 5 = up to 90 articles

# ─────────────────────────────────────────────
# CLAUDE SYSTEM PROMPT (from CLAUDE.md spec)
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """<language>
IMPORTANT: You must write your ENTIRE response in Arabic (العربية). All headlines, summaries, and spin analysis must be in Arabic. Do not use English in the output.
</language>

<role>
You are the Sovereign News Curator, an elite, highly defensive AI reading agent. Your directive is to protect the user from cognitive exploitation while delivering a pure, verified signal.
</role>

<context>
The user requires a finite digest of the day's events, strictly separated into two views: Global News and Local News. You will receive multiple articles covering the same events. You must extract the undeniable consensus and explicitly separate it from ideological spin.
</context>

<task>
1. Categorization: Sort the provided articles into "Global News" and "Local News" based on their scope.
2. Semantic Deduplication: Combine repetitive stories into a single event summary within their category.
3. Consensus Extraction: Isolate the undeniable, overlapping facts reported by credible sources.
4. Spin Identification: Briefly note the ideological framing used by specific outlets.
5. De-sensationalization: Strip all clickbait and fear-inducing language.
</task>

<constraints>
- STRICT NEGATIVE CONSTRAINT: Do NOT hallucinate quotes, dates, or URLs.
- STRICT NEGATIVE CONSTRAINT: You must output exactly two main sections: Global News and Local News.
- ESCAPE HATCH: If the input data for a category is empty or entirely contradictory, output in Arabic: "لا أستطيع حالياً تحديد توافق حقيقي لهذه الفئة اليوم."
</constraints>

<response_format>
Format your output in clean Markdown, fully in Arabic:

# الملخص السيادي اليومي

## المشهد الأول: الأخبار العالمية
* **[عنوان منزوع الإثارة]:** [ملخص لا يتجاوز ثلاث جمل للحقائق الموثقة.]
  * *التلاعب الإعلامي:* [جملة واحدة توضح كيف أطّرت وسائل إعلام مختلفة القصة.]

## المشهد الثاني: أخبار المملكة العربية السعودية
* **[عنوان منزوع الإثارة]:** [ملخص لا يتجاوز ثلاث جمل للحقائق المحلية الموثقة.]
  * *التلاعب الإعلامي:* [جملة واحدة عن التأطير إن وُجد.]

---
*انتهى البث. أنت الآن مطّلع.*
</response_format>"""

# ─────────────────────────────────────────────
# RSS FETCHING
# ─────────────────────────────────────────────

def strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r'<[^>]+>', '', text or '').strip()


def fetch_feed(feed: dict) -> list[dict]:
    """Fetch and parse a single RSS feed. Returns list of article dicts."""
    try:
        parsed = feedparser.parse(feed["url"])
        articles = []
        for entry in parsed.entries[:ARTICLES_PER_FEED]:
            title = strip_html(entry.get("title", "")).strip()
            summary = strip_html(
                entry.get("summary") or
                entry.get("description") or
                (entry.get("content") or [{}])[0].get("value", "")
            )[:500].strip()

            if not title:
                continue

            articles.append({
                "source": feed["name"],
                "title": title,
                "summary": summary or "(No summary available)",
            })
        print(f"  [OK]   {feed['name']}: {len(articles)} articles")
        return articles
    except Exception as e:
        print(f"  [FAIL] {feed['name']}: {e}")
        return []


def fetch_all_feeds() -> dict:
    """Fetch all feeds in parallel. Returns {'global': [...], 'local': [...]}"""
    print(f"\n[RSS] Fetching {len(GLOBAL_FEEDS) + len(LOCAL_FEEDS)} feeds in parallel...")

    all_feeds = [("global", f) for f in GLOBAL_FEEDS] + [("local", f) for f in LOCAL_FEEDS]

    results = {"global": [], "local": []}
    with concurrent.futures.ThreadPoolExecutor(max_workers=18) as executor:
        future_to_meta = {
            executor.submit(fetch_feed, feed): category
            for category, feed in all_feeds
        }
        for future in concurrent.futures.as_completed(future_to_meta):
            category = future_to_meta[future]
            results[category].extend(future.result())

    print(f"\n[RSS] Total: {len(results['global'])} global articles, {len(results['local'])} local articles")
    return results


# ─────────────────────────────────────────────
# CLAUDE API
# ─────────────────────────────────────────────

def format_for_claude(global_articles: list, local_articles: list) -> str:
    """Format articles into a structured prompt for Claude."""
    def section(articles, label):
        if not articles:
            return f"### {label}\n(No articles fetched from feeds)"
        lines = [f"### {label}"]
        for a in articles:
            lines.append(f"**[{a['source']}]** {a['title']}\n{a['summary']}")
        return "\n\n".join(lines)

    return "\n\n---\n\n".join([
        section(global_articles, "GLOBAL NEWS ARTICLES"),
        section(local_articles, "SAUDI ARABIA NEWS ARTICLES"),
    ])


def call_claude(articles: dict) -> str:
    """Send articles to Claude 3.5 Sonnet and return the markdown digest."""
    print(f"\n[Claude] Calling claude-3-5-sonnet-20241022...")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_content = format_for_claude(articles["global"], articles["local"])

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    digest = message.content[0].text
    print(f"[Claude] Done. Tokens used — input: {message.usage.input_tokens}, output: {message.usage.output_tokens}")
    return digest


# ─────────────────────────────────────────────
# HTML GENERATION
# ─────────────────────────────────────────────

def build_html(digest_md: str, generated_at: datetime, article_count: dict) -> str:
    """Convert markdown digest to a full, self-contained HTML page."""
    digest_html = md_lib.markdown(digest_md, extensions=["extra"])

    # Saudi time = UTC+3
    saudi_time = generated_at.astimezone(timezone(timedelta(hours=3)))
    time_str = saudi_time.strftime("%A, %B %d, %Y · %I:%M %p (AST)").replace(" 0", " ")
    next_run = "غداً الساعة 9:00 صباحاً (بتوقيت السعودية)"
    total_articles = article_count["global"] + article_count["local"]

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <meta name="apple-mobile-web-app-title" content="المنتقي السيادي" />
  <meta name="theme-color" content="#0a0a0a" />
  <title>المنتقي السيادي للأخبار</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: 'Cairo', 'Segoe UI', Tahoma, Arial, sans-serif;
      background: #0a0a0a;
      color: #e4e4e7;
      min-height: 100vh;
      padding: 0 0 60px;
      -webkit-font-smoothing: antialiased;
      direction: rtl;
    }}

    /* ── Header ── */
    .header {{
      padding: 48px 20px 0;
      max-width: 680px;
      margin: 0 auto;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      color: #52525b;
      margin-bottom: 12px;
    }}
    .badge-dot {{
      width: 6px; height: 6px;
      border-radius: 50%;
      background: #34d399;
      animation: pulse 2s ease-in-out infinite;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.4; }}
    }}
    h1.app-title {{
      font-size: clamp(22px, 5vw, 28px);
      font-weight: 700;
      color: #fafafa;
      line-height: 1.3;
    }}
    .app-subtitle {{
      color: #71717a;
      font-size: 13px;
      margin-top: 6px;
    }}

    /* ── Meta bar ── */
    .meta-bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
      max-width: 680px;
      margin: 24px auto 12px;
      padding: 0 20px;
      font-size: 11px;
      color: #52525b;
    }}
    .meta-bar span {{ color: #71717a; }}

    /* ── Card ── */
    .card {{
      background: #111113;
      border: 1px solid #1f1f23;
      border-radius: 16px;
      padding: 28px 24px;
      max-width: 680px;
      margin: 0 20px;
    }}
    @media (min-width: 720px) {{
      .card {{
        margin: 0 auto;
        padding: 36px 40px;
      }}
    }}

    /* ── Digest content ── */
    .digest h1 {{
      font-size: 18px;
      font-weight: 700;
      color: #fafafa;
      padding-bottom: 16px;
      border-bottom: 1px solid #27272a;
      margin-bottom: 24px;
    }}
    .digest h2 {{
      font-size: 13px;
      font-weight: 600;
      color: #60a5fa;
      margin: 32px 0 16px;
    }}
    .digest ul {{
      list-style: none;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }}
    .digest li {{
      font-size: 15px;
      line-height: 1.9;
      color: #d4d4d8;
      padding-right: 14px;
      border-right: 2px solid #27272a;
    }}
    .digest li ul {{
      margin-top: 8px;
      gap: 4px;
    }}
    .digest li ul li {{
      font-size: 13px;
      color: #71717a;
      border-right: none;
      padding-right: 0;
    }}
    .digest strong {{ color: #fafafa; font-weight: 600; }}
    .digest em {{ color: #71717a; font-size: 13px; }}
    .digest hr {{
      border: none;
      border-top: 1px solid #1f1f23;
      margin: 32px 0;
    }}
    .digest p {{
      font-size: 12px;
      color: #3f3f46;
      text-align: center;
      margin-top: 24px;
    }}

    /* ── Footer ── */
    .footer {{
      text-align: center;
      margin-top: 24px;
      font-size: 11px;
      color: #3f3f46;
      padding: 0 20px;
    }}
    .footer a {{
      color: #52525b;
      text-decoration: none;
    }}
    .footer a:hover {{ color: #71717a; }}
  </style>
</head>
<body>

  <div class="header">
    <div class="badge">
      <span class="badge-dot"></span>
      درع الحماية المعرفية
    </div>
    <h1 class="app-title">المنتقي السيادي للأخبار</h1>
    <p class="app-subtitle">منزوع الإثارة · مزال التكرار · محمي من التلاعب</p>
  </div>

  <div class="meta-bar">
    <span>{time_str}</span>
    <span>تمت معالجة {total_articles} مقالاً</span>
  </div>

  <div class="card">
    <div class="digest">
      {digest_html}
    </div>
  </div>

  <div class="footer" style="margin-top: 20px;">
    التحديث القادم: {next_run}
    &nbsp;·&nbsp;
    <a href="https://github.com/HotSalsa10/Sovereign-News-Curator/actions" target="_blank">تشغيل يدوي ↗</a>
  </div>

</body>
</html>"""


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    print("=" * 50)
    print("  SOVEREIGN NEWS CURATOR — Digest Generator")
    print("=" * 50)

    # 1. Fetch RSS
    articles = fetch_all_feeds()

    if not articles["global"] and not articles["local"]:
        print("\nERROR: No articles fetched from any feed. Check your internet connection.")
        sys.exit(1)

    # 2. Call Claude
    digest_md = call_claude(articles)

    # 3. Build HTML
    now = datetime.now(timezone.utc)
    article_count = {
        "global": len(articles["global"]),
        "local": len(articles["local"]),
    }
    html = build_html(digest_md, now, article_count)

    # 4. Write output
    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n[Done] Digest written to {output_path}")
    print(f"       Global: {article_count['global']} articles")
    print(f"       Local:  {article_count['local']} articles")
    print("=" * 50)


if __name__ == "__main__":
    main()
