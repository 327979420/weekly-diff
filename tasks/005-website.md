# 005 — Static website + RSS

## Goal
Render every issue in `data/issues/` into a minimal, fast, accessible static site in `site/` for GitHub Pages. Wire `run.py render` and the build hook.

## Scope
1. **`weekly_diff/site.py`**: `render_site(cfg, issues_dir, out_dir) -> list[Path]`. Loads all issues (newest first), clears and rewrites `out_dir`. Jinja2 `Environment` with `autoescape=True`, `StrictUndefined`, templates from `templates/`.
2. **Output**:
   - `index.html` — latest issue in full, plus links to archive and RSS. Empty state when no issues: "{name} — first issue coming soon."
   - `issues/YYYY-WW/index.html` — one page per issue.
   - `archive/index.html` — all issues, newest first: issue title, date range, first sixty-second bullet.
   - `feed.xml` — RSS 2.0, newest `site.feed_items` issues; title, link, guid (issue URL, isPermaLink), RFC 822 pubDate, description = escaped HTML of the 60-second bullets and item headlines with links. Absolute URLs throughout.
   - `404.html`, `.nojekyll`, `assets/style.css`.
3. **Issue page layout**: header with `name` and `tagline`; "Issue YYYY-WW · {period in site.timezone, e.g. 12–18 Oct 2026}"; "This week in 60 seconds" bullets; one `<section id="{key}">` per config section with its title; per item: headline (`h3`), summary, **Why it matters:** …, **For builders:** … (only if present), tag label from `cfg.tags`, "Source: {domain} ↗" link (`rel="noopener"`), and for GitHub items "+{stars_gained} stars this week" when present. Sections with no items are omitted.
4. **Links**: every internal link uses `cfg.base_path` (site lives at `/weekly-diff/`), e.g. `/weekly-diff/issues/2026-42/`. `<link rel="canonical">`, `<link rel="alternate" type="application/rss+xml">`, `<meta name="description">`, Open Graph title/description/url, `<html lang>` from config.
5. **Design**: system font stack, max width ~42rem, comfortable line height, mobile-first. Light and dark via `prefers-color-scheme` with CSS custom properties; text contrast ≥ 4.5:1 in both. Visible focus styles, skip link, logical heading order. No JavaScript, no web fonts, no external requests, no analytics. Home page HTML+CSS under 50 KB for a 15-item issue.
6. **Wiring**: `pipeline.render` → `render_site(cfg, data/issues, site/)`; the build hook from task 004 calls it (dry-run renders from `data/issues` plus the dry-run issue so the artifact shows the new week).

## Files
weekly_diff/site.py, weekly_diff/pipeline.py (render), weekly_diff/build.py (hook only), templates/{base,home,issue,archive,404}.html, templates/feed.xml, static/style.css, tests/test_site.py, tests/fixtures/issues/*.json (two sample issues).

## Acceptance criteria
- Rendering two fixture issues creates all files above; home shows the newer issue; archive lists both newest first.
- All internal links start with `/weekly-diff/`; feed links are absolute `https://327979420.github.io/weekly-diff/...`.
- A headline containing `<script>alert(1)</script>` is escaped in HTML and in the feed.
- `feed.xml` parses with feedparser and has the right number of entries and dates.
- Empty `data/issues/` renders the coming-soon home page without errors.
- Size check for the home page passes. All tests pass.

## Test command
`.venv/bin/python -m pytest -q`
