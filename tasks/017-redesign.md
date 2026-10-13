# 017 — Full redesign: layout, visual theme, interaction

The owner reviewed the live site and finds it cheap-looking. Treat this as a real web product. Rebuild templates and CSS from scratch to the spec below; keep the data model, URLs, both languages and all tests' behaviours (update tests that assert old markup).

## What is wrong now (from Claude's review of the live page)
- Blue-grey dark default, cards with a thin purple top line, huge emoji, GitHub OpenGraph images taking half a card, clunky "展开" buttons, an orphan card in the 2-column grid → looks like a template, not a publication.
- "60 秒速览" is a block of underlined blue links.
- Header links tiny; title, date and count crammed together; no hierarchy.

## References to copy (Codex cannot browse; these are described exactly)
- **TLDR newsletter issue pages** (tldr.tech/ai/<date>): a single reading column; section header = emoji + uppercase label; each story = **bold title that is the link** + muted "(source · N min read)" + one short paragraph; thin dividers; no cards, no images. → copy this list structure for items.
- **Linear changelog** (linear.app/changelog): very large whitespace; a left rail with the date (small, muted, with an accent dot) and the content column on the right; big confident headline (48 px, tight letter-spacing); near-black background in dark mode, pure neutrals; one accent colour. → copy this for the issue header and desktop layout.
- **Vercel / Geist style**: neutral greys, 1 px hairline borders, 8 px radius, monospace for code/model IDs. → copy for details.

## Design spec
**Theme**: light is the default and the primary design (paper `#FBFBF9`, ink `#111111`, muted `#6B6B6B`, hairline `#E7E5E0`); dark via `prefers-color-scheme` **and** a toggle (near-black `#0A0A0A`, ink `#EDEDED`, muted `#9A9A9A`, hairline `#232323`). One accent `#FF5A1F` (orange) used only for: the date dot, numbers in the highlights list, link hover, focus ring. Section markers use the accent too — no per-section rainbow.
**Type**: `-apple-system, "Inter", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", sans-serif`; mono `ui-monospace, "SF Mono", Menlo, monospace`. Scale: issue title 44/48 px (mobile 32), section label 13 px uppercase tracking .08em, item title 19 px semibold, body 16 px (zh 16 px with line-height 1.75, en 1.6), meta 13 px muted.
**Layout**: max content width 680 px. ≥ 1100 px: two-column grid `200px 680px` — left rail holds the issue label ("第 42 期 / Issue 42"), date range, item count, and a small section index (sticky); right column holds content. Below 1100 px: single column, rail content moves above the title. Vertical rhythm: 96 px between sections on desktop, 64 px mobile.
**Header bar**: 64 px, hairline bottom border, wordmark "The Weekly Diff" (semibold 17 px) left; right: 本期 · 往期 · RSS, a segmented `EN | 中文` control, theme toggle icon. Mobile: same row, nav collapses to 往期 + language + theme.
**Highlights** ("本周要点 / This week"): replaces the 60-second box. Numbered 1–3 with large accent numerals, plain ink text (not links); a small "→" at the end of each line links to the item anchor. No box background; a hairline above and below.
**Items** (TLDR-style list, no cards): a small 28 px rounded-square emoji tile on the left (subtle hairline, no colour fill), then: title (link to source, ink colour, underline on hover only) + meta line `github.com · 🚀 马上能试` in muted text; one-sentence takeaway in body text; then, always visible and compact, "值得看：…" and "上手：…" lines in 15 px muted text with the label in ink. Model IDs / commands in inline mono chips. GitHub items add "本周 +N ★" in the meta line. Hairline divider between items. **Remove all thumbnails** from item lists (keep `image_url` for Open Graph / Discord only).
**Footer**: hairline top, three short lines (about, update schedule, RSS links), plus the past-issues list.
**Past issues**: on the home page below the issue, "往期" as a compact timeline (left: date with accent dot, right: issue label + first highlight). Archive page: same component grouped by month.

## Interaction
- Remove `<details>` expanders entirely (everything compact and visible).
- Theme toggle: ≤ 20 lines of inline JS, respects system preference by default, stores choice in localStorage with try/catch, no flash (set `data-theme` in a head script). Without JS the site still works (system theme).
- Language switch keeps the reader on the same page and scroll anchor where possible.
- Smooth scroll to anchors (`scroll-behavior: smooth`, disabled under `prefers-reduced-motion`); anchors offset for the header (`scroll-margin-top`).
- Visible focus ring (2 px accent); hover only changes underline/colour — no movement, no shadows.
- "↑ 回到顶部 / Back to top" at the end of the issue.

## Discord (match the new voice)
Single clean embed per language: title `The Weekly Diff · 第 42 期`, description = the 3 highlights numbered, then top items as `**{title}** — {takeaway} [原文](url)` lines (no fields grid), footer "每周一 08:00 更新". Accent colour `#FF5A1F`. Keep all limits/routing/escaping.

## Done means
- All pages (home, issue, archive, 404, both languages) rebuilt to this spec; no thumbnails in lists; no `<details>`.
- Home HTML+CSS+JS < 50 KB. Contrast ≥ 4.5:1 in both themes (test). Tests updated; `.venv/bin/python -m pytest -q` passes; `.venv/bin/python run.py render` exits 0.
- Do not touch `publish_enabled`. Report + COLLAB-LOG entry. Do not commit or push (Claude reviews in a browser and commits).
