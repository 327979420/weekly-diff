from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from weekly_diff.config import load_config
from weekly_diff.llm.base import InvalidJSON, LLMError
from weekly_diff.llm.fake import FakeLLM
from weekly_diff.models import Candidate
from weekly_diff.score import Scored, score

DATA = json.loads((Path(__file__).parent / 'fixtures/shortlist.json').read_text())


def generated(system: str, user: str, schema: dict, max_tokens: int) -> dict:
    return {'items': [{**DATA['row'], 'id': item['id'], 'section': 'quick'} for item in json.loads(user)]}


def test_batching_cap_reservation_and_payload() -> None:
    cfg = load_config()
    cfg = replace(cfg, llm=replace(cfg.llm, max_candidates_to_score=12, score_batch_size=5))
    base = Candidate.from_dict(DATA['candidate'])
    candidates = [replace(base, key=f'news:{i}', signals={'hn_points': 100000}, text='x' * 500) for i in range(20)]
    candidates += [replace(base, key=f'gh:{i}', source_type='github_trending',
                           signals={'stars_gained': i, 'stars_total': 100000 - i}) for i in range(15)]
    fake = FakeLLM(generated)
    result = score(candidates, cfg, fake)
    assert len(result) == 12
    assert {s.candidate.key for s in result if s.section == 'github'} == {f'gh:{i}' for i in range(5, 15)}
    assert [len(json.loads(call['user'])) for call in fake.calls] == [5, 5, 2]
    payloads = [row for call in fake.calls for row in json.loads(call['user'])]
    assert all(len(row['text']) <= 300 for row in payloads)
    assert all(set(row) == {'id', 'title', 'source_name', 'domain', 'signals', 'text'} for row in payloads)
    assert cfg.sources.primary_domains[0] in fake.calls[0]['system']
    assert Scored.from_dict(result[0].to_dict()) == result[0]


def test_hard_sections_unknown_and_missing_ids() -> None:
    base = Candidate.from_dict(DATA['candidate'])
    candidates = [replace(base, key=kind, source_type=kind) for kind in ('github_trending', 'github_release', 'huggingface', 'rss')]
    fake = FakeLLM([{'items': [{**DATA['row'], 'id': kind, 'section': 'quick'}
                              for kind in ('github_trending', 'github_release', 'huggingface', 'unknown')]}])
    result = {s.candidate.key: s for s in score(candidates, load_config(), fake)}
    assert len(result) == 4
    assert [result[k].section for k in ('github_trending', 'github_release', 'huggingface')] == ['github', 'tools', 'models']
    assert result['rss'].relevant is False


@pytest.mark.parametrize('change', [{'score': True}, {'score': 11}, {'score': 3.5}, {'tag': 'bad'},
                                    {'section': 'bad'}, {'reason': 'word ' * 21}, {'relevant': 'yes'},
                                    {'unexpected': 1}, {'tag': []}, {'section': {}}])
def test_invalid_fields_retry_once(change: dict) -> None:
    bad = {'items': [{**DATA['row'], **change}]}
    good = {'items': [DATA['row']]}
    candidate = Candidate.from_dict(DATA['candidate'])
    fake = FakeLLM([bad, good])
    assert score([candidate], load_config(), fake)[0].relevant
    assert len(fake.calls) == 2
    with pytest.raises(LLMError, match='after retry'):
        score([candidate], load_config(), FakeLLM([bad, bad]))


def test_invalid_json_retry_and_transport_no_retry() -> None:
    candidate = Candidate.from_dict(DATA['candidate'])
    fake = FakeLLM([InvalidJSON('Invalid JSON completion'), {'items': [DATA['row']]}])
    assert score([candidate], load_config(), fake)[0].score == 8
    failing = FakeLLM([LLMError('Connection error')])
    with pytest.raises(LLMError, match='Connection error'):
        score([candidate], load_config(), failing)
    assert len(failing.calls) == 1
    empty = FakeLLM()
    assert score([], load_config(), empty) == []
    assert empty.calls == []


def test_fake_queue_copies_and_records() -> None:
    response = deepcopy(DATA['row'])
    fake = FakeLLM([response])
    result = fake.complete_json('system', 'user', {}, 10)
    result['score'] = 0
    assert response['score'] == 8
    assert fake.calls == [{'system': 'system', 'user': 'user', 'schema': {}, 'max_tokens': 10}]
    with pytest.raises(LLMError, match='exhausted'):
        fake.complete_json('', '', {}, 10)


@pytest.mark.parametrize('value', ['yes', 1, None])
def test_try_now_requires_boolean(value: object) -> None:
    candidate = Candidate.from_dict(DATA['candidate'])
    bad = {'items': [{**DATA['row'], 'try_now': value}]}
    with pytest.raises(LLMError):
        score([candidate], load_config(), FakeLLM([bad, bad]))


def test_spaces_stay_in_quick_and_legacy_selection_loads() -> None:
    candidate = replace(Candidate.from_dict(DATA['candidate']), key='hfspace:demo/app',
                        source_type='huggingface', section_hint='quick')
    result = score([candidate], load_config(), FakeLLM(generated))[0]
    assert result.section == 'quick' and result.try_now
    old = result.to_dict()
    del old['try_now']
    assert Scored.from_dict(old).try_now is False
