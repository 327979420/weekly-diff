# 001 — Skeleton, config loader, models, logging, CLI

## Goal
A runnable project skeleton that later tasks plug into: typed config, data models, secret-safe logging, issue-week helpers and the `run.py` CLI.

## Scope
1. **Environment**: `requirements.txt` (runtime: PyYAML, requests, feedparser, beautifulsoup4, Jinja2, anthropic, openai) and `requirements-dev.txt` (`-r requirements.txt`, pytest, responses). `pyproject.toml` with `[project] requires-python = ">=3.11"` and pytest config (`testpaths = ["tests"]`). Create `.venv` with `python3.12 -m venv .venv` and install `requirements-dev.txt`.
2. **`weekly_diff/config.py`**: load `config.yaml` into frozen dataclasses mirroring every key in the current file (name, tagline, publish_enabled, paused, site, issue + sections, tags, llm, dedupe, discord, sources and each source block). Validate types and required keys; raise `ConfigError` with the dotted key path (e.g. `issue.sections[2].max`). Checks: `site.base_url` has no trailing slash; section keys unique and include models/tools/github/quick; `min <= max`; tag keys are exactly builders/work/beginner; `llm.provider` in auto/anthropic/openai. `load_config(path="config.yaml") -> Config`. Helpers: `Config.base_path` (URL path part of base_url, e.g. `/weekly-diff`), `Config.issue_url(issue_id)`.
3. **`weekly_diff/models.py`**: dataclasses with `to_dict()` / `from_dict()` round-tripping through JSON (datetimes as ISO 8601 UTC):
   - `Candidate`: key, title, url, source_name, source_type (rss | html_index | github_release | github_trending | hackernews | huggingface), published_at (datetime | None), text, primary (bool), section_hint (str | None), signals (dict[str, float | int]), extra (dict).
   - `Item`: key, section, headline, summary, why_it_matters, for_builders (str | None), tag, source_url, source_name, published_at, score (float), extra (dict).
   - `Issue`: id, name, published_at, period_start, period_end, sixty_seconds (list[str]), sections (ordered dict section_key → list[Item]), top (list of item keys). `Issue.items()` iterates all items in page order.
4. **`weekly_diff/dates.py`**: `issue_id_for(dt: datetime) -> str` = ISO year-week of the UTC date, formatted `YYYY-WW` (zero-padded); `parse_issue_id`; `window(now, lookback_days) -> (start, end)`; `issue_period(issue_id) -> (monday, sunday)`. Use timezone-aware datetimes only.
5. **`weekly_diff/log.py`**: `setup_logging(verbose: bool)`. A logging filter that replaces the value of each set secret env var (ANTHROPIC_API_KEY, OPENAI_API_KEY, DISCORD_WEBHOOK_URL, DISCORD_PREVIEW_WEBHOOK_URL, GITHUB_TOKEN; only values ≥ 8 chars) with `***`, and any `https://discord(app)?.com/api/webhooks/...` URL with `https://discord.com/api/webhooks/***`, in the message, args and exception text. Export `redact(text) -> str` for other modules.
6. **`weekly_diff/paths.py`**: repo-relative paths (data/, data/issues/, data/seen.json, data/stars.json, build/, build/dry-run/, site/). Directories are created on demand.
7. **`weekly_diff/pipeline.py`**: stage functions `collect(cfg, args)`, `build(cfg, args)`, `render(cfg, args)`, `publish(cfg, args)`, each currently raising `NotImplementedError("task 00N")` with the task that will implement it.
8. **`run.py`** (argparse): global options `--config PATH` (default config.yaml), `--dry-run`, `--issue YYYY-WW` (default: `issue_id_for(now)`), `-v/--verbose`. Subcommands: `collect`, `build`, `render`, `publish [--preview]`, `status [--github-output]`. `status` prints name, issue id, paused, publish_enabled; with `--github-output` it also appends `paused=true|false`, `publish_enabled=true|false`, `issue_id=…` to the file named by `$GITHUB_OUTPUT`. Exit codes: 0 success, 1 runtime error (message logged, no traceback unless -v), 2 config/usage error.
9. **Data seeds**: create `data/issues/.gitkeep` and `data/stars.json` (`{}`) if missing. Do not change `data/seen.json`.

## Files
requirements.txt, requirements-dev.txt, pyproject.toml, run.py, weekly_diff/{__init__,config,models,dates,log,paths,pipeline}.py, tests/{test_config,test_models,test_dates,test_log,test_cli}.py, tests/fixtures/ (small config variants), data/issues/.gitkeep, data/stars.json.

## Acceptance criteria
- `load_config()` loads the real config.yaml; invalid fixtures raise `ConfigError` naming the bad key.
- Model round-trip: `X.from_dict(json.loads(json.dumps(x.to_dict()))) == x` for all three models.
- `issue_id_for` is correct around ISO year boundaries (e.g. 2026-12-31 → `2026-53`, 2027-01-04 → `2027-01`) and for Sunday 21:00 UTC.
- A logged message containing a secret env value or a Discord webhook URL is redacted, including in exception tracebacks.
- `python run.py status` prints the four values; `--github-output` writes them; `python run.py --help` lists all subcommands.
- All tests pass.

## Test command
`.venv/bin/python -m pytest -q`
