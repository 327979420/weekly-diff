# 008 — Quality fixes from the first real dry run

## Goal
Fix three problems seen in the first GitHub Actions dry run (issue 2026-42, 12 items), without changing anything else.

## Problems and changes
1. **Third-party repacks used as the source.** "Google releases EmbeddingGemma 2" linked to `huggingface.co/unsloth/embeddinggemma-2-GGUF` (a community quantised copy) after the original `google/embeddinggemma-2` was dropped. Change in the Hugging Face collector and/or dedupe:
   - Treat a model as a **repack** when its name ends in or contains a format/quant marker (`GGUF`, `MLX`, `AWQ`, `GPTQ`, `EXL2`, `FP8`, `bnb`, `4bit`, `8bit`) **and** its author is not in `sources.huggingface.orgs`, or when the author is in a new config list `sources.huggingface.repack_authors` (set to: unsloth, bartowski, lmstudio-community, mlx-community, TheBloke, QuantFactory, MaziyarPanahi).
   - Drop repacks from candidates. If the repack's original (same family name) is not already a candidate, do not invent it; just drop the repack.
   - Tests for both rules.
2. **Quick hits section empty.** The issue had models 4, tools 4, github 4, quick 0, although `quick.min` is 2. In `weekly_diff/select.py`, after filling sections: if any section is below its `min`, top it up from the best remaining relevant, `score >= llm.min_score` candidates; for `quick`, eligible leftovers may come from **any** non-github section (reassign their section to `quick`). Same for the backup lists used by task 004's backfill, so a dropped quick item is replaced by another quick-eligible one. Respect `issue.max_items` by removing the lowest-scored item from the largest non-github section if needed. Add a test reproducing models 4 / tools 4 / github 4 / quick 0 with spare relevant candidates → quick ends with ≥ 2.
3. **Good items dropped for long headlines.** Three items were dropped with "headline exceeds 80 characters" (twice after retry). Add `issue.max_headline_chars: 90` to config.yaml (+ fixture config + config.py) and use it in the validator and the summarise prompt. If after the retry the **only** problem is headline length, shorten it deterministically (cut at the last word boundary before the limit, no trailing punctuation fragment) instead of dropping the item. Tests for both.

## Files
weekly_diff/collectors/huggingface.py and/or weekly_diff/dedupe.py, weekly_diff/select.py, weekly_diff/validate.py, weekly_diff/summarise.py, weekly_diff/prompts/summarise.md, weekly_diff/config.py, config.yaml, tests (+ fixtures).

## Acceptance criteria
- The three behaviours above are covered by tests; all tests pass.
- No other behaviour changes.

## Test command
`.venv/bin/python -m pytest -q`
