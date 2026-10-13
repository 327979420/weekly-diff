"""Editorial retries, phrase repair and evidence retention use the recorded summary."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from weekly_diff.config import load_config
from weekly_diff.editorial import banned_problems, opening, strip_banned
from weekly_diff.llm.base import LLMError
from weekly_diff.llm.fake import FakeLLM
from weekly_diff.models import Candidate
from weekly_diff.score import Scored
from weekly_diff.summarise import summarise, vary_openings
from weekly_diff.validate import validate_item

FIX = Path(__file__).parent / 'fixtures/summarise'
GOOD = json.loads((FIX / 'summary.json').read_text())
SOURCE = (FIX / 'source.md').read_text()
CANDIDATE = Candidate.from_dict(json.loads((FIX / 'candidates.json').read_text())[0])
SCORED = Scored(CANDIDATE, True, 'models', 'try', 8, 'Useful')


@pytest.mark.parametrize('phrase', ['赋能', '助力', '重磅', '炸裂', '全面升级', '一站式', '这意味着',
                                   'game-changer', 'REVOLUTIONARY', 'unlock the power', '!', '！'])
def test_banned_phrases(phrase: str) -> None:
    assert banned_problems(phrase)
    assert not banned_problems(strip_banned(phrase))
    assert not banned_problems('revolutionaryish')


@pytest.mark.parametrize('chinese', [False, True])
@pytest.mark.parametrize('corrected', [False, True])
def test_phrase_retry_then_strip(chinese: bool, corrected: bool) -> None:
    row = deepcopy(GOOD)
    copy = row['zh'] if chinese else row
    copy['why_it_matters'] = ('赋能' if chinese else 'Revolutionary ') + copy['why_it_matters']
    fake = FakeLLM([row, GOOD if corrected else row])
    item = summarise(SCORED, SOURCE, load_config(), fake)
    assert item is not None
    assert not validate_item(item, SOURCE, load_config())
    assert len(fake.calls) == 2
    assert 'banned phrase:' in fake.calls[1]['user']
    assert item.zh['why_it_matters'] == GOOD['zh']['why_it_matters']
    assert item.why_it_matters == GOOD['why_it_matters']


def test_phrase_removal_does_not_hide_evidence_error() -> None:
    row = {**GOOD, 'summary': 'Revolutionary gains of 99999.'}
    assert summarise(SCORED, SOURCE, load_config(), FakeLLM([row, row])) is None


@pytest.mark.parametrize('response', [GOOD, LLMError('failed'), {**GOOD, 'summary': 'Costs 99999.'}])
def test_variety_retry_keeps_valid_original_on_failure_or_repetition(response: dict | Exception) -> None:
    item = summarise(SCORED, SOURCE, load_config(), FakeLLM([GOOD]))
    assert item is not None
    sections = {'models': [item, replace(item, key='second'), replace(item, key='third')]}
    original = deepcopy(sections)
    fake = FakeLLM([response, response])
    vary_openings(sections, load_config(), fake)
    assert len(fake.calls) == 2  # Adjacent You can / 你可以, even before the third occurrence.
    assert all('vary the opening; do not start with' in call['user'] for call in fake.calls)
    assert [row.summary for row in sections['models']] == [row.summary for row in original['models']]
    assert len(sections['models']) == 3


@pytest.mark.parametrize('chinese', [False, True])
def test_general_opening_limit_and_successful_rewrite(chinese: bool) -> None:
    row = deepcopy(GOOD)
    row['summary'] = 'Subagents compact the context before the main conversation.'
    row['zh']['summary'] = '子代理会提前压缩上下文。'
    item = summarise(SCORED, SOURCE, load_config(), FakeLLM([row]))
    assert item is not None
    # Vary the other language so the general four-word/character rule is isolated.
    rows = [deepcopy(replace(item, key=str(i))) for i in range(3)]
    for i, entry in enumerate(rows):
        if chinese:
            entry.summary = ['Earlier compaction is configurable.', 'Set the compaction window.', 'Context compacts earlier.'][i]
        else:
            entry.zh['summary'] = ['可以配置压缩时机。', '提前压缩上下文。', '设置子代理压缩时机。'][i]
    revised = deepcopy(row)
    revised['summary'] = 'Earlier context compaction is configurable.'
    revised['zh']['summary'] = '提前压缩上下文的时机可以配置。'
    fake = FakeLLM([revised])
    sections = {'models': rows[:2], 'tools': rows[2:]}
    vary_openings(sections, load_config(), fake)
    assert len(fake.calls) == 1
    assert sections['tools'][0].summary == revised['summary']
    notes = json.loads(fake.calls[0]['user'])['validation_problems']
    assert any(('子代理会' if chinese else 'subagents compact the context') in note for note in notes)


def test_opening_normalization() -> None:
    assert opening('  YOU CAN test it.', chinese=False) == 'you can'
    assert opening('你可以配置它。', chinese=True) == '你可以'
    assert opening('把技术概念画出来。', chinese=True) == '把技术概'


def test_both_prompts_include_voice_and_examples() -> None:
    for name in ('summarise', 'sixty'):
        prompt = Path(f'weekly_diff/prompts/{name}.md').read_text()
        for phrase in ('Docker Agent runs AI assistants from one YAML file', 'Haiku 5.5 runs about 75%',
                       '每个零件背后都是一个真的小模型', 'no more than 2', 'never two in a row', '一站式'):
            assert phrase.casefold() in prompt.casefold()
        assert 'must address the reader' not in prompt
        assert '必须用“你”' not in prompt
