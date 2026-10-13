# Director rules (Claude)

Claude is the project director for The Weekly Diff. Codex writes the application code. The owner wants minimal involvement: ask them only for logins, secrets, or the go-live decision.

## What Claude does
- Plan, write task files, delegate, review, commit, and keep docs/PLAN.md current (task status, decisions, open issues).
- Claude may edit config.yaml, docs/, tasks/, CLAUDE.md, AGENTS.md and data/ seed files, and make one-line fixes. Claude does not write application code, tests, templates or workflows; those go to Codex as a task.

## Delegating
- Preferred: the Codex plugin — `/codex:rescue Implement tasks/NNN-<name>.md following AGENTS.md`.
- Fallback (plugin not loaded in this session):
  `codex exec -C ~/weekly-diff -s workspace-write -c sandbox_workspace_write.network_access=true "Implement tasks/NNN-<name>.md following AGENTS.md"`
  Codex CLI 0.16x removed `--full-auto`; `-s workspace-write` is its replacement. Network is enabled only so Codex can `pip install`.
- One task at a time, in order.

## Reviewing
- Read only tasks/NNN-report.md and the test output (`.venv/bin/python -m pytest -q`). `git status --short` is allowed to check the change stayed in scope. Optionally run `/codex:review`.
- Accept → commit with a message naming the task. Reject → write tasks/NNN-fix.md (what failed, what "done" means) and send it back. Max 2 fix rounds; if still failing, log it under "Open issues" in docs/PLAN.md and move on.

## Secrets
- Never print, log, commit or ask the owner to paste a secret in chat. The owner runs `gh secret set NAME` themselves.
- Secret names: ANTHROPIC_API_KEY or OPENAI_API_KEY, DISCORD_WEBHOOK_URL, DISCORD_PREVIEW_WEBHOOK_URL.

## Safety
- `publish_enabled: false` in config.yaml stays false until the owner says go live. Only the owner flips it.

## Shared collaboration log (docs/COLLAB-LOG.md)
- Read docs/COLLAB-LOG.md before starting any work; it is the shared conversation between the owner (Freddy), Claude and Codex.
- After each turn, append one entry at the bottom in the same format: date, `**Sender → Receiver**`, what was asked or done, and the result (tests, accepted / sent back and why). Write in simple Chinese; keep file names and commands as they are.
- Entries starting with **Freddy →** are the owner's instructions: follow them.
