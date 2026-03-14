# Sovereign News Curator — Development Workflow

## 1. Project Overview

The **Sovereign News Curator** ("المنتقي السيادي للأخبار") is a fully automated, zero-click daily news briefing application. It delivers an "Epistemic Defense Shield" — protecting users from cognitive overload, algorithmic bias, and media manipulation.

### The Pipeline
1. **Data Ingestion**: GitHub Actions runs daily at 06:00 UTC. Python script fetches 18 RSS feeds in parallel (10 global news, 8 Saudi/regional).
2. **Living Context Engine**: Loads up to 7 days of archived headlines to detect developing stories.
3. **LLM Processing**: Sends all articles to Claude (claude-sonnet-4-6) via Anthropic API.
4. **JSON Digest**: Claude returns structured JSON with de-sensationalized headlines, consensus facts, media spin analysis, category tags, and developing-story flags — all in Arabic.
5. **HTML Rendering**: Python generates a self-contained `index.html` (no dependencies, single file).
6. **Deployment**: Commits updated HTML + archive to GitHub; live via GitHub Pages.

### Frontend Features
- Two-tab interface: Global News (عالمي) and Saudi Arabia News (السعودية)
- Category filtering (Security, Economy, Politics, Health, Tech, Environment, Society)
- Table of Contents with deep-link navigation
- Collapsible story cards: consensus summary, media spin breakdown, source attribution
- Freshness indicator (color-coded dot + relative time)
- Dark/light theme toggle (localStorage persistence)
- Read-state tracking (visual fade on expand)
- Share via Web Share API or clipboard
- PWA-compliant: installable on mobile home screen
- Full RTL support (Arabic-Indic numerals, Cairo font)

---

## 2. GSD Phase-Based Workflow

Follow this three-phase cycle for all development tasks:

### Phase 1: PLAN
Use the `/everything-claude-code:plan` agent to scope the task.
- Define what needs to change and why
- Identify affected files
- Consider edge cases and risks
- Estimate implementation approach

### Phase 2: EXECUTE
Use TDD methodology (write tests first, implement to pass, refactor).

**RED** → Write test(s) that should fail
- Use `pytest` with mocking for API/file I/O
- Test edge cases, not happy paths
- Verify tests actually fail

**GREEN** → Implement minimal code to pass tests
- Focus on the test requirements
- Don't over-engineer
- Keep functions small (<50 lines)

**IMPROVE** → Refactor if needed
- Reduce duplication
- Improve readability
- No new behavior (tests should still pass)

### Phase 3: VERIFY
Use code review agents before merging.
- `/everything-claude-code:python-review` — PEP 8, type hints, idiomatic Python
- `/everything-claude-code:security-review` — Secrets, injection, validation
- Fix all CRITICAL and HIGH issues
- Address MEDIUM issues when possible
- Push only after review passes

---

## 3. Agent Routing Table

| Task | Agent | When to Use |
|------|-------|-----------|
| Planning a feature | `/everything-claude-code:plan` | Before writing any code |
| Architecture decisions | `everything-claude-code:architect` | Multi-file refactoring, design patterns |
| Writing/testing Python | `/everything-claude-code:python-review` | After code changes, before commit |
| TDD workflow | `/everything-claude-code:tdd` | New features, bug fixes (write tests first) |
| Security analysis | `/everything-claude-code:security-review` | Before commit: secrets, validation, injection |
| Build/runtime errors | `everything-claude-code:build-error-resolver` | When tests or scripts fail |

---

## 4. Token Optimization (CRITICAL)

ECC uses three models. Choose wisely to minimize cost and latency:

### Haiku 4.5 (Fast, cheapest — 90% of Sonnet capability)
Use for:
- File reads, glob searches, simple grep queries
- Exploratory tasks (understanding code structure)
- Simple edits (typo fixes, variable renames)

### Sonnet 4.6 (Balanced — best for coding)
Use for:
- Writing code (functions, tests, modules)
- Unit test implementation
- Code review
- Bug fixes
- **Default for main development tasks**

