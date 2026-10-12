from datetime import date
import json
from pathlib import Path

import pytest

from weekly_diff.models import Candidate, Item
from weekly_diff.seen import is_seen, load_seen, mark_seen, prune, save_seen

DATA = json.loads((Path(__file__).parent / 'fixtures/shortlist.json').read_text())


def test_seen_roundtrip_rerun_alias_and_prune(tmp_path: Path) -> None:
    path = tmp_path / 'seen.json'
    seen = load_seen(path)
    candidate = Candidate.from_dict(DATA['candidate'])
    candidate.extra['dedupe_aliases'] = [{'key': 'alias', 'url': 'http://example.com/story?ref=x', 'title': 'Alias'}]
    mark_seen(seen, [candidate], '2026-41', date(2026, 10, 10))
    assert not is_seen(seen, candidate.key, candidate.url, '2026-41')
    assert is_seen(seen, candidate.key, 'https://example.com/different', '2026-42')
    assert is_seen(seen, 'different', candidate.url + '/?utm_source=x', '2026-42')
    assert is_seen(seen, 'different', 'https://example.com/story', '2026-42')
    mark_seen(seen, [candidate], '2026-42', date(2026, 10, 12))
    assert seen['items'][candidate.key]['issue'] == '2026-41'
    save_seen(seen, path)
    assert load_seen(path) == seen
    assert path.read_text() == json.dumps(seen, sort_keys=True, indent=2) + '\n'
    prune(seen, 2, date(2026, 10, 12))
    assert len(seen['items']) == 2
    prune(seen, 1, date(2026, 10, 12))
    assert seen['items'] == {}


def test_mark_published_item(tmp_path: Path) -> None:
    data = json.loads((Path(__file__).parent / 'fixtures/models.json').read_text())
    seen = load_seen(tmp_path / 'missing')
    item = Item.from_dict(data['item'])
    mark_seen(seen, [item], '2026-41', date(2026, 10, 10))
    assert seen['items'][item.key]['title'] == item.headline


@pytest.mark.parametrize('raw', ['broken', '{"version": 2, "items": {}}', '{"version": 1, "items": {"x": {}}}'])
def test_corrupt_seen_fails_closed(tmp_path: Path, raw: str) -> None:
    path = tmp_path / 'seen.json'
    path.write_text(raw)
    with pytest.raises(ValueError, match='Invalid seen file'):
        load_seen(path)
