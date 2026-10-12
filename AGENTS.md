# Rules for Codex

You implement one task file at a time for The Weekly Diff, a fully automatic weekly roundup of AI and developer news. Read docs/PLAN.md for the architecture and config.yaml for settings before you start.

## Scope
- Implement exactly the task you were given (tasks/NNN-*.md). Do not start later tasks, refactor unrelated code, or change config.yaml values unless the task says so (adding new keys a task asks for is fine).
- Do not commit, push, or change git settings. The director reviews and commits.
- Do not edit CLAUDE.md, AGENTS.md, docs/PLAN.md or other task files.

## Code
- Python 3.11+ (CI uses 3.12). Type hints on every function. Small modules with one job each; short functions.
- Package code lives in `weekly_diff/`; `run.py` is the CLI entry point.
- Runtime dependencies go in requirements.txt, test-only ones in requirements-dev.txt (which includes `-r requirements.txt`). Use the local virtualenv: create it with `python3.12 -m venv .venv` if missing, then `.venv/bin/python -m pip install -r requirements-dev.txt`.
- All names, URLs, limits and models come from config.yaml through `weekly_diff.config`. Do not hard-code them.
- Use `logging` (set up by `weekly_diff.log`), not print, except for intended CLI output.
- Network code must time out, send the configured User-Agent, and fail gracefully: one broken source must never stop the run.

## Tests
- Every module gets pytest tests in tests/. All tests must pass: `.venv/bin/python -m pytest -q`.
- Tests use recorded fixtures in tests/fixtures/ only. No real network or API calls in tests: mock HTTP (the `responses` library) and use the fake LLM client.
- Fixtures may be trimmed real responses. Never put secrets or real webhook URLs in fixtures.

## Secrets
- Secrets come only from environment variables: ANTHROPIC_API_KEY, OPENAI_API_KEY, DISCORD_WEBHOOK_URL, DISCORD_PREVIEW_WEBHOOK_URL, GITHUB_TOKEN.
- Never print, log, write to disk, or put secrets in exception messages. Logging goes through the redaction filter in `weekly_diff/log.py`.

## Content rules
- Summaries use only facts from the fetched source text. Never invent numbers, names, dates, quotes or claims.
- Every item links its source (http/https). Prefer primary sources (the lab, the repo, the official blog) over aggregators.
- No item repeats an earlier issue (data/seen.json).
- Escape all external and LLM text in HTML (Jinja2 autoescape) and neutralise mentions in Discord.

## Finish
Write tasks/NNN-report.md (NNN = your task number; a fix task overwrites the same file) with at most 10 lines:
- Changes: …
- Testing: exact command and result (e.g. "`.venv/bin/python -m pytest -q` → 42 passed")
- Unfinished: …
- Questions: …
