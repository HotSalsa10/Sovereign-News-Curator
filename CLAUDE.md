# Sovereign News Curator — Development Workflow

> Integrated from: GSD (get-shit-done), Everything Claude Code (ECC), UI/UX Pro Max, Awesome Claude Code

---

## 1. Project Overview

The **Sovereign News Curator** ("المنتقي السيادي للأخبار") is a fully automated, zero-click daily news briefing application. It delivers an "Epistemic Defense Shield" — protecting users from cognitive overload, algorithmic bias, and media manipulation.

### The Pipeline
1. **Data Ingestion**: GitHub Actions runs daily at 06:00 UTC. Python script fetches 18 RSS feeds in parallel (10 global news, 8 Saudi/regional).
2. **Living Context Engine**: Loads archived headlines (3-day window) to detect developing stories.
3. **LLM Processing**: Sends articles to Claude (claude-sonnet-4-6) via Anthropic API.
4. **JSON Digest**: Claude returns structured JSON with de-sensationalized headlines, consensus facts, media spin analysis, category tags, developing-story flags — all in Arabic.
5. **HTML Rendering**: Python generates self-contained `index.html` (no dependencies, single file).
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

## 2. GSD Phase-Based Workflow (from gsd-build/get-shit-done)

**Core principle**: Capture decisions in files BEFORE execution. Context engineering is the primary quality lever.

Follow this three-phase cycle for ALL development tasks. Save decisions to `.planning/` before writing any code.

### Pre-Phase: Discuss (for non-trivial features)

Before planning, answer these questions explicitly — save to `.planning/{N}-CONTEXT.md`:
- What exactly changes in the output format (JSON schema or HTML)?
- Does this affect the archive schema (backward compatibility)?
- What are the failure modes? (API timeout, empty feed, malformed RSS)
- Is this a GitHub Actions constraint or also a local concern?
- Who is affected? (CI pipeline, end users, future devs)

### Phase 1: PLAN

Use `/everything-claude-code:plan` agent to scope the task. Save to `.planning/{N}-PLAN.md`.
- Research existing patterns before writing new code
- Define what changes and why
- Identify affected files and functions
- Consider edge cases and failure modes
- Break into atomic tasks with clear dependencies

**Wave execution**: Group independent tasks → run them in parallel. Sequential only when there are dependencies.

### Phase 2: EXECUTE

Use TDD methodology (RED → GREEN → IMPROVE):

**RED** → Write tests first (tests MUST fail before implementing)
- Use `pytest` with mocking for API/file I/O
- Test edge cases and failure paths, not just happy paths
- Verify tests actually fail: `python -m pytest tests/ -v`

**GREEN** → Implement minimal code to pass tests
- Focus only on what the tests require
- Keep functions small (<50 lines)
- No over-engineering

**IMPROVE** → Refactor without changing behavior
- Reduce duplication
- Improve readability
- Tests must still pass after refactor

### Phase 3: VERIFY

Run the 6-phase verification gate before every commit:

```bash
# 1. Tests + Coverage
python -m pytest tests/ --cov=scripts --cov-report=term-missing

# 2. Type check
mypy scripts/generate_digest.py --ignore-missing-imports

# 3. Lint
ruff check scripts/

# 4. Coverage gate (must be ≥80%)
python -m pytest tests/ --cov=scripts --cov-fail-under=80

# 5. Security scan (no hardcoded secrets)
grep -rn "ANTHROPIC_API_KEY\s*=" scripts/ --include="*.py" | grep -v "os.environ"

# 6. Diff review
git diff HEAD --stat
```

Then run agents:
- `/everything-claude-code:python-review` — PEP 8, type hints, idiomatic Python
- `/everything-claude-code:security-review` — secrets, injection, XSS via RSS content

Fix all CRITICAL and HIGH issues before committing. Address MEDIUM when possible.

### Session Management
- Save session at end of every session: `/everything-claude-code:save-session`
- Resume at start of next session: `/everything-claude-code:resume-session`
- Update `.planning/STATE.md` with what changed and what's next

---

## 3. Agent Routing Table (ECC — 18 agents)

Use **parallel agent execution** for independent tasks. Never run sequentially when agents don't depend on each other.

