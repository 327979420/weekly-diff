# The Weekly Diff — plan

A fully automatic weekly roundup of AI and developer news for an English-speaking public audience (builders, professionals, beginners). The name lives in `config.yaml`.

## Outputs (from the same weekly data)
1. **Discord post** every Monday about 08:00 Melbourne: 60-second summary, top 5 items, link to the full issue.
2. **Website** on GitHub Pages (https://327979420.github.io/weekly-diff/): home = latest issue, `/issues/YYYY-WW/`, `/archive/`, `/feed.xml`. Minimal, fast, mobile-friendly, light/dark, no JavaScript.

## Issue format
10–15 items across: This week in 60 seconds (3 bullets, drawn from the items) · New models & labs · Agent & dev tool updates · Trending on GitHub (by stars gained this week) · Quick hits.
Each item: headline, one plain-English sentence, "Why it matters", optional "For builders", one tag (🛠️ Builders / 💼 Work & productivity / 🌱 Beginner-friendly), source link (required).

## Pipeline
```
collect ──► dedupe ──► score/rank (LLM) ──► select ──► summarise (LLM) ──► validate ──► render site + Discord payload ──► publish
build/candidates.json            build/selection.json          data/issues/YYYY-WW.json, data/seen.json, site/
```
- `run.py collect` — every source module runs independently; failures are logged and skipped (`build/collect-report.json`).
- `run.py build` — dedupe, score, select, summarise, validate, save the issue, mark items seen, render `site/`.
- `run.py render` — rebuild `site/` from `data/issues/` only (no network, no LLM).
- `run.py publish [--preview]` — Discord. `--dry-run` on any command means: no Discord post, no writes to `data/`.
- `run.py status --github-output` — exposes `paused`, `publish_enabled`, `issue_id` to workflows.

## Key rules
- Facts come only from fetched source text; numbers in generated text must appear in the source (validator). Items failing validation are retried once, then replaced by the next candidate.
- Every item links its source; primary sources preferred (config `primary_domains`).
- No repeats across issues: `data/seen.json` (keyed by item key and canonical URL). Re-running the same week replaces that week's issue.
- Issue id = ISO year-week of the run date in UTC. The Sunday 21:00 UTC run therefore publishes the week that just ended; the Friday preview builds the same id.
- LLM: one swappable module (`weekly_diff/llm/`). `provider: auto` uses Anthropic if `ANTHROPIC_API_KEY` is set, else OpenAI. Defaults: `claude-haiku-5-5` (JSON-schema structured output via `output_config.format`, `effort: low`, no temperature) or `gpt-5-mini`. Expected cost: a few cents per week.
- Secrets only from environment variables; logging redacts them.

## Schedule (GitHub Actions, public repo)
| Workflow | When (UTC) | Melbourne | Does |
| --- | --- | --- | --- |
| preview.yml | Fri 09:00 | Fri 20:00 (19:00 in winter) | build, post preview to `DISCORD_PREVIEW_WEBHOOK_URL`, upload site as artifact. Commits nothing. |
| weekly.yml | Sun 21:00 | Mon 08:00 (07:00 in winter, AEST) | build, commit `data/`, deploy Pages, then Discord: public channel if `publish_enabled: true`, otherwise preview channel only. |
| pages.yml | push to main (templates, config, data/issues) | — | re-render and redeploy the site (e.g. after a rename). |
| ci.yml | push / PR | — | tests. |
All scheduled workflows also have `workflow_dispatch` with a `dry_run` option. `paused: true` makes scheduled runs exit early.

## Data layout
- `data/issues/YYYY-WW.json` — published issues (committed by weekly.yml).
- `data/seen.json` — every item ever published, for dedupe.
- `data/stars.json` — weekly star snapshots for repos too large to count via the stargazers API.
- `build/` (ignored) — candidates, selection, collect report, dry-run output. `site/` (ignored) — rendered website.

## Tasks
| # | Task | Status |
| --- | --- | --- |
| 001 | Skeleton, config loader, models, logging, run.py CLI, pytest | done (54 tests) |
| 002 | Collectors (one module per source), fixture tests | done, 1 fix round (115 tests) |
| 003 | Dedupe, seen.json, LLM module, scoring and selection | done (166 tests) |
| 004 | Source text, summariser, validation, build orchestration | done (229 tests; live LLM run pending key) |
| 005 | Static website + RSS | done (240 tests) |
| 006 | Discord sender (preview/publish, publish_enabled) | done (273 tests) |
| 007 | GitHub Actions workflows, Pages deploy, owner README | done (289 tests) |
| 008 | Quality fixes from first dry run (HF repacks, empty quick hits, long headlines) | done (349 tests) |
| 009 | Bilingual (EN/中文) snack-sized content, emoji, source images | done (413 tests) |
| 010 | Colourful bilingual site (/zh/) and two Discord messages | done (422 tests) |
| 011 | Reader-first, simpler copy (what it does + how you can use it) | done (439 tests) |
| 012 | Shared collaboration log (docs/COLLAB-LOG.md) | done |
| 013 | Frozen legacy-issue fixture; Codex session IDs | done (439 tests) |
| 014 | Vibe-coder focus, new sources, try/learn/watch tags | done, 1 fix round (472 tests) |
| 015 | History browsing, visual polish, Discord layout | done (489 tests) |
| 016 | Shorten instead of dropping; realistic zh limits; fill to min_items | done (513 tests) |

## Decisions
- 2026-10-12: Repo at `~/weekly-diff`, GitHub `327979420/weekly-diff` (public). Pages source: GitHub Actions.
- 2026-10-12: Codex delegation via `codex exec -s workspace-write` (plugin installed but not loaded in the director session; `--full-auto` no longer exists in Codex CLI 0.162).
- 2026-10-12: `publish_enabled` gates only the public Discord post. The website updates every week regardless, so the owner can review it before going live.
- 2026-10-12: Tool release feeds use GitHub Releases; Cursor (closed source) uses its changelog RSS. Roo Code dropped (archived). Labs without RSS (Anthropic, Meta, DeepSeek) use the html_index collector; xAI (blocks bots), Qwen, Kimi and GLM are covered by Hugging Face orgs and Hacker News.
- 2026-10-12: GitHub no longer lists stargazers (REST 404 for every repo, GraphQL count 0), so "stars gained this week" = total stars for repos created inside the window, otherwise current − snapshot from `data/stars.json` (closest to 7 days, within 5–9). Snapshots are recorded on every non-dry-run collect and committed weekly; a first snapshot was committed at setup so the first issue can rank established repos too.

## Open issues
- None yet.

## Go-live checklist
1. ✅ (2026-10-12) Owner sets secrets: `gh secret set ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`), `gh secret set DISCORD_WEBHOOK_URL`, optionally `gh secret set DISCORD_PREVIEW_WEBHOOK_URL`.
2. ✅ (2026-10-12) Dry run of weekly.yml succeeds; site artifact looks right (after fixes 003 ×2 and task 008).
3. ✅ (2026-10-12) Real run with `publish_enabled: false`: issue 2026-42 live (14 items, 5 sections), Discord publish job reported `preview`.
4. ⏳ Owner decides to go live → `publish_enabled: true`.