### Opus 4.6 (Deepest reasoning — most expensive)
Use for:
- Complex architecture decisions
- Security analysis (vulnerability audit)
- Multi-file refactoring strategy
- Research and analysis

**Strategy**: Let agents route to Haiku for reads, Sonnet for coding, Opus for complex reasoning. Avoid Opus for simple tasks.

---

## 5. Code Standards

### Immutability (CRITICAL)
**Never modify existing objects. Always create new copies.**

```python
# WRONG
def add_category(digest, story, cat):
    story["category"] = cat  # ❌ Mutates story
    return digest

# CORRECT
def add_category(digest, story, cat):
    new_story = {**story, "category": cat}  # ✓ Creates new dict
    return digest
```

### File Organization
- Target: **200–400 lines** per file (max 800)
- High cohesion: one responsibility per file
- Low coupling: import only what you use
- Group by feature/domain, not by type

### Error Handling
- **Always handle errors explicitly** at every level
- Provide user-friendly error messages in CLI output
- Log detailed error context (stack trace, input data) on server side
- Never silently swallow errors

```python
# GOOD
try:
    digest = call_claude(articles, archive_context)
except Exception as e:
    print(f"ERROR: Claude API call failed: {e}")
    logger.error("Claude failure", exc_info=True, articles_count=len(articles))
    sys.exit(1)
```

### Input Validation
- Validate all user input before processing
- Validate external API responses (never trust them)
- Fail fast with clear error messages
- Use schema-based validation where possible

```python
# GOOD
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY environment variable not set")
    sys.exit(1)
```

### No Hardcoded Secrets
- **NEVER** hardcode API keys, tokens, or credentials
- Use environment variables (see `.env.example`)
- Validate required env vars at startup
- Rotate secrets if accidentally exposed

---

## 6. Test-Driven Development

### Requirements
- **Minimum 80% test coverage** for all code
- Unit tests for functions (not mocking I/O)
- Integration tests for API calls (mocking external services)
- E2E tests for critical user flows

### Workflow
1. Write test first (RED — test should fail)
2. Implement minimal code to pass (GREEN)
3. Refactor (IMPROVE — no behavior change)
4. Verify coverage: `pytest tests/ --cov=scripts --cov-report=term-missing`

### Testing Tools
- **pytest** — test runner
- **pytest-mock** — mocking fixtures
- **pytest-cov** — coverage reporting

### Example
```python
# tests/test_generate_digest.py
import pytest
from scripts.generate_digest import strip_html

def test_strip_html_removes_tags():
    """RED: This should pass"""
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"

def test_strip_html_empty_input():
    """Edge case: empty string"""
    assert strip_html("") == ""
    assert strip_html(None) == ""
```

---

## 7. Commit Conventions

Use **conventional commits** for clarity and automated changelog generation:

```
<type>: <description>

<optional body explaining why>
```

### Types
- `feat:` — new feature
- `fix:` — bug fix
- `test:` — add/update tests
- `docs:` — documentation
- `refactor:` — code restructuring (no behavior change)
- `perf:` — performance improvement
- `ci:` — CI/CD changes
- `chore:` — dependencies, tooling

### Examples
```
feat: add category filtering to story cards
test: add unit tests for load_archive()
fix: handle missing ANTHROPIC_API_KEY gracefully
docs: document GSD workflow in CLAUDE.md
refactor: split generate_digest.py into smaller modules
```

---

## 8. Pipeline Architecture Reference

### File Structure
```
Sovereign-News-Curator/
├── scripts/
│   └── generate_digest.py     # Main pipeline (RSS → Claude → HTML)
├── tests/
│   ├── __init__.py
│   └── test_generate_digest.py # Unit tests
├── archive/
│   └── YYYY-MM-DD.json         # 7-day headline history
├── .env.example                # Secret template
├── .env                        # (GITIGNORED) Actual secrets
├── index.html                  # Generated web app
├── manifest.json               # PWA config
├── CLAUDE.md                   # This file
├── requirements.txt            # Python dependencies
└── .github/
    └── workflows/
        ├── daily-digest.yml    # Scheduled news generation
        └── ci.yml              # PR test runner
```

