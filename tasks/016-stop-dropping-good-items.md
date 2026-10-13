# 016 — Stop dropping good items for length; always reach 10 items

## What happened (real run 2026-10-13, Actions run 38347027048)
226 candidates collected, but the issue ended with **7 items** (models 1, tools 2, github 4, quick 0) and the 60-second box fell back to headlines. Log, after retry:
- 5× `zh.for_builders exceeds 60 characters`, 2× `zh.summary exceeds 50 characters` → item dropped, then its backups dropped for the same reason.
- 1× `unsupported number: 11`.
- `Sixty seconds failed validation; using top headlines`.

## Changes
1. **Shorten, don't drop**: if after the retry the only problems are length limits (any text field, either language, including sixty-second bullets), shorten deterministically instead of dropping: cut at the last sentence/clause boundary (。！？；，. ; ,) within the limit, else at a word boundary (EN) / character limit (中文), with no dangling punctuation or half-open brackets, then revalidate. Only fact/number/empty/link problems may drop an item.
2. **Realistic Chinese limits** (config + prompts + validation): `max_summary_chars_zh` 70, `max_why_chars_zh` 100, `max_builders_chars_zh` 90, `max_bullet_chars_zh` 80, `max_headline_chars_zh` 40 (unchanged). Prompts state the limits explicitly in both languages.
3. **Always aim for `min_items`**: if, after backfill, the issue has fewer than `issue.min_items`, run one more selection pass over the remaining relevant candidates with `min_score - 1` (never below 3), filling sections below their `min` first (quick can take any non-github item), then summarise those. Log how many were added this way.
4. **Sixty seconds**: after one retry, shorten bullets per rule 1 instead of falling back to headlines; fall back only on fact/number problems.
5. Tests: zh.for_builders over the limit is shortened (not dropped); a sentence-boundary cut in Chinese and English; under-min issue triggers the extra pass and reaches 10 with fixture candidates; sixty-second bullet shortened instead of fallback.

## Done means
`.venv/bin/python -m pytest -q` → all pass. No change to `publish_enabled`. Report + COLLAB-LOG entry per AGENTS.md. Do not commit or push.
