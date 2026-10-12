# 003 — Dedupe, seen.json, LLM module, scoring and selection

## Goal
Turn raw candidates into a ranked, de-duplicated shortlist assigned to the four sections, using one swappable LLM module.

## Scope
1. **`weekly_diff/urls.py`**: `canonical_url(url)`: https, lowercase host without `www.`, no fragment, drop `utm_*`, `ref`, `source`, `fbclid`, `gclid` query params, sort remaining params, strip trailing slash except root; `domain_of(url)`; `is_primary(url, primary_domains)` (subdomains count).
2. **`weekly_diff/seen.py`**: file format `{"version": 1, "items": {key: {"issue", "url", "title", "first_seen"}}}`. `load_seen`, `is_seen(seen, key, url, current_issue)` (true if the key **or** canonical URL was recorded under a **different** issue, so re-running a week is idempotent), `mark_seen(seen, items, issue_id, today)`, `prune(seen, retention_days, today)`, `save_seen` (sorted keys, 2-space indent, trailing newline).
3. **`weekly_diff/dedupe.py`**: `dedupe(candidates, cfg, seen, issue_id) -> list[Candidate]`:
   - merge candidates with the same canonical URL (keep the primary source's title/text, merge signals by max, keep `extra.also_seen_on` source names);
   - merge near-duplicate stories: lowercase title words minus stopwords, Jaccard ≥ `dedupe.title_similarity`, published within 3 days → keep the primary-domain one, else the one with higher signals;
   - collapse Hugging Face variants: same author and same family (model name with size/quant/format suffixes like `-7B`, `-Instruct`, `-FP8`, `-GGUF`, `-AWQ`, `-Base` removed) → keep the most-liked, list the others in `extra.variants`;
   - drop anything `is_seen`.
4. **`weekly_diff/llm/`** — the only place that knows about providers:
   - `base.py`: `LLMClient` protocol with `complete_json(system: str, user: str, schema: dict, max_tokens: int) -> dict`; `LLMError`, `LLMNotConfigured`.
   - `__init__.py`: `get_client(cfg) -> LLMClient`. `provider: auto` → Anthropic if `ANTHROPIC_API_KEY` is set, else OpenAI if `OPENAI_API_KEY` is set, else raise `LLMNotConfigured("Set ANTHROPIC_API_KEY or OPENAI_API_KEY")`. Explicit provider without its key → same error.
   - `anthropic_client.py`: official `anthropic` SDK. `client.messages.create(model=cfg.llm.anthropic_model, max_tokens=…, system=system, messages=[{"role": "user", "content": user}], output_config={"format": {"type": "json_schema", "schema": schema}, "effort": cfg.llm.effort})`; parse the first text block with `json.loads`. Do **not** send `temperature`, `top_p` or `thinking` (Haiku 5.5 rejects non-default sampling; effort controls depth). If `stop_reason` is `"refusal"` or `"max_tokens"`, raise `LLMError`. Schemas must set `additionalProperties: false` and list `required`. Catch SDK errors most-specific-first (`RateLimitError`, `APIStatusError`, `APIConnectionError`) and re-raise as `LLMError` without echoing request content.
   - `openai_client.py`: official `openai` SDK with strict JSON-schema structured output (Responses API `text.format` or Chat Completions `response_format`), `reasoning.effort = cfg.llm.effort`, no temperature. Same error mapping.
   - `fake.py`: `FakeLLM` returning queued or function-generated responses and recording calls; used by all tests.
   - Log model name and token usage per call (never prompt or response text).
5. **`weekly_diff/score.py`**: `score(candidates, cfg, llm) -> list[Scored]`:
   - heuristic pre-score (primary +2, log-scaled `hn_points`, `stars_gained`, `likes`, `release_count`, recency) and keep the top `llm.max_candidates_to_score`, but always keep the top 10 GitHub trending candidates by `stars_gained`;
   - batches of `llm.score_batch_size`; per candidate send id, title, source name, domain, signals and the first 300 chars of text;
   - output schema: `{"items": [{"id", "relevant": bool, "section": models|tools|github|quick, "tag": builders|work|beginner, "score": 0–10 integer, "reason": ≤20 words}]}`;
   - prompt in `weekly_diff/prompts/score.md`: audience (builders, professionals, beginners); favour new models and major updates from the listed labs, significant agent/dev-tool releases, useful open-source repos; penalise funding/partnership/marketing-only news, opinion pieces and rumours;
   - hard section rules override the LLM: github_trending → github, github_release → tools, huggingface → models;
   - unknown ids ignored, missing ids → not relevant; invalid JSON → one retry, then `LLMError`.
6. **`weekly_diff/select.py`**: `select(scored, cfg) -> Selection` with `chosen: dict[section, list[Scored]]` and `backups: dict[section, list[Scored]]`. Only `relevant` and `score >= llm.min_score`. GitHub section ordered by `stars_gained` desc; other sections by score then signals. Fill each section to `min`, then add the best remaining up to each `max` while total ≤ `issue.max_items`; top up `quick` from leftovers until `issue.min_items` if possible. If total < `issue.hard_min_items`, raise `InsufficientItems`. Save to `build/selection.json`.

## Files
weekly_diff/{urls,seen,dedupe,score,select}.py, weekly_diff/llm/{__init__,base,anthropic_client,openai_client,fake}.py, weekly_diff/prompts/score.md, tests/test_{urls,seen,dedupe,score,select,llm}.py, fixtures as needed.

## Acceptance criteria
- Canonicalisation, merge, near-duplicate, HF-variant and seen-filter cases each have a test, including "same item re-run in the same issue is not dropped".
- Provider selection tests via monkeypatched env (no key → `LLMNotConfigured`). Provider clients tested with the SDK client mocked: correct model, `output_config`/structured-output parameters present, no temperature, refusal → `LLMError`.
- Selection respects min/max per section, total cap, GitHub ordering by stars gained (not total stars), and `InsufficientItems`.
- No test calls a real API. All tests pass.

## Test command
`.venv/bin/python -m pytest -q`
