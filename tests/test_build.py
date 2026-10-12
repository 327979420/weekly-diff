from argparse import Namespace
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

import pytest
import responses

from weekly_diff import build, paths, pipeline
from weekly_diff.config import Config, load_config
from weekly_diff.llm.fake import FakeLLM
from weekly_diff.models import Candidate, Issue
from weekly_diff.score import Scored
from weekly_diff.select import Selection
from weekly_diff.seen import load_seen
from weekly_diff.validate import validate_issue

FIX = Path(__file__).parent / 'fixtures/summarise'
ROWS = json.loads((FIX / 'candidates.json').read_text())
GOOD = json.loads((FIX / 'summary.json').read_text())
NOW = datetime(2026, 10, 11, 21, tzinfo=timezone.utc)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_http: responses.RequestsMock) -> Config:
    for name, relative in (('BUILD', 'build'), ('DATA', 'data'), ('ISSUES', 'data/issues'),
                           ('SEEN', 'data/seen.json'), ('DRY_RUN', 'build/dry-run'), ('SITE', 'site')):
        monkeypatch.setattr(paths, name, tmp_path / relative)
    paths.BUILD.mkdir()
    (paths.BUILD / 'candidates.json').write_text(json.dumps(ROWS))
    for row in ROWS:
        offline_http.get(row['url'], body=(FIX / 'image.html').read_text())
    return load_config()


def fake_response(system: str, user: str, schema: dict, max_tokens: int) -> dict:
    data = json.loads(user)
    if isinstance(data, list):
        return {'items': [{'id': row['id'], 'relevant': True, 'section': row['id'].split(':')[0],
                           'tag': 'builders', 'score': 8, 'reason': 'Useful update'} for row in data]}
    if 'SOURCE' in data:
        return GOOD
    return {'bullets': [{'text': item['headline'], 'text_zh': item['zh']['headline'], 'item_keys': [item['key']]} for item in data['items'][:3]]}


