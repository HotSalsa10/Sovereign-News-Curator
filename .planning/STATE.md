# Project State — Last Updated: 2026-03-15

## What's Working
- Full pipeline: RSS → Claude → HTML + version.json → GitHub Pages
- Token optimization: ~$1/month cost (was $2/week)
- **125 unit tests, 99% coverage**
- CI pipeline: ruff, mypy, gitleaks, coverage gate (≥95%)
- PWA: installable, offline, dark/light theme, RTL support
- PWA push notifications: bell opt-in, periodicsync, visibilitychange fallback
- Modular scripts: fetcher, archive, claude_client, renderer, main

## Recently Completed (2026-03-15)
- Modularized generate_digest.py → 5 focused modules
- UI/UX improvements: WCAG contrast fix, sessionStorage category filter,
  reduced-motion support, SVG icons, share API, read-state tracking
- Added build_version_json() + version.json for PWA update detection
- Added sw.js periodicsync + notificationclick handlers
- Full pipeline smoke test (test_smoke_full_pipeline_writes_index_and_version)
- PWA HTML assertions (test_smoke_index_html_is_valid_pwa)
- ruff + mypy already in requirements.txt and ci.yml

## What's Next (backlog)
- (no known open items)

## Known Issues / Watch Points
- Safari/iOS has limited periodicsync support — visibilitychange fallback covers this
- Archive loading uses 3-day window — verify no developing-story context lost

## What NOT to Retry
- Don't increase archive window back to 7 days (cost reason: ~$1/month target)
- Don't add CDN dependencies to index.html (PWA offline requirement)
- Don't use localStorage for auth/secrets (security)
