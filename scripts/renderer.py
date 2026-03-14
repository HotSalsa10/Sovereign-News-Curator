"""HTML rendering for the daily digest page."""

import html as html_lib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def ar(n: int) -> str:
    """Convert integer to Arabic-Indic numerals."""
    eastern = "٠١٢٣٤٥٦٧٨٩"
    return "".join(eastern[int(d)] for d in str(n))


def safe(text: str) -> str:
    """HTML-escape a string for use in attributes or text nodes."""
    return html_lib.escape(str(text or ""), quote=True)


def _build_badges(is_top: bool, is_dev: bool) -> str:
    """Return badge HTML for a story card."""
    badges = ""
    if is_top:
        badges += '<span class="badge badge-hot">الأكثر تداولاً</span>'
    if is_dev:
        badges += '<span class="badge badge-dev">متطور</span>'
    return badges


def _build_spin_section(spin: str) -> str:
    """Return the spin disclosure HTML, or empty string if no spin."""
    if not spin:
        return ""
    return (
        f'<div class="spin-wrap">'
        f'<button class="spin-btn" onclick="toggleSpin(this)">اكشف التحيز الإعلامي</button>'
        f'<div class="spin-body" hidden>'
        f'<span class="spin-label">التلاعب الإعلامي: </span>{safe(spin)}'
        f'</div></div>'
    )


def build_story_cards(stories: list[dict[str, Any]], section_id: str) -> str:
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

        badges       = _build_badges(is_top, is_dev)
        source_pills = "".join(f'<span class="src-pill">{safe(s)}</span>' for s in sources)
        context_html = f'<div class="story-context">{safe(context)}</div>' if context else ""
        spin_html    = _build_spin_section(spin)

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
  <div class="story-body">
    <div class="story-body-inner">
      {context_html}
      <p class="story-summary">{safe(summary)}</p>
      {spin_html}
      <div class="story-actions">
        <button class="share-btn" onclick="shareStory(this)">مشاركة ↗</button>
      </div>
    </div>
  </div>
