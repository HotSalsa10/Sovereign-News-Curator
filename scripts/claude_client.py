"""Claude API client, prompt formatting, and JSON extraction."""

import json
import logging
import os
import re
import time
from typing import Any, cast

import anthropic

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3

SYSTEM_PROMPT = """You are the Sovereign News Curator. Extract consensus facts only. Output ONLY valid JSON.

TASKS: (1) Deduplicate articles covering same events (2) Consensus facts only, no hallucinations (3) Detect media spin (4) Flag developing stories using historical context

OUTPUT: Valid JSON with global/local arrays. Each story: headline (Arabic), summary (3 sent max), spin (1 sent), sources (list), category (سياسة|اقتصاد|أمن|صحة|تقنية|بيئة|مجتمع), is_developing (bool), context (Arabic or null).

RULES: Empty section = []. All Arabic text in headline/summary/spin/context/category. No hallucinated quotes/dates/URLs. context=null for new stories."""

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
        section(local_articles, "SAUDI ARABIA NEWS ARTICLES"),
    ]
    return "\n\n".join(parts)


def extract_json(text: str) -> dict[str, Any]:
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text.strip(), flags=re.MULTILINE)
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        return json.loads(match.group())  # type: ignore[no-any-return]
    raise ValueError("No valid JSON in Claude response")


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


def call_claude(articles: dict[str, Any], archive_context: str) -> dict[str, Any]:
    from anthropic.types import TextBlock
    logger.info("Calling %s...", MODEL)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
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
            raw = cast(TextBlock, message.content[0]).text
            logger.info(
                "Claude done. Tokens — input: %d, output: %d",
                message.usage.input_tokens,
                message.usage.output_tokens,
            )
            digest = extract_json(raw)
            validate_digest(digest)
            for section_key in ("global", "local"):
                for story in digest.get(section_key, []):
                    story["source_count"] = len(story.get("sources", []))
            return digest
        except (KeyboardInterrupt, SystemExit):
            raise
        except (anthropic.APIError, anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt
                logger.warning("Attempt %d failed: %s. Retrying in %ds...", attempt, e, wait)
                time.sleep(wait)
        except Exception as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt
                logger.warning("Attempt %d failed: %s. Retrying in %ds...", attempt, e, wait)
                time.sleep(wait)
    raise RuntimeError(f"Claude API failed after {MAX_RETRIES} attempts: {last_exc}") from last_exc
