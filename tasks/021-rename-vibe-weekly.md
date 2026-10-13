# 021 — Rename to "Vibe Weekly" / "Vibe 周刊"

Freddy chose the new name on 2026-10-13: English **Vibe Weekly**, Chinese **Vibe 周刊**.

## Changes
1. config.yaml: `name: "Vibe Weekly"`, add `name_zh: "Vibe 周刊"`, `tagline: "The weekly AI digest for vibe coders."`, `tagline_zh: "给 vibe coder 的每周 AI 工具速览。"` (config.py + fixture config + validation; `name_zh` required).
2. Use the language's name everywhere: header wordmark, kicker above the issue H1, `<title>`, Open Graph, RSS channel titles, 404, footer, and Discord (zh message uses `Vibe 周刊`, en uses `Vibe Weekly`; webhook `username` = the name of the message's language). No hard-coded brand strings anywhere in code or templates.
3. Update README.md and docs/PLAN.md wording to the new name (keep the repo name `weekly-diff` and the site URL `https://327979420.github.io/weekly-diff/` unchanged; say so in README).
4. Favicon/letter mark: "V".

## Done means
Tests updated for both names; a grep for "Weekly Diff" in `weekly_diff/`, `templates/`, `static/`, `config.yaml`, README.md finds nothing (history files under tasks/ and docs/COLLAB-LOG.md stay as they are). `.venv/bin/python -m pytest -q` passes; `.venv/bin/python run.py render` exits 0. Report + COLLAB-LOG entry. No commit/push; don't touch publish_enabled.
