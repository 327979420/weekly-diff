"""Run independent collectors and persist reviewable build artifacts."""
from datetime import datetime
import json
import time

from weekly_diff import paths
from weekly_diff.collectors import github_releases, github_trending, hackernews, html_index, huggingface, reddit, rss
from weekly_diff.config import Config
from weekly_diff.dates import window
from weekly_diff.http import Http
from weekly_diff.log import redact
from weekly_diff.models import Candidate

COLLECTORS = (rss, html_index, github_releases, github_trending, hackernews, huggingface, reddit)


def run_collect(cfg: Config, now: datetime, dry_run: bool) -> list[Candidate]:
    period = window(now, cfg.issue.lookback_days)
    http = Http(cfg, dry_run=dry_run)
    candidates = []
    report = {}
    try:
        for source in COLLECTORS:
            name = source.__name__.rsplit('.', 1)[-1]
            started = time.monotonic()
            http.errors.clear()
            items = []
            try:
                items = source.collect(cfg, period, http)
            except Exception as error:
                http.failure(name, error)
            candidates.extend(items)
            report[name] = {'count': len(items), 'error': '\n'.join(http.errors) or None,
                            'duration': time.monotonic() - started}
    finally:
        http.close()
    paths.ensure_directory(paths.BUILD)
    (paths.BUILD / 'candidates.json').write_text(
        json.dumps([item.to_dict() for item in candidates], indent=2) + '\n', encoding='utf-8')
    (paths.BUILD / 'collect-report.json').write_text(
        redact(json.dumps(report, indent=2)) + '\n', encoding='utf-8')
    return candidates
