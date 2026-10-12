"""Discover repositories and rank weekly gains from star-count history."""
from datetime import datetime, timedelta
import json
import logging
from typing import Any

from weekly_diff import paths
from weekly_diff.collectors import in_window, valid_url
from weekly_diff.config import Config
from weekly_diff.http import Http
from weekly_diff.models import Candidate
from weekly_diff.text import parse_date

logger = logging.getLogger(__name__)
History = dict[str, list[dict[str, Any]]]


def _discover(cfg: Config, window: tuple[datetime, datetime], http: Http) -> list[dict[str, Any]]:
    settings = cfg.sources.github_trending
    repos = {}
    for query in settings.queries:
        try:
            query = query.format(since=window[0].date().isoformat(), created_since=(
                window[1] - timedelta(days=settings.created_within_days)).date().isoformat())
            data = http.get_json(f'{cfg.sources.github_api_url}/search/repositories', params={
                'q': query, 'sort': 'stars', 'order': 'desc', 'per_page': settings.search_per_page})
            for repo in data['items']:
                repos[repo['full_name'].lower()] = repo
        except Exception as error:
            http.failure(settings.name, error)
    return list(repos.values())


def _snapshots(http: Http) -> History:
    try:
        data = json.loads(paths.STARS.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('invalid star snapshot')
        if 'version' in data:
            if data['version'] != 1 or not isinstance(data.get('repos'), dict):
                raise ValueError('invalid star snapshot history')
            data = data['repos']
        result = {}
        for key, value in data.items():
            entries = [value] if isinstance(value, dict) else value
            if isinstance(entries, list):
                result[key.lower()] = [entry for entry in entries if isinstance(entry, dict)
                                       and type(entry.get('stars')) is int
                                       and parse_date(entry.get('at')) is not None]
        return result
    except FileNotFoundError:
        return {}
    except (ValueError, OSError) as error:
        http.failure('star snapshots', error)
        return {}


def _gain(repo: dict[str, Any], history: History, cfg: Config,
          window: tuple[datetime, datetime]) -> tuple[int, dict[str, str]] | None:
    if in_window(parse_date(repo.get('created_at')), window):
        return repo['stargazers_count'], {'gain_method': 'new'}
    settings = cfg.sources.github_trending
    eligible = []
    for entry in history.get(repo['full_name'].lower(), []):
        age = window[1] - parse_date(entry['at'])
        if timedelta(days=settings.snapshot_min_days) <= age <= timedelta(days=settings.snapshot_max_days):
            eligible.append(entry)
    if not eligible:
        return None
    previous = min(eligible, key=lambda entry: abs(
        window[1] - parse_date(entry['at']) - timedelta(weeks=1)))
    return repo['stargazers_count'] - previous['stars'], {
        'gain_method': 'snapshot', 'gain_since': previous['at']}


def _save(history: History, repos: list[dict[str, Any]], cfg: Config,
          now: datetime, http: Http) -> None:
    settings = cfg.sources.github_trending
    for repo in repos:
        entries = history.setdefault(repo['full_name'].lower(), [])
        entries[:] = [entry for entry in entries if parse_date(entry['at']) != now]
        entries.append({'at': now.isoformat(), 'stars': repo['stargazers_count']})
    cutoff = now - timedelta(days=settings.snapshot_retention_days)
    retained = {}
    for name, entries in history.items():
        ordered = sorted(entries, key=lambda entry: parse_date(entry['at']))
        if ordered and parse_date(ordered[-1]['at']) >= cutoff:
            retained[name] = ordered[-settings.snapshot_history_limit:]
    try:
        paths.ensure_directory(paths.STARS.parent)
        temporary = paths.STARS.with_suffix('.json.tmp')
        temporary.write_text(json.dumps({'version': 1, 'repos': retained}, indent=2) + '\n',
                             encoding='utf-8')
        temporary.replace(paths.STARS)
    except OSError as error:
        http.failure('star snapshots', error)


def collect(cfg: Config, window: tuple[datetime, datetime], http: Http) -> list[Candidate]:
    history = _snapshots(http)
    repos = _discover(cfg, window, http)
    settings = cfg.sources.github_trending
    excluded = {name.lower() for name in settings.exclude_repos}
    result = []
    skipped = 0
    for repo in repos:
        if (repo['fork'] or repo['archived'] or repo['full_name'].lower() in excluded
                or not parse_date(repo.get('created_at')) or not valid_url(repo.get('html_url', ''))):
            continue
        measured = _gain(repo, history, cfg, window)
        if measured is None:
            skipped += 1
            logger.debug('No weekly star baseline for %s', repo['full_name'])
            continue
        gained, extra = measured
        extra.update({key: repo.get(key) for key in ('language', 'topics', 'description')})
        result.append(Candidate(f"github:{repo['full_name'].lower()}", repo['full_name'],
                                repo['html_url'], settings.name, 'github_trending',
                                parse_date(repo['created_at']), repo.get('description') or '',
                                True, 'github', {'stars_gained': gained,
                                                'stars_total': repo['stargazers_count']}, extra))
    logger.info('GitHub trending: skipped %d repos without a weekly star baseline', skipped)
    if not http.dry_run and (repos or history):
        _save(history, repos, cfg, window[1], http)
    return sorted(result, key=lambda item: item.signals['stars_gained'], reverse=True)[:settings.candidates]