def test_end_to_end_and_rerun(workspace: Config, monkeypatch: pytest.MonkeyPatch,
                             caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeLLM(fake_response)
    monkeypatch.setattr(build, 'get_client', lambda cfg: fake)
    caplog.set_level('INFO')
    first = build.run_build(workspace, '2026-41', NOW, False)
    target = paths.ISSUES / '2026-41.json'
    assert Issue.from_dict(json.loads(target.read_text())) == first
    assert 10 <= len(list(first.items())) <= 15
    assert len(first.sixty_seconds) == 3 and len(first.top) == 5
    assert len(first.sixty_seconds_zh) == 3
    assert all(item.emoji and set(item.zh) == {'headline', 'summary', 'why_it_matters', 'for_builders'}
               and item.image_url == 'https://example.com/image.png' for item in first.items())
    assert not validate_issue(first, workspace)
    assert set(load_seen()['items']) == {item.key for item in first.items()}
    assert first.published_at == NOW
    assert first.period_start == NOW - timedelta(days=workspace.issue.lookback_days)
    assert first.period_end == NOW
    assert (paths.SITE / 'issues/2026-41/index.html').exists()
    second = build.run_build(workspace, '2026-41', NOW + timedelta(hours=1), False)
    assert {item.key for item in second.items()} == {item.key for item in first.items()}
    assert json.loads(target.read_text())['published_at'] == second.published_at.isoformat()


def test_dry_run_leaves_data_untouched(workspace: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build, 'get_client', lambda cfg: FakeLLM(fake_response))
    build.run_build(workspace, '2026-41', NOW, True)
    assert not paths.DATA.exists()
    paths.DATA.mkdir()
    (paths.DATA / 'sentinel').write_bytes(b'unchanged')
    before = {p: p.read_bytes() for p in paths.DATA.rglob('*') if p.is_file()}
    build.run_build(workspace, '2026-41', NOW, True)
    assert before == {p: p.read_bytes() for p in paths.DATA.rglob('*') if p.is_file()}
    assert (paths.BUILD / 'dry-run/2026-41.json').exists()


@pytest.mark.parametrize('failure', ['invalid', 'unsupported', 'empty'])
def test_backfill(workspace: Config, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    calls = Counter()

    def handler(system: str, user: str, schema: dict, max_tokens: int) -> dict:
        payload = json.loads(user)
        if isinstance(payload, dict) and payload.get('title') == 'models Alpha':
            calls['failed'] += 1
            return {**GOOD, **({'supported': False} if failure == 'unsupported' else {'summary': 'Invented 99999.'})}
        return fake_response(system, user, schema, max_tokens)

    if failure == 'empty':
        rows = [dict(row, text='') if row['key'] == 'models:Alpha' else row for row in ROWS]
        (paths.BUILD / 'candidates.json').write_text(json.dumps(rows))
    monkeypatch.setattr(build, 'get_client', lambda cfg: FakeLLM(handler))
    issue = build.run_build(workspace, '2026-41', NOW, True)
    keys = {item.key for item in issue.items()}
    assert 'models:Alpha' not in keys and 'models:Echo' in keys
    assert len(keys) == 15
    assert calls['failed'] == {'invalid': 2, 'unsupported': 1, 'empty': 0}[failure]


def test_quick_backup_after_same_section_exhausted(workspace: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    def scored(index: int) -> Scored:
        candidate = Candidate.from_dict(ROWS[index])
        return Scored(candidate, True, candidate.section_hint, 'builders', 8, '')

    chosen = {section: [] for section in ('models', 'tools', 'github', 'quick')}
    chosen['models'] = [scored(0)]
    selection = Selection(chosen, {'models': [scored(1)], 'quick': [scored(15)]})
    fake = FakeLLM([{**GOOD, 'supported': False}, {**GOOD, 'supported': False}, GOOD])
    http = build.Http(workspace)
    try:
        result = build._write_items(selection, workspace, http, fake)
    finally:
        http.close()
    assert not result['models']
    assert [item.key for item in result['quick']] == ['quick:Alpha']


def test_failed_build_does_not_save(workspace: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(system: str, user: str, schema: dict, max_tokens: int) -> dict:
        data = json.loads(user)
        return {**GOOD, 'supported': False} if isinstance(data, dict) and 'SOURCE' in data else fake_response(system, user, schema, max_tokens)

    monkeypatch.setattr(build, 'get_client', lambda cfg: FakeLLM(handler))
    with pytest.raises(ValueError, match='Too few validated'):
        build.run_build(workspace, '2026-41', NOW, False)
    assert not paths.DATA.exists()


def test_missing_candidates(workspace: Config) -> None:
    (paths.BUILD / 'candidates.json').unlink()
    with pytest.raises(FileNotFoundError, match='run collect first'):
        build.run_build(workspace, '2026-41', NOW, False)


def test_pipeline_and_render_hook(workspace: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(pipeline, 'run_build', lambda *args: calls.append(args))
    pipeline.build(workspace, Namespace(issue='2026-41', dry_run=True))
    assert calls[0][0:2] == (workspace, '2026-41') and calls[0][3] is True
    monkeypatch.setattr(build, 'render_site', lambda *args: calls.append(args))
    issue = Issue.from_dict(json.loads((Path(__file__).parent / 'fixtures/issues/2026-41.json').read_text()))
    build._render(workspace, issue, False)
    assert calls[-1] == (workspace, paths.ISSUES, paths.SITE)


def test_top_score_and_section_cap(workspace: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build, 'get_client', lambda cfg: FakeLLM(fake_response))
    issue = build.run_build(workspace, '2026-41', NOW, True)
    items = [replace(item, score=10 if item.section == 'models' else 7) for item in issue.items()]
    top = build.top_items(items, workspace)
    assert len(top) == 5
    assert all(next(item for item in items if item.key == key).section == 'models' for key in top[:2])
    counts = Counter(item.section for item in items if item.key in top)
    assert max(counts.values()) <= workspace.issue.max_top_per_section


def test_final_validation_blocks_save(workspace: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build, 'get_client', lambda cfg: FakeLLM(fake_response))
    cfg = replace(workspace, issue=replace(workspace.issue, max_top_per_section=1))
    with pytest.raises(ValueError, match='Invalid issue: top'):
        build.run_build(cfg, '2026-41', NOW, False)
    assert not paths.DATA.exists()


@pytest.mark.parametrize('quick_first', [False, True])
def test_shared_quick_backups_consumed_once(workspace: Config, quick_first: bool) -> None:
    models = [Scored(Candidate.from_dict(row), True, 'models', 'builders', 8, '') for row in ROWS[:4]]
    quick = replace(models[1], section='quick')
    chosen = {'models': [models[0]], 'quick': [quick]}
    if quick_first:
        chosen = dict(reversed(list(chosen.items())))
    selection = Selection(chosen, {'models': models[2:],
                                   'quick': [replace(item, section='quick') for item in models[2:]]})
    fake = FakeLLM([{**GOOD, 'supported': False}] * 2 + [GOOD] * 2)
    http = build.Http(workspace)
    try:
        result = build._write_items(selection, workspace, http, fake)
    finally:
        http.close()
    assert len(result['models']) == len(result['quick']) == 1
    assert {item.key for rows in result.values() for item in rows} == {item.candidate.key for item in models[2:]}
    assert all(item.section == section for section, rows in result.items() for item in rows)
    assert len(fake.calls) == 4
