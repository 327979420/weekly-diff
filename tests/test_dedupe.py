from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path

from weekly_diff.config import load_config
from weekly_diff.dedupe import dedupe
from weekly_diff.models import Candidate
from weekly_diff.seen import mark_seen

DATA = json.loads((Path(__file__).parent / 'fixtures/shortlist.json').read_text())


def test_url_merge_and_seen_aliases() -> None:
    cfg = load_config()
    lab = Candidate.from_dict(DATA['candidate'])
    hn = replace(lab, key='hn:1', source_name='HN', source_type='hackernews', primary=True,
                 title='An aggregator headline', text='Short snippet', url=lab.url + '/?utm_source=hn',
                 signals={'hn_points': 300, 'likes': 1})
    lab.signals = {'likes': 20}
    original = deepcopy([hn, lab])
    merged = dedupe([hn, lab], cfg, {'version': 1, 'items': {}}, '2026-41')
    assert len(merged) == 1
    assert merged[0].title == lab.title and merged[0].text == lab.text
    assert merged[0].signals == {'hn_points': 300, 'likes': 20}
    assert merged[0].extra['also_seen_on'] == ['HN']
    assert [hn, lab] == original
    seen = {'version': 1, 'items': {}}
    mark_seen(seen, [hn], '2026-41', date(2026, 10, 10))
    assert len(dedupe([hn, lab], cfg, seen, '2026-41')) == 1
    assert dedupe([hn, lab], cfg, seen, '2026-42') == []


def test_near_primary_signals_and_dates() -> None:
    cfg = load_config()
    lab = Candidate.from_dict(DATA['candidate'])
    other = replace(lab, key='other', title='Atlas releases new reasoning model',
                    url='https://example.com/story', primary=False, signals={'hn_points': 500})
    empty = {'version': 1, 'items': {}}
    assert dedupe([other, lab], cfg, empty, '2026-41')[0].key == lab.key
    nonprimary = replace(lab, primary=False, url='https://example.net/story')
    assert dedupe([nonprimary, other], cfg, empty, '2026-41')[0].key == other.key
    for published in (None, lab.published_at + timedelta(days=3, seconds=1)):
        assert len(dedupe([lab, replace(other, published_at=published)], cfg, empty, '2026-41')) == 2
    assert len(dedupe([lab, replace(other, published_at=lab.published_at + timedelta(days=3))], cfg, empty, '2026-41')) == 1


def test_hf_variants_and_distinct_authors() -> None:
    base = Candidate.from_dict(DATA['candidate'])
    models = [replace(base, key=f'hf:{name}', title=name, url=f'https://huggingface.co/{name}',
                      source_type='huggingface', signals={'likes': likes}, extra={'author': name.split('/')[0]})
              for name, likes in [('lab/Atlas-7B-Instruct-FP8', 12), ('lab/Atlas-70B-GGUF', 40),
                                  ('lab/Atlas-7B-Base', 2), ('other/Atlas-7B-AWQ', 100),
                                  ('lab/Atlas-Next-7B', 50)]]
    result = dedupe(models, load_config(), {'version': 1, 'items': {}}, '2026-41')
    assert len(result) == 3
    winner = next(c for c in result if c.title == 'lab/Atlas-70B-GGUF')
    assert winner.extra['variants'] == ['lab/Atlas-7B-Base', 'lab/Atlas-7B-Instruct-FP8']
    seen = {'version': 1, 'items': {}}
    mark_seen(seen, [winner], '2026-41', date(2026, 10, 10))
    assert dedupe([models[0]], load_config(), seen, '2026-42') == []