| Task | Agent | Model | When to Use |
|------|-------|-------|-------------|
| Planning any feature | `/everything-claude-code:plan` | Opus | BEFORE writing any code — read-only, waits for "yes" |
| Architecture decisions | `/everything-claude-code:architect` | Opus | Multi-file refactoring, design patterns |
| Security analysis | `/everything-claude-code:security-review` | Sonnet | Before EVERY commit; after auth/API/input code |
| TDD workflow | `/everything-claude-code:tdd` | Sonnet | New features, bug fixes — write tests FIRST |
| Python code review | `/everything-claude-code:python-review` | Sonnet | After any Python changes |
| Build/runtime errors | `/everything-claude-code:build-error-resolver` | Sonnet | When tests or scripts fail |
| Dead code cleanup | `/everything-claude-code:refactor-cleaner` | Sonnet | Code maintenance, before major refactors |
| Documentation | `/everything-claude-code:doc-updater` | Haiku | After API or interface changes |

### Orchestrated Workflows (run full chains)
```
# New feature (full pipeline):
/orchestrate feature "add topic clustering to digest stories"
# Runs: planner → tdd-guide → code-reviewer → security-reviewer

# Bug fix:
/orchestrate bugfix "fix malformed RSS handling"
# Runs: planner → tdd-guide → code-reviewer

# Security audit:
/orchestrate security "audit HTML output for XSS via RSS content"
# Runs: security-reviewer → code-reviewer → architect
```

---

## 4. Token Optimization (CRITICAL)

**Strategy**: Right-size the model to the task. Every wasted Opus call is ~20x the cost of Haiku.

### Model Selection

| Model | When to Use | Cost |
|-------|-------------|------|
| **Haiku 4.5** | File reads, grep searches, simple bash commands, list operations, doc updates | Cheapest |
| **Sonnet 4.6** | Code implementation, unit tests, code reviews, bug fixes, pipeline edits | Default |
| **Opus 4.6** | Complex architecture, security audits, multi-file refactoring strategy, research | Most expensive |

### Rules
- Keep active MCPs ≤10 (too many shrinks your effective context window)
- Avoid last 20% of context window for large refactoring — start fresh subagent
- Use parallel `Task` execution for independent operations — never run sequentially when not needed
- Plan before coding to reduce iteration (fewer round-trips = fewer tokens)
- Haiku for exploratory reads; Sonnet once you know what to change

### Context Bridging
When a session grows long, pass state via files — not conversation:
- `.planning/STATE.md` — what was decided, what's next, what failed
- Update this at the end of every session before `/save-session`

---

## 5. Code Standards

### Immutability (CRITICAL)
**Never modify existing objects. Always create new copies.**

```python
# WRONG — mutates in place
def add_category(digest, story, cat):
    story["category"] = cat  # ❌
    return digest

# CORRECT — returns new copy
def add_category(digest, story, cat):
    new_story = {**story, "category": cat}  # ✓
    return digest
```

### File Organization
- Target: **200–400 lines** per file (max 800)
- One responsibility per file — high cohesion, low coupling
- Group by feature/domain, not by type
- If `generate_digest.py` exceeds 800 lines, split into:
  - `scripts/fetcher.py` — RSS fetching
  - `scripts/renderer.py` — HTML rendering
  - `scripts/claude_client.py` — API calls

### Error Handling (never swallow errors)
```python
# GOOD
try:
    digest = call_claude(articles, archive_context)
except anthropic.APIError as e:
    print(f"ERROR: Claude API call failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Unexpected failure: {e}")
    raise
```

### Input Validation (at every boundary)
```python
# GOOD — validate at startup, fail fast
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY environment variable not set")
    sys.exit(1)

# GOOD — validate external API responses
if not isinstance(digest, dict) or "global" not in digest:
    raise ValueError(f"Unexpected Claude response structure: {type(digest)}")
```

### No Hardcoded Secrets
- **NEVER** hardcode API keys, tokens, or credentials
- Use `.env` file locally (see `.env.example`)
- Validate required env vars at script startup
- Check: `grep -rn "sk-ant" scripts/` before every commit

---

## 6. UI/UX Standards for index.html (from ui-ux-pro-max-skill)

Apply these rules whenever modifying the HTML output template in `generate_digest.py`.

### Non-Negotiable Rules
- **Contrast**: Primary text ≥4.5:1, secondary text ≥3:1 — test BOTH light and dark modes
- **Touch targets**: Story cards and buttons must be ≥44×44pt with 8px+ spacing
- **Icons**: SVG-based only (no emoji as structural UI elements)
- **Animation**: Card expand/collapse within 150–300ms; respect `prefers-reduced-motion`
- **Mobile-first**: Design for 375px first; verify no horizontal scroll
- **RTL**: Arabic text direction, Arabic-Indic numerals (`ar()` function), Cairo font

