"""
Sovereign News Curator — Daily Digest Generator
Model: claude-sonnet-4-6
"""

import os, re, sys, json, concurrent.futures, html as html_lib
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import anthropic

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
ARTICLES_PER_FEED = 3
ARCHIVE_DAYS = 3
ROOT_DIR = Path(__file__).parent.parent

GLOBAL_FEEDS = [
    {"name": "BBC World News",        "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Al Jazeera English",    "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "The Guardian World",    "url": "https://www.theguardian.com/world/rss"},
    {"name": "France 24 English",     "url": "https://www.france24.com/en/rss"},
    {"name": "DW World",              "url": "https://rss.dw.com/rdf/rss-en-world"},
    {"name": "NPR World",             "url": "https://feeds.npr.org/1004/rss.xml"},
    {"name": "Reuters World",         "url": "https://feeds.reuters.com/reuters/worldNews"},
    {"name": "AP Top News",           "url": "https://rsshub.app/apnews/topics/apf-topnews"},
    {"name": "Sky News World",        "url": "https://feeds.skynews.com/feeds/rss/world.xml"},
    {"name": "The Independent World", "url": "https://www.independent.co.uk/news/world/rss"},
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
# SYSTEM PROMPT
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are the Sovereign News Curator. Extract consensus facts only. Output ONLY valid JSON.

TASKS: (1) Deduplicate articles covering same events (2) Consensus facts only, no hallucinations (3) Detect media spin (4) Flag developing stories using historical context

OUTPUT: Valid JSON with global/local arrays. Each story: headline (Arabic), summary (3 sent max), spin (1 sent), sources (list), category (سياسة|اقتصاد|أمن|صحة|تقنية|بيئة|مجتمع), is_developing (bool), context (Arabic or null).

RULES: Empty section = []. All Arabic text in headline/summary/spin/context/category. No hallucinated quotes/dates/URLs. context=null for new stories."""

# ─────────────────────────────────────────────
# RSS FETCHING
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
    results = {"global": [], "local": []}
    with concurrent.futures.ThreadPoolExecutor(max_workers=18) as executor:
        future_to_cat = {executor.submit(fetch_feed, f): cat for cat, f in all_feeds}
        for future in concurrent.futures.as_completed(future_to_cat):
            results[future_to_cat[future]].extend(future.result())
    print(f"\n[RSS] Total: {len(results['global'])} global, {len(results['local'])} local")
    return results

# ─────────────────────────────────────────────
# ARCHIVE (Living Context Engine)
# ─────────────────────────────────────────────

def load_archive() -> str:
    archive_dir = ROOT_DIR / "archive"
    if not archive_dir.exists():
        return ""
    files = sorted(archive_dir.glob("*.json"), reverse=True)[:ARCHIVE_DAYS]
    if not files:
        return ""
    lines = ["HISTORICAL CONTEXT — story headlines from the past 7 days (use this to detect developing stories and add context):"]
    for f in reversed(files):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            date = f.stem
            g = " / ".join(data.get("global", [])[:6])
            l = " / ".join(data.get("local", [])[:4])
            lines.append(f"[{date}] Global: {g} | Saudi: {l}")
        except Exception:
            pass
    return "\n".join(lines)


def save_archive(digest: dict, date_str: str):
    archive_dir = ROOT_DIR / "archive"
    archive_dir.mkdir(exist_ok=True)
    data = {
        "global": [s.get("headline", "") for s in digest.get("global", [])],
        "local":  [s.get("headline", "") for s in digest.get("local", [])],
    }
    out = archive_dir / f"{date_str}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Archive] Saved → {out.name}")

# ─────────────────────────────────────────────
# CLAUDE
# ─────────────────────────────────────────────

def format_for_claude(global_articles: list, local_articles: list, archive_context: str) -> str:
    def section(articles, label):
        if not articles:
            return f"### {label}\n(No articles fetched from feeds)"
        return f"### {label}\n" + "\n\n".join(
            f"**[{a['source']}]** {a['title']}\n{a['summary']}" for a in articles
        )
    parts = []
    if archive_context:
        parts += [archive_context, "---"]
    parts += [
        section(global_articles, "GLOBAL NEWS ARTICLES"),
        "---",
        section(local_articles, "SAUDI ARABIA NEWS ARTICLES"),
    ]
    return "\n\n".join(parts)


def extract_json(text: str) -> dict:
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text.strip(), flags=re.MULTILINE)
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON in Claude response")


def call_claude(articles: dict, archive_context: str) -> dict:
    print(f"\n[Claude] Calling {MODEL}...")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    user_content = format_for_claude(articles["global"], articles["local"], archive_context)
    message = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = message.content[0].text
    print(f"[Claude] Done. Tokens — input: {message.usage.input_tokens}, output: {message.usage.output_tokens}")
    digest = extract_json(raw)
    for section_key in ("global", "local"):
        for story in digest.get(section_key, []):
            story["source_count"] = len(story.get("sources", []))
    return digest

# ─────────────────────────────────────────────
# HTML HELPERS
# ─────────────────────────────────────────────

def ar(n: int) -> str:
    """Convert integer to Arabic-Indic numerals."""
    eastern = "٠١٢٣٤٥٦٧٨٩"
    return "".join(eastern[int(d)] for d in str(n))


def safe(text: str) -> str:
    """HTML-escape a string for use in attributes."""
    return html_lib.escape(str(text or ""), quote=True)


def build_story_cards(stories: list, section_id: str) -> str:
    if not stories:
        return '<p class="empty-state">لا أستطيع حالياً تحديد توافق حقيقي لهذه الفئة اليوم.</p>'

    max_sources = max((s.get("source_count", 0) for s in stories), default=0)
    cards = []

    for i, story in enumerate(stories):
        headline    = story.get("headline", "")
        summary     = story.get("summary", "")
        spin        = story.get("spin", "")
        sources     = story.get("sources", [])
        category    = story.get("category", "")
        is_dev      = story.get("is_developing", False)
        context     = story.get("context") or ""
        source_count = story.get("source_count", 0)
        is_top      = source_count == max_sources and max_sources > 1

        badges = ""
        if is_top:
            badges += '<span class="badge badge-hot">الأكثر تداولاً</span>'
        if is_dev:
            badges += '<span class="badge badge-dev">متطور</span>'

        source_pills = "".join(f'<span class="src-pill">{safe(s)}</span>' for s in sources)
        context_html = f'<div class="story-context">{safe(context)}</div>' if context else ""
        spin_html = (
            f'<div class="spin-wrap">'
            f'<button class="spin-btn" onclick="toggleSpin(this)">اكشف التحيز الإعلامي</button>'
            f'<div class="spin-body" hidden>'
            f'<span class="spin-label">التلاعب الإعلامي: </span>{safe(spin)}'
            f'</div></div>'
        ) if spin else ""

        cards.append(f"""
<div class="story-card" data-cat="{safe(category)}" data-headline="{safe(headline)}" data-summary="{safe(summary[:150])}">
  <div class="story-hdr" onclick="toggleStory(this)">
    <div class="story-meta">
      <span class="story-num">#{ar(i+1)}</span>
      {f'<span class="cat-tag">{safe(category)}</span>' if category else ""}
      {badges}
    </div>
    <h3 class="story-title">{safe(headline)}</h3>
    {f'<div class="src-pills">{source_pills}</div>' if source_pills else ""}
    <span class="expand-icon" aria-hidden="true">+</span>
  </div>
  <div class="story-body" hidden>
    {context_html}
    <p class="story-summary">{safe(summary)}</p>
    {spin_html}
    <div class="story-actions">
      <button class="share-btn" onclick="shareStory(this)">مشاركة ↗</button>
    </div>
  </div>
</div>""")

    return "\n".join(cards)


def build_toc(digest: dict) -> str:
    lines = []
    for section_key, label in [("global", "الأخبار العالمية"), ("local", "أخبار المملكة")]:
        stories = digest.get(section_key, [])
        if not stories:
            continue
        lines.append(f'<p class="toc-label">{label}</p>')
        for i, s in enumerate(stories):
            lines.append(
                f'<a class="toc-item" data-section="{section_key}" data-index="{i}" '
                f'onclick="jumpToStory(this);return false;" href="#">'
                f'#{ar(i+1)} {safe(s.get("headline",""))}</a>'
            )
    return "\n".join(lines)


def get_categories(digest: dict) -> list:
    cats = set()
    for sk in ("global", "local"):
        for s in digest.get(sk, []):
            if s.get("category"):
                cats.add(s["category"])
    return sorted(cats)


def count_words(digest: dict) -> int:
    words = 0
    for sk in ("global", "local"):
        for s in digest.get(sk, []):
            words += len(s.get("summary", "").split())
    return words


def all_headlines_js(digest: dict) -> str:
    lines = []
    for i, s in enumerate(digest.get("global", []), 1):
        lines.append(f"{i}. {s.get('headline','')}")
    for i, s in enumerate(digest.get("local", []), 1):
        lines.append(f"{i}. {s.get('headline','')}")
    # Escape for JS template literal
    return "\\n".join(lines).replace("`", "\\`")

# ─────────────────────────────────────────────
# HTML BUILD
# ─────────────────────────────────────────────

def build_html(digest: dict, generated_at: datetime, article_count: dict) -> str:
    saudi_tz  = timezone(timedelta(hours=3))
    saudi_now = generated_at.astimezone(saudi_tz)
    iso       = generated_at.isoformat()
    display   = saudi_now.strftime("%d/%m/%Y · %I:%M %p")

    global_stories = digest.get("global", [])
    local_stories  = digest.get("local",  [])
    g_count = len(global_stories)
    l_count = len(local_stories)
    total   = article_count["global"] + article_count["local"]

    words   = count_words(digest)
    read_min = max(1, round(words / 120))

    global_cards = build_story_cards(global_stories, "global")
    local_cards  = build_story_cards(local_stories,  "local")
    toc_html     = build_toc(digest)
    categories   = get_categories(digest)
    headlines_js = all_headlines_js(digest)

    cat_btns = '<button class="flt-btn active" data-cat="all" onclick="filterCat(this)">الكل</button>'
    for c in categories:
        cat_btns += f'<button class="flt-btn" data-cat="{safe(c)}" onclick="filterCat(this)">{safe(c)}</button>'

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"/>
  <meta name="apple-mobile-web-app-capable" content="yes"/>
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"/>
  <meta name="apple-mobile-web-app-title" content="المنتقي"/>
  <meta name="theme-color" content="#0a0a0a" id="theme-meta"/>
  <link rel="apple-touch-icon" href="icon-180.png"/>
  <link rel="manifest" href="manifest.json"/>
  <title>المنتقي السيادي للأخبار</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>
  <style>
    :root{{
      --bg:#0a0a0a;--bg2:#111113;--bg3:#18181b;
      --bd:#27272a;--bd2:#1f1f23;
      --t1:#f4f4f5;--t2:#a1a1aa;--t3:#52525b;
      --blue:#3b82f6;--blue-d:#1d3b6e;
      --green:#10b981;--green-d:#064e3b;
      --amber:#f59e0b;--amber-d:#292203;
      --r:12px;
    }}
    .light{{
      --bg:#f4f4f5;--bg2:#fff;--bg3:#e4e4e7;
      --bd:#d4d4d8;--bd2:#e4e4e7;
      --t1:#09090b;--t2:#52525b;--t3:#a1a1aa;
      --blue-d:#dbeafe;--green-d:#d1fae5;--amber-d:#fef3c7;
    }}
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    html{{scroll-behavior:smooth}}
    body{{
      font-family:'Cairo','Segoe UI',Tahoma,Arial,sans-serif;
      background:var(--bg);color:var(--t1);
      min-height:100vh;direction:rtl;
      -webkit-font-smoothing:antialiased;
      transition:background .2s,color .2s;
    }}

    /* ── HEADER ── */
    .hdr{{
      position:sticky;top:0;z-index:100;
      background:var(--bg);border-bottom:1px solid var(--bd2);
      backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
    }}
    .hdr-top{{
      display:flex;align-items:center;justify-content:space-between;
      padding:12px 16px 0;max-width:700px;margin:0 auto;
    }}
    .app-name{{font-size:17px;font-weight:800;color:var(--t1);line-height:1}}
    .hdr-meta{{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--t3);margin-top:3px}}
    .dot{{width:6px;height:6px;border-radius:50%;display:inline-block;flex-shrink:0}}
    .icon-btn{{
      background:var(--bg3);border:1px solid var(--bd);color:var(--t2);
      border-radius:8px;padding:6px 10px;font-size:13px;cursor:pointer;
      font-family:inherit;transition:all .15s;
    }}
    .icon-btn:hover{{color:var(--t1);border-color:var(--t2)}}

    /* ── TABS ── */
    .tabs{{display:flex;gap:6px;padding:8px 16px;max-width:700px;margin:0 auto}}
    .tab{{
      flex:1;padding:8px;border-radius:8px;border:1px solid var(--bd);
      background:transparent;color:var(--t2);font-family:inherit;
      font-size:13px;font-weight:700;cursor:pointer;transition:all .15s;
    }}
    .tab.on{{background:var(--blue);border-color:var(--blue);color:#fff}}
    .tab.on.local{{background:var(--green);border-color:var(--green)}}

    /* ── CONTENT ── */
    .main{{max-width:700px;margin:0 auto;padding:12px 16px 80px}}

    /* ── DIGEST META ── */
    .dmeta{{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}}
    .dmeta-txt{{font-size:12px;color:var(--t3)}}
    .copy-btn{{
      font-size:11px;padding:5px 10px;background:var(--bg3);
      border:1px solid var(--bd);color:var(--t2);border-radius:6px;
      cursor:pointer;font-family:inherit;transition:all .15s;
    }}
    .copy-btn:hover{{color:var(--t1)}}

    /* ── TOC ── */
    .toc-wrap{{background:var(--bg2);border:1px solid var(--bd2);border-radius:var(--r);margin-bottom:10px;overflow:hidden}}
    .toc-toggle{{
      width:100%;background:none;border:none;padding:12px 16px;
      display:flex;align-items:center;justify-content:space-between;
      font-family:inherit;font-size:13px;font-weight:700;color:var(--t2);cursor:pointer;
    }}
    .toc-body{{padding:0 16px 12px;display:none}}
    .toc-body.open{{display:block}}
    .toc-label{{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--t3);margin:10px 0 4px}}
    .toc-item{{
      display:block;font-size:13px;color:var(--t2);padding:5px 0;
      text-decoration:none;border-bottom:1px solid var(--bd2);
      transition:color .1s;cursor:pointer;
    }}
    .toc-item:hover{{color:var(--blue)}}
    .toc-item:last-child{{border:none}}

    /* ── FILTERS ── */
    .filters{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}}
    .flt-btn{{
      padding:5px 12px;border-radius:20px;border:1px solid var(--bd);
      background:transparent;color:var(--t2);font-size:12px;
      font-family:inherit;cursor:pointer;transition:all .15s;
    }}
    .flt-btn.active{{background:var(--blue);border-color:var(--blue);color:#fff}}

    /* ── SECTION ── */
    .sec{{display:none}}.sec.on{{display:block}}
    .sec-hdr{{display:flex;align-items:center;gap:8px;margin:16px 0 10px}}
    .sec-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
    .sec-dot.g{{background:var(--blue)}}.sec-dot.l{{background:var(--green)}}
    .sec-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--t2)}}
    .sec-count{{font-size:11px;color:var(--t3);margin-right:auto}}

    /* ── STORY CARD ── */
    .story-card{{
      background:var(--bg2);border:1px solid var(--bd2);
      border-radius:var(--r);margin-bottom:8px;overflow:hidden;
      transition:border-color .15s,opacity .3s;
    }}
    .story-card.read{{opacity:.55}}
    .story-card[hidden]{{display:none!important}}

    .story-hdr{{
      padding:14px 16px;cursor:pointer;position:relative;
      user-select:none;-webkit-user-select:none;
    }}
    .story-meta{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px}}
    .story-num{{font-size:11px;color:var(--t3);font-weight:700}}
    .cat-tag{{font-size:10px;padding:2px 8px;border-radius:10px;background:var(--blue-d);color:var(--blue);font-weight:600}}
    .badge{{font-size:10px;padding:2px 8px;border-radius:10px;font-weight:600}}
    .badge-hot{{background:var(--amber-d);color:var(--amber)}}
    .badge-dev{{background:var(--green-d);color:var(--green)}}
    .story-title{{font-size:15px;font-weight:700;color:var(--t1);line-height:1.55;margin-bottom:8px;padding-left:22px}}
    .src-pills{{display:flex;flex-wrap:wrap;gap:4px}}
    .src-pill{{font-size:10px;padding:2px 6px;border-radius:4px;background:var(--bg3);color:var(--t3);border:1px solid var(--bd)}}
    .expand-icon{{position:absolute;left:14px;top:14px;font-size:20px;color:var(--t3);font-weight:300;transition:transform .2s;line-height:1}}
    .story-hdr.open .expand-icon{{transform:rotate(45deg)}}

    /* ── STORY BODY ── */
    .story-body{{padding:0 16px 14px;border-top:1px solid var(--bd2)}}
    .story-context{{
      font-size:12px;color:var(--green);background:var(--green-d);
      padding:8px 12px;border-radius:8px;margin:12px 0 10px;line-height:1.7;
    }}
    .story-summary{{font-size:14px;line-height:2;color:var(--t1);margin:12px 0 10px}}

    /* ── SPIN ── */
    .spin-wrap{{margin:8px 0}}
    .spin-btn{{
      font-size:12px;padding:6px 14px;background:transparent;
      border:1px solid var(--amber);color:var(--amber);border-radius:6px;
      cursor:pointer;font-family:inherit;font-weight:600;transition:all .15s;
    }}
    .spin-btn.open{{background:var(--amber-d)}}
    .spin-body{{
      margin-top:8px;padding:10px 12px;background:var(--amber-d);
      border:1px solid var(--amber);border-radius:8px;
      font-size:13px;color:var(--t1);line-height:1.8;
    }}
    .spin-label{{color:var(--amber);font-weight:700}}

    /* ── ACTIONS ── */
    .story-actions{{display:flex;gap:8px;margin-top:12px}}
    .share-btn{{
      font-size:12px;padding:6px 14px;background:var(--bg3);
      border:1px solid var(--bd);color:var(--t2);border-radius:6px;
      cursor:pointer;font-family:inherit;transition:all .15s;
    }}
    .share-btn:hover{{color:var(--t1)}}

    /* ── EMPTY ── */
    .empty-state{{text-align:center;color:var(--t3);font-size:14px;padding:40px 20px}}

    /* ── SCROLL TOP ── */
    #go-top{{
      position:fixed;bottom:24px;left:16px;
      width:40px;height:40px;border-radius:50%;
      background:var(--bg3);border:1px solid var(--bd);
      color:var(--t2);font-size:18px;cursor:pointer;
      display:none;align-items:center;justify-content:center;
      z-index:50;box-shadow:0 4px 16px rgba(0,0,0,.4);transition:all .15s;
    }}
    #go-top:hover{{color:var(--t1)}}
    #go-top.on{{display:flex}}

    /* ── FOOTER ── */
    footer{{
      text-align:center;font-size:11px;color:var(--t3);
      padding:20px 16px 40px;max-width:700px;margin:0 auto;
    }}
    footer a{{color:var(--t3);text-decoration:none}}
    footer a:hover{{color:var(--t2)}}
  </style>
</head>
<body>

<header class="hdr">
  <div class="hdr-top">
    <div>
      <div class="app-name">المنتقي السيادي</div>
      <div class="hdr-meta">
        <span class="dot" id="fresh-dot"></span>
        <span id="rel-time">...</span>
        &nbsp;·&nbsp;
        وقت القراءة: {ar(read_min)} دقائق
      </div>
    </div>
    <button class="icon-btn" id="theme-btn" onclick="toggleTheme()">☀️</button>
  </div>
  <div class="tabs">
    <button class="tab on"     onclick="switchTab('g',this)">عالمي ({ar(g_count)})</button>
    <button class="tab local"  onclick="switchTab('l',this)">السعودية ({ar(l_count)})</button>
  </div>
</header>

<div class="main">

  <div class="dmeta">
    <span class="dmeta-txt">{ar(total)} مقال · {display}</span>
    <button class="copy-btn" id="copy-btn" onclick="copyHeadlines()">نسخ العناوين</button>
  </div>

  <!-- Table of Contents -->
  <div class="toc-wrap">
    <button class="toc-toggle" onclick="toggleToc(this)">
      <span>فهرس القصص</span><span id="toc-arrow">▾</span>
    </button>
    <div class="toc-body" id="toc-body">
      {toc_html}
    </div>
  </div>

  <!-- Category Filters -->
  <div class="filters">{cat_btns}</div>

  <!-- Global Section -->
  <div class="sec on" id="sec-g">
    <div class="sec-hdr">
      <span class="sec-dot g"></span>
      <span class="sec-title">الأخبار العالمية</span>
      <span class="sec-count">{ar(g_count)} قصة</span>
    </div>
    {global_cards}
  </div>

  <!-- Local Section -->
  <div class="sec" id="sec-l">
    <div class="sec-hdr">
      <span class="sec-dot l"></span>
      <span class="sec-title">أخبار المملكة العربية السعودية</span>
      <span class="sec-count">{ar(l_count)} قصة</span>
    </div>
    {local_cards}
  </div>

</div>

<button id="go-top" onclick="scrollTo({{top:0,behavior:'smooth'}})">↑</button>

<footer>
  التحديث القادم: غداً الساعة ٩:٠٠ صباحاً (توقيت السعودية)
  &nbsp;·&nbsp;
  <a href="https://github.com/HotSalsa10/Sovereign-News-Curator/actions" target="_blank">تحديث يدوي ↗</a>
</footer>

<script>
const GEN = "{iso}";
const HEADLINES = `{headlines_js}`;

// ── Freshness ──
function relTime(iso){{
  const m = Math.floor((Date.now()-new Date(iso))/60000);
  const h = Math.floor(m/60);
  if(m<60) return `منذ ${{m}} دقيقة`;
  if(h<24) return `منذ ${{h}} ساعة`;
  return 'منذ أكثر من يوم';
}}
function freshColor(iso){{
  const h=(Date.now()-new Date(iso))/3600000;
  return h<4?'#10b981':h<12?'#3b82f6':h<24?'#f59e0b':'#ef4444';
}}
function updateMeta(){{
  document.getElementById('rel-time').textContent=relTime(GEN);
  document.getElementById('fresh-dot').style.background=freshColor(GEN);
}}
updateMeta(); setInterval(updateMeta,60000);

// ── Theme ──
let dark=true;
function toggleTheme(){{
  dark=!dark;
  document.body.classList.toggle('light',!dark);
  document.getElementById('theme-btn').textContent=dark?'☀️':'🌙';
  document.getElementById('theme-meta').content=dark?'#0a0a0a':'#f4f4f5';
  localStorage.setItem('snc-theme',dark?'dark':'light');
}}
if(localStorage.getItem('snc-theme')==='light') toggleTheme();

// ── Tabs ──
let curTab='g', curCat='all';
function switchTab(id,btn){{
  curTab=id;
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  document.querySelectorAll('.sec').forEach(s=>s.classList.remove('on'));
  document.getElementById('sec-'+id).classList.add('on');
  applyFilter();
  scrollTo({{top:0,behavior:'smooth'}});
}}

// ── Story expand ──
function toggleStory(hdr){{
  const body=hdr.nextElementSibling;
  const opening=body.hidden;
  body.hidden=!opening;
  hdr.classList.toggle('open',opening);
  if(opening) hdr.closest('.story-card').classList.add('read');
}}

// ── Spin ──
function toggleSpin(btn){{
  const body=btn.nextElementSibling;
  body.hidden=!body.hidden;
  btn.classList.toggle('open',!body.hidden);
  btn.textContent=body.hidden?'اكشف التحيز الإعلامي':'إخفاء التحيز';
}}

// ── TOC ──
function toggleToc(btn){{
  const body=document.getElementById('toc-body');
  body.classList.toggle('open');
  document.getElementById('toc-arrow').textContent=body.classList.contains('open')?'▴':'▾';
}}
function jumpToStory(el){{
  const sec=el.dataset.section==='global'?'g':'l';
  const idx=parseInt(el.dataset.index);
  // Switch tab
  const tabBtn=document.querySelector(sec==='g'?'.tab:not(.local)':'.tab.local');
  switchTab(sec,tabBtn);
  // Close TOC
  document.getElementById('toc-body').classList.remove('open');
  document.getElementById('toc-arrow').textContent='▾';
  // Scroll & expand
  setTimeout(()=>{{
    const cards=[...document.querySelectorAll('#sec-'+sec+' .story-card')].filter(c=>!c.hidden);
    if(cards[idx]){{
      cards[idx].scrollIntoView({{behavior:'smooth',block:'center'}});
      const hdr=cards[idx].querySelector('.story-hdr');
      if(cards[idx].querySelector('.story-body').hidden) toggleStory(hdr);
    }}
  }},120);
}}

// ── Category filter ──
function filterCat(btn){{
  curCat=btn.dataset.cat;
  document.querySelectorAll('.flt-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  applyFilter();
}}
function applyFilter(){{
  document.querySelectorAll('#sec-'+curTab+' .story-card').forEach(card=>{{
    card.hidden = curCat!=='all' && card.dataset.cat!==curCat;
  }});
}}

// ── Share ──
async function shareStory(btn){{
  const card=btn.closest('.story-card');
  const headline=card.dataset.headline;
  const summary=card.dataset.summary;
  const text=headline+'\\n'+summary+'...\\n\\nعبر المنتقي السيادي للأخبار';
  if(navigator.share){{
    try{{await navigator.share({{title:headline,text}});}}catch(e){{}}
  }}else{{
    try{{await navigator.clipboard.writeText(text);alert('تم النسخ!');}}catch(e){{}}
  }}
}}

// ── Copy headlines ──
async function copyHeadlines(){{
  try{{
    await navigator.clipboard.writeText(HEADLINES);
    const btn=document.getElementById('copy-btn');
    btn.textContent='تم النسخ ✓';
    setTimeout(()=>btn.textContent='نسخ العناوين',2500);
  }}catch(e){{}}
}}

// ── Scroll-to-top ──
const goTop=document.getElementById('go-top');
window.addEventListener('scroll',()=>goTop.classList.toggle('on',scrollY>300));
</script>
</body>
</html>"""

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    print("=" * 52)
    print(f"  SOVEREIGN NEWS CURATOR  |  Model: {MODEL}")
    print("=" * 52)

    articles = fetch_all_feeds()

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
    l = len(digest.get("local", []))
    print(f"\n[Done] index.html written")
    print(f"       Global stories : {g}")
    print(f"       Local stories  : {l}")
    print("=" * 52)


if __name__ == "__main__":
    main()
