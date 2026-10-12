from dataclasses import replace
import json
from pathlib import Path

import pytest

from weekly_diff.config import load_config
from weekly_diff.llm.base import InvalidJSON, LLMError
from weekly_diff.llm.fake import FakeLLM
from weekly_diff.models import Candidate
from weekly_diff.score import Scored
from weekly_diff.summarise import summarise

FIX = Path(__file__).parent / 'fixtures/summarise'
GOOD = json.loads((FIX / 'summary.json').read_text())
SOURCE = (FIX / 'source.md').read_text()
CANDIDATE = Candidate.from_dict(json.loads((FIX / 'candidates.json').read_text())[0])
SCORED = Scored(CANDIDATE, True, 'models', 'builders', 8, 'Useful')


def test_retry_and_evidence() -> None:
    candidate = replace(CANDIDATE, signals={'stars_gained': 123}, extra={'dedupe_aliases': []})
    fake = FakeLLM([{**GOOD, 'summary': 'Invented 99999 gains.'}, GOOD])
    item = summarise(replace(SCORED, candidate=candidate), SOURCE, load_config(), fake)
    assert item is not None
    assert item.source_url == candidate.url
    assert item.extra['stars_gained'] == 123
    assert item.extra['source_text'] == SOURCE
    assert item.extra['candidate_title'] == candidate.title
    assert 'unsupported number' in fake.calls[1]['user']
    payload = json.loads(fake.calls[0]['user'])
    assert payload['SOURCE'] == SOURCE and payload['section'] == 'models'


@pytest.mark.parametrize('bad', [{**GOOD, 'summary': ''}, {**GOOD, 'summary': 'First. Second.'},
                                 {**GOOD, 'supported': 'yes'}, {**GOOD, 'for_builders': []},
                                 {**GOOD, 'source_url': 'https://example.com/injected'},
                                 InvalidJSON('bad'), LLMError('failed')])
def test_persistently_invalid(bad: dict | Exception, caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeLLM([bad, bad])
    assert summarise(SCORED, SOURCE, load_config(), fake) is None
    assert len(fake.calls) == 2
    assert 'Dropped item' in caplog.text


def test_unsupported_and_empty() -> None:
    fake = FakeLLM([{**GOOD, 'supported': False}])
    assert summarise(SCORED, SOURCE, load_config(), fake) is None
    assert len(fake.calls) == 1
    assert summarise(SCORED, '', load_config(), fake) is None
    assert len(fake.calls) == 1
