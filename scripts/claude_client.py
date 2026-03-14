"""Claude API client, prompt formatting, and JSON extraction."""

import json
import logging
import os
import random
import re
import time
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3

SYSTEM_PROMPT = """You are the Sovereign News Curator — an elite defensive news intelligence agent. Your job is to shield readers from cognitive overload, sensationalism, and media manipulation. Extract consensus facts only. Output ONLY valid JSON with no prose before or after it.

TASKS:
1. Deduplicate: group articles covering the same event into one story.
2. Consensus only: state only facts reported by multiple sources. No hallucinations.
3. Spin detection: identify the single most notable editorial bias or framing difference across sources.
4. Developing stories: use HISTORICAL CONTEXT (if provided) to flag stories still unfolding.

OUTPUT FORMAT — return exactly this JSON structure:

{
  "global": [
    {
      "headline": "عنوان موضوعي محايد بالعربية",
      "summary": "ملخص وقائعي بثلاث جمل بالعربية. الجملة الأولى: ماذا حدث. الثانية: السياق. الثالثة: الأثر.",
      "spin": "وصف موجز للتحيز الإعلامي الأبرز بالعربية",
      "sources": ["Source Name A", "Source Name B"],
      "category": "سياسة",
      "is_developing": false,
      "context": null
    }
  ],
  "local": [
    {
      "headline": "عنوان موضوعي محايد بالعربية",
      "summary": "ملخص وقائعي بثلاث جمل بالعربية.",
      "spin": "وصف موجز للتحيز الإعلامي الأبرز بالعربية",
      "sources": ["Source Name A"],
      "category": "اقتصاد",
      "is_developing": true,
      "context": "جملة سياق تاريخي واحدة بالعربية بناءً على السجل التاريخي المقدم"
    }
  ]
}

FIELD RULES:
- headline: neutral, de-sensationalized Arabic title. No clickbait, no emotional adjectives.
- summary: exactly 3 Arabic sentences. Facts only — no opinions, no speculation.
- spin: one Arabic sentence describing the most notable framing bias across sources.
- sources: list of source names exactly as provided in the input (e.g. "BBC World News").
- category: one of سياسة | اقتصاد | أمن | صحة | تقنية | بيئة | مجتمع — nothing else.
- is_developing: true only if this story appeared in HISTORICAL CONTEXT and is still evolving.
- context: one Arabic sentence from HISTORICAL CONTEXT if is_developing=true; null otherwise.

HARD RULES:
- Output ONLY the JSON object. No markdown fences, no explanatory text, no trailing comments.
- If a section has no articles: return an empty array [].
- Never hallucinate quotes, dates, URLs, or statistics not present in the input.
- All text in headline/summary/spin/context must be Arabic (except source names in the sources list)."""

# ─────────────────────────────────────────────
# FUNCTIONS
# ─────────────────────────────────────────────

def format_for_claude(
    global_articles: list[dict[str, str]],
    local_articles: list[dict[str, str]],
    archive_context: str,
) -> str:
    def section(articles: list, label: str) -> str:
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
        section(local_articles, "SAUDI ARABIA NEWS ARTICLES (Arabic-language Saudi sources — include only stories about Saudi Arabia or directly affecting Saudi Arabia)"),
    ]
    return "\n\n".join(parts)


def extract_json(text: str) -> dict[str, Any]:
    from json_repair import repair_json

    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text.strip(), flags=re.MULTILINE)
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        raise ValueError("No valid JSON in Claude response")
    raw_json = match.group()
    try:
        return json.loads(raw_json)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        logger.warning(
            "JSON parse failed at char %d (line %d, col %d): %s — attempting repair. "
            "Context: ...%s...",
            exc.pos,
            exc.lineno,
            exc.colno,
            exc.msg,
            raw_json[max(0, exc.pos - 60) : exc.pos + 60],
        )
        repaired = repair_json(raw_json, return_objects=True)
        if isinstance(repaired, dict):
            return repaired  # type: ignore[return-value]
        raise ValueError(f"JSON repair failed — unrecoverable response: {exc}") from exc


def validate_digest(digest: dict[str, Any]) -> None:
    """Raise ValueError if digest is missing required top-level keys or story fields."""
    required_story_fields = ("headline", "summary", "sources", "category")
    for key in ("global", "local"):
        if key not in digest or not isinstance(digest[key], list):
            raise ValueError(f"Digest missing '{key}' array")
    for section in ("global", "local"):
        for i, story in enumerate(digest[section]):
            for field in required_story_fields:
                if field not in story:
                    raise ValueError(f"Story {i} in '{section}' missing field '{field}'")
            if not isinstance(story["headline"], str):
                raise ValueError(f"Story {i} in '{section}': 'headline' must be a string")
            if not isinstance(story["summary"], str):
                raise ValueError(f"Story {i} in '{section}': 'summary' must be a string")
            if not isinstance(story["sources"], list):
                raise ValueError(f"Story {i} in '{section}': 'sources' must be a list")


def call_claude(articles: dict[str, Any], archive_context: str) -> dict[str, Any]:
    logger.info("Calling %s...", MODEL)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    client = anthropic.Anthropic(api_key=api_key)
    user_content = format_for_claude(articles["global"], articles["local"], archive_context)
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=8192,
                timeout=300.0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = getattr(message.content[0], "text", None) if message.content else None
            if not isinstance(raw, str):
                raise ValueError(f"Unexpected Claude response structure: {message.content!r}")
            logger.info(
                "Claude done. Tokens — input: %d, output: %d",
                message.usage.input_tokens,
                message.usage.output_tokens,
            )
            digest = extract_json(raw)
            validate_digest(digest)
            return {
                key: [
                    {**story, "source_count": len(story.get("sources", []))}
                    for story in digest.get(key, [])
                ]
                for key in ("global", "local")
            }
        except (KeyboardInterrupt, SystemExit):
            raise
        except (anthropic.APIError, anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning("Attempt %d failed: %s. Retrying in %.2fs...", attempt, e, wait)
                time.sleep(wait)
        except Exception as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning("Attempt %d failed: %s. Retrying in %.2fs...", attempt, e, wait)
                time.sleep(wait)
    raise RuntimeError(f"Claude API failed after {MAX_RETRIES} attempts: {last_exc}") from last_exc
