"""Build, validate and persist one weekly issue."""
from collections import Counter
from datetime import datetime
import json
import logging
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from weekly_diff import paths
from weekly_diff.config import Config
from weekly_diff.dates import as_utc, parse_issue_id, window
from weekly_diff.dedupe import dedupe
from weekly_diff.http import Http
from weekly_diff.llm import get_client
from weekly_diff.llm.base import LLMClient
from weekly_diff.models import Candidate, Issue, Item
from weekly_diff.score import score
from weekly_diff.seen import load_seen, mark_seen, prune, save_seen
from weekly_diff.select import Selection, select
from weekly_diff.site import render_site
from weekly_diff.sixty import sixty
from weekly_diff.source_text import fetch_source_text
from weekly_diff.summarise import summarise
from weekly_diff.validate import validate_issue


def top_items(items: list[Item], cfg: Config) -> list[str]:
    counts: Counter[str] = Counter()
    result = []
    for item in sorted(items, key=lambda item: (-int(item.extra.get('try_now') is True), -item.score, item.key)):
        if len(result) >= cfg.issue.top_items:
            break
        if counts[item.section] < cfg.issue.max_top_per_section:
            result.append(item.key)
            counts[item.section] += 1
    return result


def _write_items(selection: Selection, cfg: Config, http: Http, llm: LLMClient) -> dict[str, list[Item]]:
    sections: dict[str, list[Item]] = {section.key: [] for section in cfg.issue.sections}
    missing = []
    for section, chosen in selection.chosen.items():
        for scored in chosen:
            source = fetch_source_text(scored.candidate, http, cfg.llm.max_source_chars)
            item = summarise(scored, source, cfg, llm)
            if item is None:
                logging.getLogger(__name__).warning('Dropped candidate %s; seeking backup', scored.candidate.key)
                missing.append(section)
            else:
                sections[item.section].append(item)
    limits = {section.key: section.max for section in cfg.issue.sections}
    backups = {section: list(items) for section, items in selection.backups.items()}
    attempted = {scored.candidate.key for items in selection.chosen.values() for scored in items}
    for section in missing:
        filled = False
        for replacement_section in dict.fromkeys((section, 'quick')):
            pool = backups.get(replacement_section, [])
            while pool and len(sections[replacement_section]) < limits[replacement_section]:
                scored = pool.pop(0)
                if scored.candidate.key in attempted:
                    continue
                attempted.add(scored.candidate.key)
                source = fetch_source_text(scored.candidate, http, cfg.llm.max_source_chars)
                item = summarise(scored, source, cfg, llm)
                if item is not None:
                    sections[item.section].append(item)
                    filled = True
                    break
                logging.getLogger(__name__).warning('Dropped backup %s; seeking next backup', scored.candidate.key)
            if filled:
                break
    return sections


def _render(cfg: Config, issue: Issue, dry_run: bool) -> None:
    if not dry_run:
        render_site(cfg, paths.ISSUES, paths.SITE)
        return
    with TemporaryDirectory(prefix='weekly-diff-issues-') as temporary:
        combined = Path(temporary)
        for source in paths.ISSUES.glob('*.json'):
            shutil.copyfile(source, combined / source.name)
        (combined / f'{issue.id}.json').write_text(json.dumps(issue.to_dict()), encoding='utf-8')
        render_site(cfg, combined, paths.SITE)


def run_build(cfg: Config, issue_id: str, now: datetime, dry_run: bool) -> Issue:
    parse_issue_id(issue_id)
    now = as_utc(now)
    candidate_path = paths.BUILD / 'candidates.json'
    if not candidate_path.exists():
        raise FileNotFoundError('run collect first')
    candidates = [Candidate.from_dict(row) for row in json.loads(candidate_path.read_text(encoding='utf-8'))]
    seen = load_seen()
    llm = get_client(cfg)
    selection = select(score(dedupe(candidates, cfg, seen, issue_id), cfg, llm), cfg)
    http = Http(cfg, dry_run=dry_run)
    try:
        sections = _write_items(selection, cfg, http, llm)
    finally:
        http.close()
    items = [item for rows in sections.values() for item in rows]
    if len(items) < max(3, cfg.issue.hard_min_items):
        raise ValueError('Too few validated items to publish')
    top = top_items(items, cfg)
    by_key = {item.key: item for item in items}
    ordered = [by_key[key] for key in top]
    ordered.extend(sorted((item for item in items if item.key not in top), key=lambda item: (-int(item.extra.get('try_now') is True), -item.score, item.key)))
    bullet_keys: list[list[str]] = []
    bullets, bullets_zh = sixty(ordered, llm, cfg, bullet_keys)
    start, end = window(now, cfg.issue.lookback_days)
    issue = Issue(issue_id, cfg.name, now, start, end, bullets, sections, top, sixty_seconds_zh=bullets_zh, sixty_seconds_keys=bullet_keys)
    if problems := validate_issue(issue, cfg):
        raise ValueError('Invalid issue: ' + '; '.join(problems))
    destination = paths.BUILD / 'dry-run' if dry_run else paths.ISSUES
    paths.ensure_directory(destination)
    (destination / f'{issue_id}.json').write_text(json.dumps(issue.to_dict(), indent=2) + '\n', encoding='utf-8')
    if not dry_run:
        mark_seen(seen, items, issue_id, now.date())
        prune(seen, cfg.dedupe.seen_retention_days, now.date())
        save_seen(seen)
    _render(cfg, issue, dry_run)
    return issue
