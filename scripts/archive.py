"""Archive loading and saving for the Living Context Engine."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

ARCHIVE_DAYS = 3
ROOT_DIR = Path(__file__).parent.parent

# ─────────────────────────────────────────────
# FUNCTIONS
# ─────────────────────────────────────────────

def load_archive() -> str:
    archive_dir = ROOT_DIR / "archive"
    if not archive_dir.exists():
        return ""
    files = sorted(archive_dir.glob("*.json"), reverse=True)[:ARCHIVE_DAYS]
    if not files:
        return ""
    lines = [f"HISTORICAL CONTEXT — story headlines from the past {ARCHIVE_DAYS} days (use this to detect developing stories and add context):"]
    for f in reversed(files):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "global" not in data or "local" not in data:
                raise ValueError(f"Invalid archive structure in {f.name}")
            date = f.stem
            g = " / ".join(str(h) for h in data["global"][:6])
            local_line = " / ".join(str(h) for h in data["local"][:4])
            lines.append(f"[{date}] Global: {g} | Saudi: {local_line}")
        except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError) as e:
            logger.warning("Archive file %s corrupted, skipping: %s", f.name, e)
    return "\n".join(lines)


def save_archive(digest: dict[str, Any], date_str: str) -> None:
    archive_dir = ROOT_DIR / "archive"
    archive_dir.mkdir(exist_ok=True)
    data = {
        "global": [s.get("headline", "") for s in digest.get("global", [])],
        "local":  [s.get("headline", "") for s in digest.get("local", [])],
    }
    out = archive_dir / f"{date_str}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Archive saved → %s", out.name)
