"""Stage interfaces reserved for later tasks."""
from argparse import Namespace
from datetime import datetime, timezone
import json

from weekly_diff import paths
from weekly_diff.collect import run_collect
from weekly_diff.build import run_build
from weekly_diff.log import redact
from weekly_diff.config import Config


def collect(cfg: Config, args: Namespace) -> None:
    run_collect(cfg, datetime.now(timezone.utc), args.dry_run)
    report = json.loads((paths.BUILD / 'collect-report.json').read_text(encoding='utf-8'))
    for name, entry in report.items():
        status = ' (errors; see collect-report.json)' if entry['error'] else ''
        print(redact(f"{name}: {entry['count']} candidates in {entry['duration']:.2f}s{status}"))


def build(cfg: Config, args: Namespace) -> None:
    run_build(cfg, args.issue, datetime.now(timezone.utc), args.dry_run)


def render(cfg: Config, args: Namespace) -> None:
    raise NotImplementedError("task 005")


def publish(cfg: Config, args: Namespace) -> None:
    raise NotImplementedError("task 006")
