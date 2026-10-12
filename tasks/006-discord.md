# 006 — Discord sender

## Goal
Post the issue to Discord through webhooks: a preview channel and a public channel, with the `publish_enabled` safety switch. Wire `run.py publish`.

## Scope
1. **`weekly_diff/discord.py`**:
   - `build_payload(issue, cfg, preview: bool, run_url: str | None) -> dict`: `username` = `cfg.name`, `allowed_mentions: {"parse": []}`, one embed: title `"{name} — Issue YYYY-WW"` (prefixed `"[PREVIEW] "` when preview), `url` = issue page URL, `color` from config, description = `**This week in 60 seconds**` + the 3 bullets + a final line `[Read the full issue →](issue url)`; fields = the `issue.top` items in order, name `"{n}. {headline}"`, value `"{summary} [Source]({source_url})"`, `inline: false`. Preview footer: `"Preview — not posted publicly"` and, in the description, a link to `run_url` when given.
   - Enforce Discord limits (title 256, description 4096, field name 256, field value 1024, total ≤ 6000 chars, ≤ 25 fields) by truncating text with "…" without breaking the `[Source](url)` link. Escape Discord markdown (`* _ ~ \` | >`) in generated text and break `@everyone`/`@here` with a zero-width space.
   - `send(payload, webhook_url, http)`: POST JSON to `webhook_url + "?wait=true"`; on 429 wait `retry_after` (max 2 retries); non-2xx → `DiscordError` with the status code only. Reject URLs that are not `https://discord.com/api/webhooks/…` or `https://discordapp.com/api/webhooks/…` with an error that does **not** contain the URL.
   - `publish(cfg, issue, preview_flag: bool, dry_run: bool, env) -> str` returns what happened (`"public"`, `"preview"`, `"skipped: …"`, `"dry-run"`):
     - `preview_flag` (Friday) → preview webhook; payload marked preview.
     - no flag (Monday) → if `cfg.publish_enabled`: public webhook (`DISCORD_WEBHOOK_URL`; missing → `DiscordError`); else preview webhook with the description first line "publish_enabled is false — this was not posted publicly."
     - preview webhook missing → log a warning and return `"skipped: DISCORD_PREVIEW_WEBHOOK_URL not set"` (exit 0).
     - `dry_run` → print the payload JSON and the target name (never the URL) and send nothing.
   - `run_url` from `GITHUB_SERVER_URL`/`GITHUB_REPOSITORY`/`GITHUB_RUN_ID` when present.
2. **Wiring**: `pipeline.publish` loads `data/issues/{issue}.json` (with `--dry-run`, fall back to `build/dry-run/{issue}.json`); missing issue → error "build first". The CLI prints the returned outcome.

## Files
weekly_diff/discord.py, weekly_diff/pipeline.py (publish), tests/test_discord.py, tests/fixtures as needed.

## Acceptance criteria
- Payload tests: preview vs public titles, limits enforced on oversized text, markdown escaped, mentions neutralised, `allowed_mentions` set, links intact.
- Routing tests with `responses`: publish_enabled false → only the preview URL is called; true → only the public URL; preview flag → preview URL; missing preview webhook → skipped, no request; dry-run → no request.
- 429 retry honoured; a 500 raises `DiscordError` whose message and logs contain no webhook URL (assert with a fake webhook in env).
- All tests pass.

## Test command
`.venv/bin/python -m pytest -q`
