# 010 — Colourful, snack-sized website and Discord in English and Chinese

## Goal
Make the website and Discord post quick to scan and lively, with two language versions. Uses the content fields added in task 009.

## Website
1. **Two versions**: English at the current paths; Chinese mirror under `/zh/`: `/zh/`, `/zh/issues/YYYY-WW/`, `/zh/archive/`, `/zh/feed.xml`. A clear `EN | 中文` switch at the top right links to the **same page** in the other language. `<html lang="en">` / `lang="zh-CN"`, `hreflang` alternates on every page. Chinese system font stack (PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, sans-serif).
2. **Missing Chinese** (old issues without `zh`): the Chinese page shows the English text for those fields with a small "本期暂无中文版" note; never crash.
3. **Snack-sized cards**: each item is a card showing: section-coloured edge, the item `emoji` large, headline, the one-line summary, tag pill, "Source ↗ / 原文 ↗" link, "+N ★ this week / 本周 +N ★" for GitHub items. If `image_url` exists, a 16:9 thumbnail (`loading="lazy"`, `referrerpolicy="no-referrer"`, `alt` = headline, fixed aspect ratio so layout doesn't jump). "Why it matters" and "For builders" go inside `<details><summary>More / 展开</summary>` (no JavaScript).
4. **Look**: lively but clean. Each section has an icon and accent colour (models 🧠 violet, tools 🛠️ blue, GitHub ⭐ amber, quick ⚡ green) used for the section header and card edge. A highlighted "This week in 60 seconds / 60 秒速览" box at the top with a contrasting background. Rounded cards, soft shadows, generous spacing, larger headline type, cards in one column on phones and two columns from ~900px wide. Light and dark themes both designed (not just inverted); text contrast ≥ 4.5:1 in both. Still no JavaScript, no web fonts, no external requests except item thumbnails.
5. Archive pages: card list per issue with the first 60-second bullet in that language. Feeds: one per language.
6. Home page HTML+CSS still under 60 KB for a 15-item issue (images excluded).

## Discord
7. Each run posts **two messages** to the same webhook: English first, then Chinese. Each: title `"{emoji of top item} {name} — Issue YYYY-WW"` (Chinese: `"… — 第 WW 期"`), the 60-second bullets in that language, top items as fields named `"{emoji} {headline}"` with the one-line summary and `[Source](url)` / `[原文](url)`, final link to that language's issue page, and `embed.image` = the top item's `image_url` when present. Preview/public routing, `publish_enabled`, limits, escaping, mentions and dry-run behave exactly as now for both messages. If the second message fails, report it but do not resend the first.

## Files
weekly_diff/site.py, templates/** (add Chinese strings via a small per-language strings dict, not duplicated templates), static/style.css, weekly_diff/discord.py, tests/test_site.py, tests/test_discord.py (+ fixtures).

## Acceptance criteria
- Rendering fixture issues (one with `zh`, one old-format) creates both language trees; every page links to its counterpart; `/zh/` pages use Chinese strings, `lang="zh-CN"` and Chinese content when present, English fallback with the note when absent.
- Item cards: details element present, thumbnail only when `image_url` exists, escaping still enforced (script-in-headline test for both languages).
- Discord tests: two payloads in order, Chinese titles/links/fields, `embed.image` set from the top item, routing tests pass for both messages.
- All tests pass.

## Test command
`.venv/bin/python -m pytest -q`
