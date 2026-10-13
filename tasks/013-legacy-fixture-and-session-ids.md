# 013 — Frozen legacy-issue fixture; Codex session IDs in the log

## Problem
`tests/test_models.py::test_committed_legacy_issue_loads_and_renders` fails (1 failed, 438 passed). It reads the live file `data/issues/2026-42.json` and asserts it is old-format (no `zh`, no `emoji`, no `image_url`, empty `sixty_seconds_zh`). On 2026-10-12 that issue was regenerated with the bilingual pipeline, so the live file is no longer old-format. The code is fine; the test uses the wrong sample.

## Changes
1. Create `tests/fixtures/issues/legacy-2026-42.json`: the old-format version of the issue, taken from git history (`git show a039ea7^:data/issues/2026-42.json` is the bilingual one; use `git log --format=%h -- data/issues/2026-42.json` and pick the newest commit whose version has **no** `zh` fields — expected `7d21d18`). Store it unchanged.
2. Point the test at that fixture instead of `data/issues/`. Keep every existing assertion (loads, all new fields default, renders both language trees with the English fallback note). Tests must never depend on files under `data/` that the weekly run rewrites; check the other tests for the same pattern and switch any you find to fixtures.
3. Add a section **"Codex 会话记录"** to `docs/COLLAB-LOG.md` (right after the intro): a table `任务 | Codex session ID | 结果`, using the IDs below, plus one line explaining that `codex resume <session ID>` reopens that session's full conversation. Also add the session ID to each matching Codex entry in the timeline.

| Task | Session ID |
| --- | --- |
| 001 | 01a12e59-f18c-7f03-9fb9-440de5e172aa |
| 002 | 01a12e5d-5a4a-7063-8a7d-7f866fcb8a67 |
| 002-fix | 01a12e66-5b00-7811-8cdf-bef45ac56e7f |
| 003 | 01a12e69-d24d-78c2-b612-1fdda385bb4a |
| 003-fix (round 1) | 01a12ec6-8b56-7682-9033-452a9a2c653c |
| 003-fix (round 2) | 01a12ecb-5078-73c3-b91d-f52c82be9113 |
| 004 | 01a12e6f-f5bf-7513-af03-701aa4b5ad1d |
| 005 | 01a12e75-3ebf-7150-96bc-a9e3aa4cc950 |
| 006 | 01a12e79-3acc-7000-aa5b-946c9424d22d |
| 007 | 01a12e7d-85ac-7c11-88d1-d441e22c9617 |
| 008 | 01a12ed1-1505-7c62-9caa-b3b6061725b7 |
| 009 | 01a12ee8-86ff-7622-8dd4-58c990c46559 |
| 010 | 01a12eed-d0f8-7c60-acd4-2e46fa6bab82 |
| 011 | 01a12f00-644a-7d93-88b4-449f0c5bbaec |
| 012 | 01a13369-953c-7293-ba9b-ebf93dcfcd9b |

4. Append your own 013 entry to the log (include your session ID if you can see it; otherwise write "见报告" and Claude will fill it in).

## Done means
- `.venv/bin/python -m pytest -q` → all pass, 0 failed.
- No change to `data/`, `config.yaml` (`publish_enabled` stays false), or application code.
- Do not commit or push. Write tasks/013-report.md per AGENTS.md.

## Test command
`.venv/bin/python -m pytest -q`
