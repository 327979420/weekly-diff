"""Stage interfaces reserved for later tasks."""
from argparse import Namespace
from datetime import datetime, timezone
import json
import os

from weekly_diff import paths
from weekly_diff.collect import run_collect
from weekly_diff.build import run_build
from weekly_diff.site import render_site
from weekly_diff.log import redact
from weekly_diff.config import Config
from weekly_diff.discord import DiscordError, publish as publish_discord
from weekly_diff.models import Issue


def collect(cfg: Config, args: Namespace) -> None:
    run_collect(cfg, datetime.now(timezone.utc), args.dry_run)
    report = json.loads((paths.BUILD / 'collect-report.json').read_text(encoding='utf-8'))
    for name, entry in report.items():
        status = ' (errors; see collect-report.json)' if entry['error'] else ''
        print(redact(f"{name}: {entry['count']} candidates in {entry['duration']:.2f}s{status}"))


def build(cfg: Config, args: Namespace) -> None:
    run_build(cfg, args.issue, datetime.now(timezone.utc), args.dry_run)


def render(cfg: Config, args: Namespace) -> None:
    render_site(cfg, paths.ISSUES, paths.SITE)


def publish(cfg: Config, args: Namespace) -> None:
    source = paths.ISSUES / f'{args.issue}.json'
    if args.dry_run and not source.is_file():
        source = paths.DRY_RUN / f'{args.issue}.json'
    if not source.is_file():
        raise DiscordError('Issue missing: build first')
    issue = Issue.from_dict(json.loads(source.read_text(encoding='utf-8')))
    print(publish_discord(cfg, issue, args.preview, args.dry_run, os.environ))