</div>""")

    return "\n".join(cards)


def build_toc(digest: dict[str, list[dict[str, Any]]]) -> str:
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


def get_categories(digest: dict[str, list[dict[str, Any]]]) -> list[str]:
    cats = set()
    for sk in ("global", "local"):
        for s in digest.get(sk, []):
            if s.get("category"):
                cats.add(s["category"])
    return sorted(cats)


def get_category_counts(digest: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """Count stories per category across all sections."""
    counts: dict[str, int] = {}
    for sk in ("global", "local"):
        for s in digest.get(sk, []):
            cat = s.get("category", "")
            if cat:
                counts[cat] = counts.get(cat, 0) + 1
    return counts


def count_words(digest: dict[str, list[dict[str, Any]]]) -> int:
    words = 0
    for sk in ("global", "local"):
        for s in digest.get(sk, []):
            words += len(s.get("summary", "").split())
    return words


def next_run_display(generated_at: datetime) -> str:
    """Return the next scheduled digest run as an Arabic-Indic time string."""
    saudi_tz = timezone(timedelta(hours=3))
    # Ensure tz-aware for safe astimezone() call
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    # Pipeline fires daily at 06:00 UTC = 09:00 AST (+3)
    run_at_utc = generated_at.replace(hour=6, minute=0, second=0, microsecond=0)
    if generated_at >= run_at_utc:
        next_run = run_at_utc + timedelta(days=1)
    else:
        next_run = run_at_utc
    next_local = next_run.astimezone(saudi_tz)
    saudi_now = generated_at.astimezone(saudi_tz)
    day = "غداً" if next_local.date() > saudi_now.date() else "اليوم"
    h = next_local.hour % 12 or 12
    m = next_local.minute
    period = "صباحاً" if next_local.hour < 12 else "مساءً"
    m_str = f"٠{ar(m)}" if m < 10 else ar(m)
    return f"{day} الساعة {ar(h)}:{m_str} {period} (توقيت السعودية)"


def all_headlines_js(digest: dict[str, list[dict[str, Any]]]) -> str:
    lines = []
    for i, s in enumerate(digest.get("global", []), 1):
        lines.append(f"{i}. {html_lib.escape(s.get('headline', ''))}")
    for i, s in enumerate(digest.get("local", []), 1):
        lines.append(f"{i}. {html_lib.escape(s.get('headline', ''))}")
    # Escape for JS template literal
    return "\\n".join(lines).replace("`", "\\`")


# ─────────────────────────────────────────────
# SVG ICONS
# ─────────────────────────────────────────────

_SVG_SUN = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true">'
    '<circle cx="12" cy="12" r="5"/>'
    '<line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>'
    '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>'
    '<line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>'
    '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>'
    '</svg>'
)
_SVG_MOON = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true">'
    '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
    '</svg>'
)


# ─────────────────────────────────────────────
# HTML BUILD
# ─────────────────────────────────────────────

def build_html(
    digest: dict[str, list[dict[str, Any]]],
    generated_at: datetime,
    article_count: dict[str, int],
) -> str:
    saudi_tz  = timezone(timedelta(hours=3))
    saudi_now = generated_at.astimezone(saudi_tz)
    iso       = generated_at.isoformat()
    display   = saudi_now.strftime("%d/%m/%Y · %I:%M %p")

    global_stories = digest.get("global", [])
    local_stories  = digest.get("local",  [])
    g_count = len(global_stories)
    l_count = len(local_stories)
    logger.info("Building HTML: %d global, %d local stories", g_count, l_count)
    total   = article_count["global"] + article_count["local"]

    words    = count_words(digest)
    read_min = max(1, round(words / 120))

    global_cards = build_story_cards(global_stories, "global")
    local_cards  = build_story_cards(local_stories,  "local")
    toc_html     = build_toc(digest)
    categories   = get_categories(digest)
    cat_counts   = get_category_counts(digest)
    headlines_js = all_headlines_js(digest)
    next_run     = next_run_display(generated_at)

    cat_btns = '<button class="flt-btn active" data-cat="all" onclick="filterCat(this)">الكل</button>'
    for c in categories:
        cnt = cat_counts.get(c, 0)
        cnt_html = f' <span class="flt-count">({ar(cnt)})</span>'
        cat_btns += (
            f'<button class="flt-btn" data-cat="{safe(c)}" onclick="filterCat(this)">'
            f'{safe(c)}{cnt_html}</button>'
        )

    svg_sun  = _SVG_SUN
    svg_moon = _SVG_MOON

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
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
      --t1:#f4f4f5;--t2:#a1a1aa;--t3:#808080;
      --blue:#3b82f6;--blue-d:#1d3b6e;
      --green:#10b981;--green-d:#064e3b;
      --amber:#f59e0b;--amber-d:#292203;
      --r:12px;
    }}
    .light{{
      --bg:#f4f4f5;--bg2:#fff;--bg3:#e4e4e7;
      --bd:#d4d4d8;--bd2:#e4e4e7;
      --t1:#09090b;--t2:#52525b;--t3:#5a5a65;
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
      min-height:44px;min-width:44px;
      display:inline-flex;align-items:center;justify-content:center;
    }}
    .icon-btn:hover{{color:var(--t1);border-color:var(--t2)}}

    /* ── TABS ── */
    .tabs{{display:flex;gap:6px;padding:8px 16px;max-width:700px;margin:0 auto}}
    .tab{{
      flex:1;padding:8px;border-radius:8px;border:1px solid var(--bd);
      background:transparent;color:var(--t2);font-family:inherit;
      font-size:13px;font-weight:700;cursor:pointer;transition:all .15s;
      min-height:44px;
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
      min-height:44px;min-width:44px;
    }}
    .copy-btn:hover{{color:var(--t1)}}

    /* ── TOC ── */
    .toc-wrap{{background:var(--bg2);border:1px solid var(--bd2);border-radius:var(--r);margin-bottom:10px;overflow:hidden}}
    .toc-toggle{{
      width:100%;background:none;border:none;padding:12px 16px;
      display:flex;align-items:center;justify-content:space-between;
      font-family:inherit;font-size:13px;font-weight:700;color:var(--t2);cursor:pointer;
      min-height:44px;
    }}
    .toc-body{{
      display:grid;grid-template-rows:0fr;
      transition:grid-template-rows 200ms ease;
    }}
    .toc-body.open{{grid-template-rows:1fr}}
    .toc-body-inner{{overflow:hidden;padding:0 16px 12px;min-height:0}}
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
      min-height:44px;
    }}
    .flt-btn.active{{background:var(--blue);border-color:var(--blue);color:#fff}}
    .flt-count{{font-size:10px;opacity:.7}}

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
    .expand-icon{{position:absolute;inset-inline-start:14px;top:14px;font-size:20px;color:var(--t3);font-weight:300;transition:transform .2s;line-height:1}}
    .story-hdr.open .expand-icon{{transform:rotate(45deg)}}

    /* ── STORY BODY (animated expand) ── */
    .story-body{{
      display:grid;grid-template-rows:0fr;
      transition:grid-template-rows 220ms cubic-bezier(.4,0,.2,1);
    }}
    .story-body.open{{grid-template-rows:1fr}}
    .story-body-inner{{
      overflow:hidden;padding:0 16px 14px;min-height:0;
      border-top:1px solid var(--bd2);
    }}
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
      min-height:44px;
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
      min-height:44px;
    }}
    .share-btn:hover{{color:var(--t1)}}

    /* ── EMPTY STATES ── */
    .empty-state{{text-align:center;color:var(--t3);font-size:14px;padding:40px 20px}}
    .filter-empty{{display:none}}
    .filter-empty:not([hidden]){{display:block}}

    /* ── SCROLL TOP ── */
    #go-top{{
      position:fixed;bottom:24px;inset-inline-start:16px;
      width:44px;height:44px;border-radius:50%;
      background:var(--bg3);border:1px solid var(--bd);
      color:var(--t2);font-size:18px;cursor:pointer;
      display:none;align-items:center;justify-content:center;
      z-index:50;box-shadow:0 4px 16px rgba(0,0,0,.4);transition:all .15s;
    }}
    #go-top:hover{{color:var(--t1)}}
    #go-top.on{{display:flex}}

    /* ── ACCESSIBILITY: keyboard focus ── */
    .icon-btn:focus-visible,.tab:focus-visible,.copy-btn:focus-visible,
    .toc-toggle:focus-visible,.toc-item:focus-visible,.flt-btn:focus-visible,
    .spin-btn:focus-visible,.share-btn:focus-visible,#go-top:focus-visible{{
      outline:2px solid var(--blue);outline-offset:2px;
    }}

    /* ── TOAST NOTIFICATION ── */
    #toast{{
      position:fixed;bottom:80px;left:50%;transform:translateX(-50%) translateY(20px);
      background:var(--bg3);border:1px solid var(--bd);color:var(--t1);
      padding:10px 18px;border-radius:8px;font-size:13px;
      opacity:0;transition:opacity .25s,transform .25s;pointer-events:none;
      z-index:9999;white-space:nowrap;
    }}
    #toast.show{{opacity:1;transform:translateX(-50%) translateY(0)}}
    #toast.error{{border-color:#ef4444;color:#ef4444}}

    /* ── REDUCED MOTION ── */
    @media (prefers-reduced-motion:reduce){{
      *,*::before,*::after{{transition:none!important;animation:none!important}}
    }}

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
    <button class="icon-btn" id="theme-btn" onclick="toggleTheme()" aria-label="تبديل السمة"></button>
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
      <div class="toc-body-inner">
        {toc_html}
      </div>
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
<div id="toast" role="status" aria-live="polite"></div>

<footer>
  التحديث القادم: {next_run}
  &nbsp;·&nbsp;
  <a href="https://github.com/HotSalsa10/Sovereign-News-Curator/actions" target="_blank">تحديث يدوي ↗</a>
</footer>

<script>
const GEN = "{iso}";
const HEADLINES = `{headlines_js}`;
const SVG_SUN = '{svg_sun}';
const SVG_MOON = '{svg_moon}';

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
  document.getElementById('theme-btn').innerHTML=dark?SVG_SUN:SVG_MOON;
  document.getElementById('theme-meta').content=dark?'#0a0a0a':'#f4f4f5';
  localStorage.setItem('snc-theme',dark?'dark':'light');
}}
if(localStorage.getItem('snc-theme')==='light') toggleTheme();
else document.getElementById('theme-btn').innerHTML=SVG_SUN;

// ── Tabs ──
let curTab='g', curCat='all';
function switchTab(id,btn){{
  curTab=id;
  curCat='all';
  document.querySelectorAll('.flt-btn').forEach(b=>b.classList.remove('active'));
  const allBtn=document.querySelector('.flt-btn[data-cat="all"]');
  if(allBtn) allBtn.classList.add('active');
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
  const opening=!body.classList.contains('open');
  body.classList.toggle('open',opening);
  hdr.classList.toggle('open',opening);
  if(opening){{
    const card=hdr.closest('.story-card');
    card.classList.add('read');
    _markRead(card.dataset.headline.slice(0,64));
  }}
}}

// ── Read state persistence ──
const READ_KEY='snc-read-v1';
function _getRead(){{
  try{{return new Set(JSON.parse(localStorage.getItem(READ_KEY)||'[]'));}}
  catch{{return new Set();}}
}}
function _markRead(key){{
  const s=_getRead();s.add(key);
  localStorage.setItem(READ_KEY,JSON.stringify([...s]));
}}
(function restoreRead(){{
  const s=_getRead();
  if(!s.size) return;
  document.querySelectorAll('.story-card').forEach(card=>{{
    if(s.has(card.dataset.headline.slice(0,64))) card.classList.add('read');
  }});
}})();

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
  const open=!body.classList.contains('open');
  body.classList.toggle('open',open);
  document.getElementById('toc-arrow').textContent=open?'▴':'▾';
}}
function jumpToStory(el){{
  const sec=el.dataset.section==='global'?'g':'l';
  const idx=parseInt(el.dataset.index);
  const tabBtn=document.querySelector(sec==='g'?'.tab:not(.local)':'.tab.local');
  switchTab(sec,tabBtn);
  document.getElementById('toc-body').classList.remove('open');
  document.getElementById('toc-arrow').textContent='▾';
  setTimeout(()=>{{
    const cards=[...document.querySelectorAll('#sec-'+sec+' .story-card')].filter(c=>!c.hidden);
    if(cards[idx]){{
      cards[idx].scrollIntoView({{behavior:'smooth',block:'center'}});
      const hdr=cards[idx].querySelector('.story-hdr');
      if(!cards[idx].querySelector('.story-body').classList.contains('open')) toggleStory(hdr);
    }}
  }},120);
}}

// ── Category filter ──
function filterCat(btn){{
  curCat=btn.dataset.cat;
  document.querySelectorAll('.flt-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  try{{sessionStorage.setItem('snc-cat',curCat);}}catch{{}}
  applyFilter();
}}
(function restoreCat(){{
  try{{
    const saved=sessionStorage.getItem('snc-cat');
    if(saved&&saved!=='all'){{
      const btn=document.querySelector('.flt-btn[data-cat="'+saved+'"]');
      if(btn){{curCat=saved;document.querySelectorAll('.flt-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');applyFilter();}}
    }}
  }}catch{{}}
}})();
function applyFilter(){{
  const section=document.getElementById('sec-'+curTab);
  let visible=0;
  section.querySelectorAll('.story-card').forEach(card=>{{
    const show=curCat==='all'||card.dataset.cat===curCat;
    card.hidden=!show;
    if(show) visible++;
  }});
  let empty=section.querySelector('.filter-empty');
  if(!empty){{
    empty=document.createElement('p');
    empty.className='filter-empty empty-state';
    section.appendChild(empty);
  }}
  empty.hidden=visible>0;
  empty.textContent=visible===0?'لا توجد قصص في هذه الفئة.':'';
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
    try{{
      await navigator.clipboard.writeText(text);
      showToast('تم نسخ الرابط ✓');
    }}catch(e){{
      showToast('فشل النسخ — انسخ يدوياً',true);
    }}
  }}
}}

// ── Toast ──
let _toastTimer=null;
function showToast(msg,isError=false){{
  const el=document.getElementById('toast');
  el.textContent=msg;
  el.classList.toggle('error',isError);
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer=setTimeout(()=>el.classList.remove('show'),2500);
}}

// ── Copy headlines ──
async function copyHeadlines(){{
  const btn=document.getElementById('copy-btn');
  try{{
    await navigator.clipboard.writeText(HEADLINES);
    btn.textContent='تم النسخ ✓';
    setTimeout(()=>btn.textContent='نسخ العناوين',2500);
    showToast('تم نسخ العناوين ✓');
  }}catch(e){{
    try{{
      const ta=document.createElement('textarea');
      ta.value=HEADLINES;ta.style.position='fixed';ta.style.opacity='0';
      document.body.appendChild(ta);ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      btn.textContent='تم النسخ ✓';
      setTimeout(()=>btn.textContent='نسخ العناوين',2500);
      showToast('تم نسخ العناوين ✓');
    }}catch(e2){{
      showToast('فشل النسخ — انسخ يدوياً',true);
    }}
  }}
}}

// ── Scroll-to-top ──
const goTop=document.getElementById('go-top');
window.addEventListener('scroll',()=>goTop.classList.toggle('on',scrollY>300));

// ── Service Worker ──
if('serviceWorker' in navigator){{
  navigator.serviceWorker.register('./sw.js').catch(()=>{{}});
}}
</script>
</body>
</html>"""
