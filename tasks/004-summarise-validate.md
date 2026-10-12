# 004 — Source text, summariser, validation, build orchestration

## Goal
Write each selected item from its fetched source text only, validate every field, and produce the saved issue. Wire `run.py build`.

## Scope
1. **`weekly_diff/source_text.py`**: `fetch_source_text(candidate, http, max_chars) -> str`:
   - github_trending → README via `GET /repos/{owner}/{repo}/readme` with `Accept: application/vnd.github.raw`, prefixed by the description;
   - github_release → the release bodies already in `candidate.text`;
   - huggingface → `https://huggingface.co/{id}/raw/main/README.md` with YAML front matter removed;
   - anything else → fetch the URL and `extract_main_text`; if that fails or yields < 200 chars, fall back to `candidate.text` (feed content).
   - Truncate to `max_chars` at a paragraph boundary. Return "" if nothing usable (the item is then skipped).
2. **`weekly_diff/summarise.py`**: `summarise(scored, source_text, cfg, llm) -> Item | None`. Prompt in `weekly_diff/prompts/summarise.md`; user message contains the section, title, source name, URL and the SOURCE text. Output schema: `headline`, `summary`, `why_it_matters`, `for_builders` (string or null), `tag` (builders|work|beginner), `supported` (bool). Rules in the prompt: plain English for a mixed audience; use only facts in SOURCE; never add numbers, names, dates, benchmarks or claims not in SOURCE; if SOURCE is too thin, set `supported=false`; headline ≤ 80 chars, no emoji, no clickbait; summary is one sentence ≤ 35 words; why_it_matters ≤ 40 words, explaining relevance using only SOURCE facts; for_builders ≤ 30 words and only when there is something concrete to try or use, else null. `supported=false` → return None. `source_url` is the candidate URL (never LLM output). Copy `stars_gained` and other display signals into `Item.extra`.
3. **`weekly_diff/validate.py`** (pure functions returning a list of problem strings):
   - `validate_item(item, source_text, cfg)`: required fields non-empty; `for_builders` None or non-empty; length limits above; summary is a single sentence; `tag` and `section` valid; `source_url` is http(s); **every number in generated text** (digits, decimals, percentages, money, version strings like `v2.1` or `4.5`) appears in source_text or the candidate title after normalising commas/spaces; no `@everyone`/`@here`.
   - `validate_issue(issue, cfg)`: exactly 3 non-empty sixty-second bullets (≤ 30 words each); item count between `hard_min_items` and `max_items`; no duplicate keys or source URLs; every item valid; `top` has `min(top_items, item count)` existing keys.
4. **Retry and backfill**: an item with problems is regenerated once with the problems listed in the prompt; if it still fails (or is unsupported, or has no source text) it is dropped and replaced by the next backup from the same section, then from `quick`. Log every drop with the reason.
5. **Sixty seconds** (`weekly_diff/sixty.py`): one LLM call over the final items' headline + summary + key; output `{"bullets": [{"text", "item_keys": [...]}] × 3}` covering the most important items; each bullet ≤ 30 words; validate that every number in a bullet appears in the referenced items' text, retry once, then fall back to the headlines of the top 3 items.
6. **Top items**: `top` = the highest-scored items across sections, at most `issue.max_top_per_section` per section, `issue.top_items` total.
7. **`weekly_diff/build.py`**: `run_build(cfg, issue_id, now, dry_run)`: load `build/candidates.json` (error if missing: "run collect first") → dedupe (with seen) → score → select → fetch source text + summarise + validate with backfill → sixty seconds → top → `validate_issue` → save `data/issues/{id}.json` (or `build/dry-run/{id}.json` when dry-run) → unless dry-run, `mark_seen` + `prune` + `save_seen` → call the render hook (`weekly_diff.site.render_site` if it exists; task 005 provides it — guard with a clear log line until then). The issue's `published_at` = now; `period_start/end` from the window. Wire `pipeline.build`.

## Files
weekly_diff/{source_text,summarise,validate,sixty,build}.py, weekly_diff/prompts/{summarise,sixty}.md, weekly_diff/pipeline.py (build), tests/test_{source_text,summarise,validate,sixty,build}.py, fixtures.

## Acceptance criteria
- Validator catches: an invented number, a two-sentence summary, an empty field, a non-http link, a duplicate URL, a bad tag, `@everyone`.
- Summariser test with FakeLLM: first response invalid → retry → valid; persistently invalid → item replaced by a backup; `supported=false` → backup used.
- End-to-end `run_build` test with recorded candidates and FakeLLM produces a valid issue JSON with 10–15 items, 3 bullets and top 5, and updates `seen.json`; dry-run writes to `build/dry-run/` and leaves `data/` untouched.
- Re-running the same issue id overwrites that issue and does not drop its own items as "seen".
- No real network or API calls in tests. All tests pass.

## Test command
`.venv/bin/python -m pytest -q`
