# 015 — Easy history browsing and a polished, professional look (web + Discord)

Run after 014. Both languages throughout.

## History (light, not bloated)
1. **Home** = this week's issue, then a compact "往期 / Past issues" strip: the last 6 issues as small rows (week label, date range, top item emoji + headline), and a "全部往期 / All issues →" link.
2. **Issue pages**: "← 上一期 / Previous" and "下一期 / Next →" links at top and bottom (hidden when none).
3. **Archive**: grouped by month, one compact row per issue (week, date range, 3 emojis of its top items, first 60-second bullet). No cards, no images.
4. Each issue page shows a small "本期 N 条 · 约 1 分钟读完 / N items · 1-minute read".

## Professional, friendly visual polish
5. Consistent design system in CSS custom properties: one type scale, spacing scale, radius, shadow; restrained palette (neutral background, one brand accent, the four section accents used only for small markers/edges). Light and dark both refined; contrast ≥ 4.5:1.
6. Header: wordmark "The Weekly Diff", tagline, language switch and nav (本期 / 往期 / RSS) aligned and sticky-free. Footer: short "每周一更新 · 内容摘自原文，点击原文核实 / Updated every Monday · Summaries from the original sources", RSS links.
7. Cards: tidy alignment of emoji, headline, one-liner, tag pill and "原文 ↗"; consistent heights in the two-column grid; the expand control styled as a clear button.
8. **Images**: never show an empty grey box. Show thumbnails only for GitHub OpenGraph images and sources known to allow hotlinking; otherwise show a neat section-coloured header band with the item emoji. (Config list `site.image_domains_allowlist`, default `opengraph.githubassets.com`.)
9. 60-second box: numbered 1–3, each bullet linking to its item on the page (anchor).
10. Mobile (390 px) first: no horizontal scroll, tap targets ≥ 44 px, readable 16 px+ body.
11. Add a simple favicon (inline SVG emoji or letter mark) and Open Graph image meta using the top item's GitHub image when available.

## Discord polish
12. Cleaner messages: title `📰 The Weekly Diff · 第 42 期` / `📰 The Weekly Diff · Issue 42`; a short date line; 60 seconds as numbered lines; top 5 as fields `"{emoji} {headline}"` with the one-liner, then `马上能试 · [原文](url)` style tag + link on one line; footer text `每周一更新 · weekly-diff` and a final "阅读完整一期 → / Read the full issue →" link; consistent brand colour. Image only from allowed domains (same rule as the website).

## Done means
- Tests for previous/next links, home past-issues strip (max 6), archive grouping by month, image allowlist fallback, Discord layout/limits, both languages.
- Home HTML+CSS still < 60 KB. `.venv/bin/python -m pytest -q` → all pass.
- Do not touch `publish_enabled`. Do not commit or push. Report + COLLAB-LOG entry per AGENTS.md.

## Test command
`.venv/bin/python -m pytest -q`
