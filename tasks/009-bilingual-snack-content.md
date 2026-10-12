# 009 — Bilingual, snack-sized content

## Goal
The owner wants a "fast-food" issue in **English and Simplified Chinese** (two separate language versions), livelier than now. This task changes the **content** only; task 010 changes the website and Discord.

## Scope
1. **Item content** (summarise step, one LLM call per item as now, same model): the output schema gains:
   - `emoji`: one emoji that fits the item (single grapheme).
   - `zh`: `{headline, summary, why_it_matters, for_builders}` in Simplified Chinese, written from the same SOURCE (not a word-for-word translation; natural Chinese a developer would write). Product names, model names and version numbers stay in their original form.
   - English fields stay as they are. `summary` (both languages) is now the **one-line takeaway**: ≤ 25 English words / ≤ 50 Chinese characters. Headline limits: English `issue.max_headline_chars`, Chinese ≤ 40 characters.
   - Tone (prompt): friendly, punchy, plain; written for someone scrolling on a phone. No hype words ("revolutionary", "game-changer", "重磅", "炸裂"), no exclamation marks, no emoji inside text fields.
   - Same rules as before: only facts from SOURCE; `supported=false` when too thin.
2. **Validation**: every number check, empty-field check and length limit applies to the `zh` fields too (Chinese length counted in characters). `emoji` must be non-empty and short (≤ 2 code points plus variation selectors/ZWJ sequences). If after the retry the only problem is the length of a headline, shorten deterministically as for English (Chinese: cut to the limit, no dangling punctuation).
3. **Sixty seconds**: produce 3 bullets in English and the matching 3 in Chinese (`sixty_seconds` and `sixty_seconds_zh`), same item references and number checks; fallback uses the top items' headlines in each language.
4. **Image**: add `image_url` (str | None) to `Item`, from the source only:
   - web pages: `og:image` / `twitter:image` from the HTML already fetched for source text (absolute-ised, http/https only);
   - GitHub repos and releases: `https://opengraph.githubassets.com/1/{owner}/{repo}`;
   - Hugging Face and anything without an image: None.
   Never let the LLM produce URLs.
5. **Models/config**: `Item` gains `emoji`, `zh` (dict or None), `image_url`; `Issue` gains `sixty_seconds_zh`. Old issue JSON without these fields must still load (defaults None/empty). Config gains `tagline_zh: "每周 AI 与开发者工具速览，一分钟看完。"`, a `title_zh` per section (models "新模型与实验室", tools "Agent 与开发工具", github "GitHub 热门", quick "快讯"), and `tags_zh` (builders "🛠️ 开发者", work "💼 工作效率", beginner "🌱 新手友好"). Validate them.
6. Keep the token budget reasonable: raise `max_tokens` for the summarise call only as needed.

## Files
weekly_diff/{models,config,summarise,validate,sixty,source_text,build}.py, weekly_diff/prompts/{summarise,sixty}.md, config.yaml, tests/fixtures/config.yaml, tests (+ fixtures).

## Acceptance criteria
- FakeLLM end-to-end build produces items with `emoji`, full `zh` fields and `image_url` where the fixture page has og:image; `sixty_seconds_zh` has 3 bullets.
- Validator rejects: an invented number in a Chinese field, an empty `zh.summary`, a Chinese headline over 40 characters (then shortened if it's the only problem), a missing emoji.
- The committed issue `data/issues/2026-42.json` (old format) still loads and renders with the current site code.
- No real network or API calls in tests. All tests pass.

## Test command
`.venv/bin/python -m pytest -q`
