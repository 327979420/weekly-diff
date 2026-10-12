"""Persistent publication identities, including aliases of merged candidates."""
from collections.abc import Iterable
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from typing import Any

from weekly_diff import paths
from weekly_diff.models import Candidate, Item
from weekly_diff.urls import canonical_url

Seen = dict[str, Any]


def load_seen(path: str | Path | None = None) -> Seen:
    target = Path(path) if path is not None else paths.SEEN
    if not target.exists():
        return {'version': 1, 'items': {}}
    try:
        seen = json.loads(target.read_text(encoding='utf-8'))
        if seen['version'] != 1 or not isinstance(seen['items'], dict):
            raise ValueError
        for entry in seen['items'].values():
            if not all(isinstance(entry[k], str) for k in ('issue', 'url', 'title', 'first_seen')):
                raise ValueError
            canonical_url(entry['url'])
            date.fromisoformat(entry['first_seen'])
        return seen
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise ValueError('Invalid seen file') from None


def is_seen(seen: Seen, key: str, url: str, current_issue: str) -> bool:
    canonical = canonical_url(url)
    return any(entry['issue'] != current_issue
               and (stored_key == key or canonical_url(entry['url']) == canonical)
               for stored_key, entry in seen['items'].items())


def _day(today: date) -> date:
    return today.date() if isinstance(today, datetime) else today


def mark_seen(seen: Seen, items: Iterable[Candidate | Item], issue_id: str, today: date) -> None:
    for item in items:
        url = item.url if isinstance(item, Candidate) else item.source_url
        title = item.title if isinstance(item, Candidate) else item.headline
        identities = [{'key': item.key, 'url': url, 'title': title},
                      *item.extra.get('dedupe_aliases', [])]
        for identity in identities:
            key = identity['key']
            # Never erase a prior issue's evidence, even if called with a repeated item.
            if key in seen['items']:
                continue
            seen['items'][key] = {'issue': issue_id, 'url': canonical_url(identity['url']),
                                  'title': identity['title'], 'first_seen': _day(today).isoformat()}


def prune(seen: Seen, retention_days: int, today: date) -> None:
    cutoff = _day(today) - timedelta(days=retention_days)
    seen['items'] = {key: item for key, item in seen['items'].items()
                     if date.fromisoformat(item['first_seen']) >= cutoff}


def save_seen(seen: Seen, path: str | Path | None = None) -> None:
    target = Path(path) if path is not None else paths.SEEN
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(seen, sort_keys=True, indent=2) + '\n', encoding='utf-8')