### Hard Anti-Patterns to Avoid
- Removing focus rings (breaks keyboard navigation)
- Placeholder-only form labels (WCAG violation)
- Animating `width`/`height` — use `transform` instead (performance)
- Mixing flat and glassmorphism styles randomly
- Text < 12px for Arabic body text
- Gray-on-gray contrast (fails WCAG in dark mode)

### Pre-Delivery HTML Checklist
- [ ] All interactive elements ≥44×44pt with visible press feedback
- [ ] Contrast ≥4.5:1 in light AND dark modes
- [ ] No emoji as structural icons; SVG only
- [ ] Card animations within 150–300ms with natural easing
- [ ] Mobile, landscape, and tablet layouts verified
- [ ] Reduced-motion supported via CSS media query
- [ ] Arabic text direction and numerals correct
- [ ] Semantic color tokens used consistently (CSS variables)

---

## 7. Test-Driven Development

### Requirements
- **Minimum 80% coverage** for all code; 100% for security-sensitive functions
- Unit tests: individual utility functions (`strip_html`, `extract_json`, `safe`, `ar`)
- Integration tests: Claude API calls (mocked), archive loading, feed fetching
- Never skip tests to save time — if it's in the code, it needs a test

### Workflow
1. Write test first (RED — MUST fail)
2. Run `python -m pytest tests/ -v` — confirm failure
3. Implement minimal code (GREEN)
4. Run tests again — confirm pass
5. Refactor (IMPROVE — no behavior change)
6. Check coverage: `pytest tests/ --cov=scripts --cov-report=term-missing`

### Testing Tools
- **pytest** — test runner
- **pytest-mock** — mocking fixtures for API/file I/O
- **pytest-cov** — coverage reporting
- **responses** — mock HTTP for RSS feed tests

### Example
```python
# tests/test_generate_digest.py
import pytest
from scripts.generate_digest import strip_html, safe, ar, extract_json

def test_strip_html_removes_tags():
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"

def test_strip_html_empty_input():
    assert strip_html("") == ""
    assert strip_html(None) == ""

def test_safe_escapes_html_attributes():
    assert "&" not in safe("cats & dogs")
    assert '"' not in safe('say "hello"')

def test_ar_converts_ascii_to_arabic_indic():
    assert ar(123) == "١٢٣"

def test_extract_json_parses_valid_json():
    response = '```json\n{"global": [], "local": []}\n```'
    result = extract_json(response)
    assert result == {"global": [], "local": []}

def test_extract_json_raises_on_invalid():
    with pytest.raises(ValueError):
        extract_json("not json at all")
```

---

## 8. Commit Conventions

```
<type>: <description>

<optional body explaining why, not what>
```

### Types
- `feat:` — new feature
- `fix:` — bug fix
- `test:` — add/update tests
- `docs:` — documentation only
- `refactor:` — restructuring (no behavior change)
- `perf:` — performance improvement
- `ci:` — CI/CD pipeline changes
- `chore:` — dependencies, tooling, config

### Examples
```
feat: add topic clustering to de-duplicate similar stories
fix: handle empty RSS feed response gracefully
test: add unit tests for extract_json edge cases
refactor: split generate_digest.py into fetcher/renderer modules
perf: reduce Claude tokens by compressing archive context
ci: add mypy type checking to CI pipeline
```

**Commit early and often.** Each logical unit of work gets its own commit. This enables precise `git bisect` and clean PR review.

---

## 9. Pipeline Architecture Reference

### File Structure
```
Sovereign-News-Curator/
├── scripts/
│   └── generate_digest.py         # Main pipeline (RSS → Claude → HTML)
├── tests/
│   ├── __init__.py
│   └── test_generate_digest.py    # Unit tests (16+ tests, 80%+ coverage)
├── archive/
│   └── YYYY-MM-DD.json            # 3-day headline history
├── .planning/                     # GSD planning artifacts (gitignored optional)
│   ├── PROJECT.md                 # Project context snapshot
│   ├── STATE.md                   # Current state + what's next
│   └── {N}-CONTEXT.md             # Per-feature decisions
├── .env.example                   # Secret template (committed)
├── .env                           # Actual secrets (GITIGNORED)
├── .claude/
│   └── settings.json              # Token optimization settings
├── index.html                     # Generated web app
├── manifest.json                  # PWA config
├── CLAUDE.md                      # This file
├── requirements.txt               # Python dependencies
└── .github/
    └── workflows/
        ├── daily-digest.yml       # Scheduled news generation
        └── ci.yml                 # PR test runner (coverage gate)
```

