# 011 — Reader-first, simpler copy

## Goal
The owner finds the items still too hard to read. Rewrite the **writing rules** (prompts + validation), not the pipeline: every item should tell the reader, in simple words, *what this thing does* and *how they can use it*.

## Changes
1. **Headline** (EN + 中文): what it is, in plain words. Name + what it does. Example: "Claude Haiku 5.5: a faster, cheaper small model" / "Claude Haiku 5.5：更快更便宜的小模型".
2. **Summary = the subtitle under the headline** (EN + 中文): written to the reader in second person — what it can do **for you** and how you could use it. Pattern: "You can use it to … — <one concrete benefit from SOURCE>." / "你可以用它……，<来自原文的一个具体好处>。" Examples:
   - EN: "You can use it for bots, summaries and other high-volume jobs, at about 75% lower cost than Haiku 4.5."
   - 中文: "你可以用它做机器人、写摘要、跑大批量任务，成本比 Haiku 4.5 低约 75%。"
   For news that is not a tool (research, policy, company news), say what it means for the reader: "If you … , this means …" / "如果你……，这意味着……".
3. **why_it_matters → "对你有什么用 / Why you'd care"**: one short sentence from the reader's point of view, only facts from SOURCE. **for_builders → "怎么上手 / How to try it"**: one concrete first step (install command, model ID, link target named in SOURCE), or null.
4. **Plain language rules** in both prompts: short sentences; everyday words; explain or avoid jargon (e.g. "embedding model" → "a model that turns text and images into numbers so apps can search them"; "开源权重" → "可以免费下载自己运行"); no acronyms without explanation except well-known product names; Chinese reads like a friend explaining it, not a press release (avoid "赋能、助力、重磅、全面升级").
5. **Validation**: summary must address the reader (EN contains "you"/"your"; 中文 contains "你") — on failure, retry once with that note; all existing fact/number checks unchanged. Update the website and Discord labels for the renamed fields: "Why you'd care / 对你有什么用", "How to try it / 怎么上手" (keep JSON field names unchanged so old issues still load).
6. Update the sixty-second prompt the same way: each bullet says what happened and what it means for the reader, in simple words.

## Files
weekly_diff/prompts/{summarise,sixty}.md, weekly_diff/validate.py, weekly_diff/summarise.py, templates/** and weekly_diff/site.py strings, weekly_diff/discord.py strings, tests.

## Acceptance criteria
- Prompts contain the rules and examples above in both languages.
- Validator test: a summary without "you"/"你" triggers the retry path.
- Labels updated on site (both languages) and Discord; old issues still render.
- All tests pass.

## Test command
`.venv/bin/python -m pytest -q`
