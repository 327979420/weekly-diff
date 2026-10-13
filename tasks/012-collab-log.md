# 012 — Create the shared collaboration log

## Goal
Create `docs/COLLAB-LOG.md`: a chat-style record of how the owner (Freddy), Claude (director) and Codex (coder) built this project, so Freddy can follow every back-and-forth and any new Codex or Claude session can catch up. Write it in simple Chinese; keep file names, commands and numbers as they are. Documentation only: no code changes.

## Format
- Top: one paragraph explaining what this file is, and how Freddy can add an instruction (append `**Freddy → Claude/Codex**：…`).
- Then one entry per message, oldest first, grouped under date headings (`## 2026-10-12`, `## 2026-10-13`):
  `**🧑 Freddy → Claude**：…` · `**🧠 Claude → Codex**：…` · `**🤖 Codex → Claude**：…` · `**🧠 Claude → Freddy**：…`
- Each entry 1–3 short lines: what was asked/done and the result (test count, accepted / sent back and why). Link the task, report or fix file, e.g. `[tasks/002-collectors.md](../tasks/002-collectors.md)`.
- End with a "当前状态" section: what is live, what is waiting for Freddy (`publish_enabled`), next automatic runs (Fri 16 Oct ~20:00 preview, Mon 19 Oct ~08:00 issue, Melbourne time).

## Sources
Use `tasks/*.md`, `tasks/*-report.md`, the history of the fix files (`git log -p -- tasks/002-fix.md tasks/003-fix.md`, which overwrote earlier versions), `git log --reverse --format='%ad %s' --date=format:'%Y-%m-%d %H:%M'`, and docs/PLAN.md. Things that are not in files, from the director:
1. Freddy asked for "The Weekly Diff": automatic weekly AI/dev news, Discord + website; Codex writes all code, Claude plans and reviews.
2. Claude set up tools (Codex installed into ~/.local), created the repo and Pages, wrote rules, plan, config and tasks 001–007.
3. 002: Codex's tests passed, but Claude's live run found 0 GitHub trending items; Claude found GitHub no longer lists who starred a repo → 002-fix (count stars by weekly snapshots) → accepted, first snapshot of 246 repos saved.
4. 005: Codex could not open a browser; Claude checked the live site later.
5. 006: Claude found the sample issue's top-5 list pointed to an item that did not exist, and fixed it (one line in a test fixture).
6. 007: Claude checked the GitHub Actions versions exist and read the README; CI and Pages deployed; site showed "coming soon".
7. Freddy set the three secrets. Dry run 1: Anthropic rejected the request (400) → 003-fix round 1 (remove unsupported schema rules). Dry run 2: AI calls timed out after 60 s → 003-fix round 2 (180 s timeout). Dry run 3: success, 12 items; Claude found 3 quality problems → task 008.
8. Real run: issue 2026-42 live (14 items, 5 sections), first preview post to the private channel.
9. Freddy asked how Claude and Codex talk, and whether Codex can be used directly; Claude added owner rules to AGENTS.md and gave Freddy a prompt for Codex.
10. Freddy: "不够好，要快餐版，中英文都要，太干太朴素" → chose: separate EN/中文 versions, one line per item + 展开, colourful cards + emoji + images → tasks 009, 010 → real run; Claude checked the Chinese page in a browser; noted OpenAI images show an empty grey box.
11. Freddy: simpler words, and the line under each headline should say what it does and how he can use it → task 011 → issue regenerated.
12. Freddy (2026-10-13): wants to see the Claude ↔ Codex back-and-forth and stay in sync → rule added to AGENTS.md and CLAUDE.md (read this log first, append after every turn) → task 012 (this file).

## Done means
- `docs/COLLAB-LOG.md` exists in the format above, covering every task 001–012 and every fix round, in order.
- Append your own entry for task 012 at the end, per the new rule in AGENTS.md.
- tasks/012-report.md written. Tests still pass.

## Test command
`.venv/bin/python -m pytest -q`