### Key Functions in `generate_digest.py`

| Function | Purpose | Priority |
|----------|---------|----------|
| `fetch_feed(feed)` | Fetch and parse one RSS feed | Core |
| `fetch_all_feeds()` | Parallel fetch of 18 feeds | Core |
| `load_archive()` | Load 3-day context window | Core |
| `call_claude(articles, archive_context)` | Send to LLM, extract JSON | Core |
| `build_html(digest, generated_at, article_count)` | Render HTML page | Core |
| `strip_html(text)` | Remove HTML tags from RSS summaries | Utility — **test** |
| `extract_json(text)` | Parse JSON from Claude response | Utility — **test** |
| `safe(text)` | HTML-escape strings (XSS prevention) | Utility — **test** |
| `ar(n)` | Convert ASCII digits to Arabic-Indic | Utility — **test** |
| `build_story_cards(stories, section_id)` | Generate HTML cards | Utility — **test** |
| `build_toc(digest)` | Generate table of contents | Utility — **test** |
| `get_categories(digest)` | Extract unique categories | Utility — **test** |
| `count_words(digest)` | Calculate reading time | Utility — **test** |

### Daily Digest CI/CD

1. **Trigger**: 06:00 UTC daily (or manual dispatch)
2. **Checkout**: Clone repo with latest code
3. **Setup**: Python 3.12 + `pip install -r requirements.txt`
4. **Generate**: `python scripts/generate_digest.py`
5. **Commit**: Auto-commit `digest: YYYY-MM-DD HH:MM UTC`
6. **Push**: GitHub Bot → GitHub Pages live

### System Prompt Directive for Claude

- **Role**: Elite defensive AI reading agent
- **Task**: Categorize → deduplicate → extract consensus → identify spin → de-sensationalize
- **Output**: Strict JSON with `global` and `local` arrays (Arabic)
- **Constraint**: No hallucinated quotes, dates, or URLs — only facts from provided sources

---

## 10. Security Checklist (MANDATORY before every commit)

- [ ] `ANTHROPIC_API_KEY` only via `os.environ.get()` — never hardcoded
- [ ] RSS content HTML-escaped before insertion into `index.html` (XSS via `safe()`)
- [ ] Archive JSON validated before loading (never trust file content)
- [ ] No `print()` statements leaking internal paths or API responses
- [ ] GitHub Actions secrets not referenced in committed files
- [ ] `index.html` does not embed API keys even in comments
- [ ] No PII in archive JSON (headlines only, no user data)

---

## Development Checklist

Before every commit:
- [ ] Tests written first (RED), implementation passes (GREEN), refactored (IMPROVE)
- [ ] 80%+ coverage: `pytest tests/ --cov=scripts --cov-report=term-missing`
- [ ] No hardcoded secrets: `grep -rn "sk-ant\|ANTHROPIC_API_KEY\s*=" scripts/`
- [ ] Functions <50 lines, files <800 lines
- [ ] Error handling on all I/O and external calls
- [ ] PEP 8 compliance: `/everything-claude-code:python-review`
- [ ] Security audit: `/everything-claude-code:security-review`
- [ ] UI/UX checklist if `index.html` template changed
- [ ] Conventional commit message
- [ ] `.planning/STATE.md` updated with what changed

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
# Discuss → Plan (.planning/) → TDD (red/green/improve) → Verify → Commit
```

---

## Resources & Integrated Repos

| Repo | Purpose | Key Contribution |
|------|---------|-----------------|
| `gsd-build/get-shit-done` | Phase-based workflow | `.planning/` artifacts, discuss→plan→execute→verify cycle |
| `affaan-m/everything-claude-code` | 18 agents, 94 skills | Agent routing, `/orchestrate`, token optimization, session management |
| `nextlevelbuilder/ui-ux-pro-max-skill` | UI/UX patterns | HTML output standards, accessibility rules, Arabic/RTL guidelines |
| `hesreallyhim/awesome-claude-code` | Best practices catalog | Hook patterns, session continuity, multi-agent orchestration |

- **Test Framework**: https://docs.pytest.org
- **Conventional Commits**: https://www.conventionalcommits.org
- **Python Style**: PEP 8 (https://pep8.org)
- **GitHub Actions**: https://docs.github.com/en/actions
