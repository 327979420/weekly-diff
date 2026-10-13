# 018 — Editorial copy (less mechanical) and same-product dedupe

Run after 017. Prompts, validation and dedupe only.

## Problem
Copy reads like a template: almost every takeaway starts with "你可以用它…" / "You can use it to…". The owner wants copy that respects the reader's experience. Also the 2026-42 issue shows "EmbeddingGemma 2" twice (from Hugging Face and from a blog post).

## Voice (put in the summarise and highlights prompts, both languages, with these examples)
- Write like a sharp tech editor briefing a friend: lead with the most interesting concrete fact, then the payoff. Vary sentence shapes.
- Headline = subject + action + the hook: "Docker 推出 Agent：一份 YAML 就能跑起 AI 助手" / "Docker Agent runs AI assistants from one YAML file".
- Takeaway (one sentence): the concrete detail that makes it worth a look. Second person only when it's genuinely natural; **no more than 2 takeaways per issue may start with "你可以" / "You can"** and never two in a row.
- 值得看 / Why it's worth a look: the practical angle for a vibe coder (cost, speed, what it unlocks), not a generic "this matters because".
- 上手 / Try it: an imperative with something concrete: a command, model ID, button, URL target from the source.
- Banned: 赋能、助力、重磅、炸裂、全面升级、一站式、"这意味着", "game-changer", "revolutionary", "unlock the power", exclamation marks.
- Bad → good examples:
  - ✗ "你可以用它把技术概念做成能互动的机器图。" ✓ "把一个技术概念画成会动的机器，每个零件背后都是一个真的小模型。"
  - ✗ "You can use it for summaries and high-volume jobs." ✓ "Haiku 5.5 runs about 75% cheaper than 4.5 — built for bots and bulk summaries."

## Validation
- Issue-level check after summarising: count takeaways starting with 你可以 / You can (and the same first 4 characters/words in general). If more than 2, regenerate the extra ones once with a note "vary the opening; do not start with …"; if still repeated, keep (don't drop).
- Banned-phrase check (both languages) → retry once, then strip the phrase if it's the only problem.

## Dedupe
- Before summarising, merge selected candidates that refer to the same product/model: normalise names (lowercase, strip org prefixes like `google/`, version separators, "-GGUF" etc.) and compare product tokens; if two candidates share the product name + version (e.g. "embeddinggemma 2"), keep the primary-source one (official blog/org over others) and merge signals. Add a final guard in `validate_issue`: no two items whose normalised product names match.
- Tests with the EmbeddingGemma 2 case (HF `google/embeddinggemma-2` + a Google blog post).

## Done means
Tests for opening-variety retry, banned phrases, product dedupe; `.venv/bin/python -m pytest -q` passes. Report + COLLAB-LOG entry. No commit/push. Don't touch `publish_enabled`.

## Design follow-ups from Claude's browser review of 017 (do these too)
1. **Theme toggle bug**: with the system in dark mode, the first click sets `dark` (no visible change); a second click is needed. The toggle must always switch to the opposite of the theme currently displayed (resolve "system" first).
2. **Issue page title**: the H1 repeats the wordmark "The Weekly Diff". Make the H1 the issue: "第 42 期" / "Issue 42"; put "THE WEEKLY DIFF" as a small uppercase kicker above it. Keep the wordmark in the header bar.
3. **Date range**: "2026年10月6日–2026年10月13日" → "10月6日 – 13日 · 2026" (zh) / "Oct 6 – 13, 2026" (en); handle ranges across months/years.
4. **Link hover/text accent contrast**: in light mode use `#C2410C` for any accent-coloured text (hover links); keep `#FF5A1F` for large numerals, dots and the focus ring (non-text, ≥ 3:1).
5. **Shortened text must end on a full sentence**: highlights and takeaways that get shortened may only be cut at a sentence end (。！？. ! ?); if no sentence end fits, regenerate once, then use the first full sentence. Never end on "，" or mid-clause (the live highlight 3 ends "…如果你要跑很多小任务").