### Key Functions in `generate_digest.py`

| Function | Purpose | Status |
|----------|---------|--------|
| `fetch_feed(feed)` | Fetch and parse one RSS feed | Core |
| `fetch_all_feeds()` | Parallel fetch of 18 feeds | Core |
| `load_archive()` | Load 7 days of context | Core |
| `call_claude(articles, archive_context)` | Send to LLM, extract JSON | Core |
| `build_html(digest, generated_at, article_count)` | Render HTML page | Core |
| `strip_html(text)` | Remove HTML tags from RSS summaries | Utility — **test** |
| `extract_json(text)` | Parse JSON from Claude response | Utility — **test** |
| `safe(text)` | HTML-escape strings for attributes | Utility — **test** |
| `ar(n)` | Convert ASCII digits to Arabic-Indic | Utility — **test** |
| `build_story_cards(stories, section_id)` | Generate HTML cards | Utility — **test** |
| `build_toc(digest)` | Generate table of contents | Utility — **test** |
| `get_categories(digest)` | Extract unique categories | Utility — **test** |
| `count_words(digest)` | Calculate reading time | Utility — **test** |

### Daily Digest Workflow (CI/CD)

1. **Trigger**: 06:00 UTC daily (or manual dispatch)
2. **Checkout**: Clone repo with latest code
3. **Setup**: Python 3.12 + `pip install -r requirements.txt`
4. **Generate**: `python scripts/generate_digest.py`
   - Fetches 18 RSS feeds
   - Calls Claude API (sonnet-4-6)
   - Writes `index.html` and `archive/YYYY-MM-DD.json`
5. **Commit**: Auto-commit with message `digest: YYYY-MM-DD HH:MM UTC`
6. **Push**: GitHub Bot pushes to main → Page live

### System Prompt for Claude

The model receives this directive:
- **Role**: Elite defensive AI reading agent
- **Task**: Categorize articles → deduplicate → extract consensus → identify spin → de-sensationalize
- **Output**: Strict JSON with `global` and `local` arrays, each containing stories with Arabic headlines, summaries, spin analysis, sources, categories, and context
- **Constraint**: No hallucinated quotes, dates, or URLs; only facts reported by the provided sources

---

## Development Checklist

Before committing:
- [ ] Tests written first (RED), implementation passes (GREEN), refactored (IMPROVE)
- [ ] 80%+ test coverage: `pytest tests/ --cov=scripts --cov-report=term-missing`
- [ ] No hardcoded secrets (use `.env`)
- [ ] Functions <50 lines, files <800 lines
- [ ] Error handling on all I/O
- [ ] PEP 8 compliance (run `/python-review` agent)
- [ ] Security audit (run `/security-review` agent)
- [ ] Conventional commit message (feat:, fix:, test:, docs:)

---

## Quick Start for Developers

```bash
# 1. Clone and enter project
git clone https://github.com/HotSalsa10/Sovereign-News-Curator
cd Sovereign-News-Curator

# 2. Create .env from template
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run tests
python -m pytest tests/ -v --cov=scripts --cov-report=term-missing

# 5. Generate a digest (manual test)
python scripts/generate_digest.py

# 6. Start development cycle
# Plan → TDD (red/green/refactor) → Review → Commit
```

---

## Resources
- **ECC Agents**: Use `/everything-claude-code:plan`, `/tdd`, `/python-review`, `/security-review`
- **Test Framework**: pytest docs at https://docs.pytest.org
- **Conventional Commits**: https://www.conventionalcommits.org
- **Python Best Practices**: PEP 8 (https://pep8.org), PEP 20 (The Zen of Python)
- **GitHub Actions**: https://docs.github.com/en/actions