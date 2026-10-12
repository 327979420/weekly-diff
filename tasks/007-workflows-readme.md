# 007 — GitHub Actions, Pages deploy, owner README

## Goal
Run the whole thing automatically on a public repo for free, deploy the site with the official GitHub Pages actions, and give the owner a one-page plain-English README.

## Scope
1. **`.github/workflows/ci.yml`** — on push and pull_request: Python 3.12, `pip install -r requirements-dev.txt`, `python -m pytest -q`.
2. **`.github/workflows/weekly.yml`** — `schedule: cron "0 21 * * 0"` (Sunday 21:00 UTC = Monday 08:00 Melbourne in summer) and `workflow_dispatch` with boolean input `dry_run` (default **true**).
   - `concurrency: weekly-diff` (no cancel). Least-privilege permissions per job: build needs `contents: write`; deploy needs `pages: write`, `id-token: write`.
   - **build** job: checkout, setup-python 3.12 with pip cache, `pip install -r requirements.txt`, `python run.py status --github-output`. If the event is `schedule` and `paused` is true, stop here (later steps/jobs skipped, run succeeds). Then `python run.py collect` and `python run.py build` (add `--dry-run` when dry_run). Env for these steps: `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` from secrets. Not dry-run: commit `data/` as `github-actions[bot]` with message `Issue {issue_id}` (skip if nothing changed) and push; upload `site/` with `actions/upload-pages-artifact`; upload `data/issues/{issue_id}.json` as an artifact for the publish job. Dry-run: upload `site/` and the dry-run issue as a normal artifact named `site-preview` and stop.
   - **deploy** job (not dry-run): `actions/deploy-pages`, environment `github-pages` with the page URL.
   - **publish** job (needs deploy, so Discord never links to a page that failed to deploy): checkout, setup-python, install, download the issue artifact into `data/issues/`, `python run.py publish`. Only this step gets `DISCORD_WEBHOOK_URL` and `DISCORD_PREVIEW_WEBHOOK_URL`.
3. **`.github/workflows/preview.yml`** — `schedule: cron "0 9 * * 5"` (Friday 09:00 UTC) and `workflow_dispatch` with `dry_run` (default true). Respect `paused` for scheduled runs. Steps: install, collect, build (normal mode in the runner; **nothing is committed or deployed**), `python run.py publish --preview` (with `--dry-run` when dry_run), upload `site/` as artifact `site-preview`. Only `contents: read`.
4. **`.github/workflows/pages.yml`** — on push to main touching `templates/**`, `static/**`, `config.yaml`, `data/issues/**`, `weekly_diff/site.py`, plus `workflow_dispatch`: `python run.py render`, upload-pages-artifact, deploy-pages. Concurrency group `pages` (shared with the deploy job of weekly.yml).
5. All third-party actions are official `actions/*` at their current major versions. No secret is echoed; no `set -x`.
6. **`README.md`** for the owner (one page, plain English, no jargon):
   - What it is and the site URL (`https://327979420.github.io/weekly-diff/`).
   - What posts when (Friday ~20:00 Melbourne preview to the private channel; Monday ~08:00 Melbourne issue + Discord; times shift one hour earlier in Melbourne winter).
   - **Go live**: in GitHub open `config.yaml` → pencil icon → change `publish_enabled: false` to `true` → Commit changes.
   - **Pause / resume**: same steps with `paused: true` / `false`.
   - **Rename**: change `name:` (and `tagline:`) the same way; the site updates within a few minutes.
   - **Run it now**: Actions tab → "Weekly issue" → Run workflow → untick "dry run" for a real run.
   - **Secrets**: list of names with which are optional, set with `gh secret set NAME` (the command prompts for the value; never paste secrets into issues or chat).
   - Cost: GitHub is free for public repos; the AI model costs a few cents per week.
   - Where issues are stored (`data/issues/`) and how to fix a bad item (edit that JSON and commit; the site re-renders).
   - Developer section (short): `python3.12 -m venv .venv`, install, `python run.py --dry-run collect` / `build`, tests.

## Files
.github/workflows/{ci,weekly,preview,pages}.yml, README.md, tests/test_workflows.py (parse each YAML: crons, inputs, permissions, that `DISCORD_*` secrets appear only in publish steps, that publish needs deploy).

## Acceptance criteria
- Workflows are valid YAML with the crons, inputs and job dependencies above; tests in `tests/test_workflows.py` pass.
- Discord secrets are referenced only in publish steps; LLM keys only in build steps.
- README covers every bullet above in under ~120 lines.
- All tests pass.

## Test command
`.venv/bin/python -m pytest -q`
