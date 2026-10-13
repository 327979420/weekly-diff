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


@pytest.mark.parametrize('bad', [{**GOOD, 'summary': ''},
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


@pytest.mark.parametrize(('headline', 'expected'), [
    ('A useful model update, with more details to follow', 'A useful model update'),
    ('A useful model update — with more details to follow', 'A useful model update'),
    ('A useful model update with more details to follow', 'A useful model update'),
])
def test_long_headline_shortened_only_after_retry(headline: str, expected: str) -> None:
    cfg = load_config()
    cfg = replace(cfg, issue=replace(cfg.issue, max_headline_chars=24))
    fake = FakeLLM([{**GOOD, 'headline': headline}] * 2)
    item = summarise(SCORED, SOURCE, cfg, fake)
    assert item is not None and item.headline == expected
    assert len(fake.calls) == 2
    assert 'at most 24 characters' in fake.calls[0]['system']
    assert 'headline exceeds 24 characters' in fake.calls[1]['user']


@pytest.mark.parametrize('extra', [{'summary': 'Invented 99999 gains.'}, {'summary': ''},
                                  {'tag': 'invalid'}, {'supported': False}])
def test_long_headline_does_not_hide_other_errors(extra: dict) -> None:
    fake = FakeLLM([{**GOOD, 'headline': 'A useful model update ' * 6, **extra}] * 2)
    assert summarise(SCORED, SOURCE, load_config(), fake) is None


def test_long_headline_without_word_boundary_is_dropped() -> None:
    fake = FakeLLM([{**GOOD, 'headline': 'x' * 100}] * 2)
    assert summarise(SCORED, SOURCE, load_config(), fake) is None


@pytest.mark.parametrize('both', [False, True])
def test_chinese_headline_shortened_after_retry(both: bool) -> None:
    row = {**GOOD, 'zh': {**GOOD['zh'], 'headline': '新' * 39 + '，还有更新'}}
    if both:
        row['headline'] = 'A useful update ' * 10
    fake = FakeLLM([row, row])
    item = summarise(SCORED, SOURCE, load_config(), fake)
    assert item is not None and item.zh['headline'] == '新' * 39
    assert len(item.headline) <= 90
    assert len(fake.calls) == 2
    assert 'zh.headline exceeds 40' in fake.calls[1]['user']
    assert row['zh']['headline'].endswith('还有更新')


@pytest.mark.parametrize('change', [{'summary': ''}, {'summary': '支持 99999 个工具'}])
def test_chinese_headline_does_not_hide_other_errors(change: dict) -> None:
    row = {**GOOD, 'zh': {**GOOD['zh'], 'headline': '新' * 41, **change}}
    assert summarise(SCORED, SOURCE, load_config(), FakeLLM([row, row])) is None


@pytest.mark.parametrize('change', [{'emoji': ''}, {'zh': None}, {'zh': []},
                                  {'zh': {'summary': '新闻'}}, {'image_url': 'https://example.com/injected'}])
def test_invalid_bilingual_response(change: dict) -> None:
    row = {**GOOD, **change}
    assert summarise(SCORED, SOURCE, load_config(), FakeLLM([row, row])) is None


def test_bilingual_schema_and_token_budget() -> None:
    fake = FakeLLM([GOOD])
    cfg = load_config()
    item = summarise(SCORED, SOURCE, cfg, fake)
    assert item is not None and item.zh == GOOD['zh'] and item.emoji == GOOD['emoji']
    call = fake.calls[0]
    assert call['max_tokens'] == cfg.content.summarise_max_tokens
    assert set(call['schema']['properties']['zh']['required']) == set(GOOD['zh'])
    assert 'image_url' not in call['schema']['properties']


def test_editorial_summary_does_not_require_second_person() -> None:
    row = {**GOOD, 'summary': 'Subagents auto-compact earlier than the main conversation.',
           'zh': {**GOOD['zh'], 'summary': '子代理可以比主对话更早自动压缩上下文。'}}
    fake = FakeLLM([row])
    assert summarise(SCORED, SOURCE, load_config(), fake) is not None
    assert len(fake.calls) == 1


@pytest.mark.parametrize('chinese', [False, True])
@pytest.mark.parametrize('field', ['headline', 'summary', 'why_it_matters', 'for_builders'])
def test_all_copy_lengths_repaired_after_retry(field: str, chinese: bool) -> None:
    from weekly_diff.validate import validate_item
    row = {**GOOD, 'zh': dict(GOOD['zh'])}
    copy = row['zh'] if chinese else row
    prefix = copy[field].rstrip('。.')
    copy[field] = prefix + ('，' + '更多说明' * 100 if chinese else ', ' + 'more details ' * 100)
    if field == 'summary':
        copy[field] = prefix + ('，' + '更多说明' * 100 + '。' if chinese else ', ' + 'more details ' * 100 + '.')
    fake = FakeLLM([row, row])
    cfg = load_config()
    item = summarise(SCORED, SOURCE, cfg, fake)
    assert item is not None
    assert (item.zh[field] if chinese else getattr(item, field)) == (copy[field] if field == 'summary' else prefix)
    assert not validate_item(item, SOURCE, cfg)
    assert len(fake.calls) == 2


def test_incomplete_summary_is_not_cut_at_comma() -> None:
    row = {**GOOD, 'summary': 'Useful tools, ' + 'details ' * 30 + 'for you'}
    assert summarise(SCORED, SOURCE, load_config(), FakeLLM([row, row])) is None


def test_prompt_uses_configured_chinese_limits() -> None:
    fake = FakeLLM([GOOD])
    summarise(SCORED, SOURCE, load_config(), fake)
    prompt = fake.calls[0]['system']
    assert 'summary 70, why_it_matters 100, for_builders 90' in prompt
    assert '摘要 70 字符' in prompt and '上手步骤 90 字符' in prompt


@pytest.mark.parametrize('chinese', [False, True])
def test_overlong_multisentence_summary_keeps_complete_first_sentence(chinese: bool) -> None:
    row = {**GOOD, 'zh': dict(GOOD['zh'])}
    copy = row['zh'] if chinese else row
    first = copy['summary']
    copy['summary'] = first + ('更多说明。' * 30 if chinese else ' More details.' * 30)
    fake = FakeLLM([row, row])
    item = summarise(SCORED, SOURCE, load_config(), fake)
    assert item is not None
    assert (item.zh['summary'] if chinese else item.summary) == first
    assert len(fake.calls) == 2


@pytest.mark.parametrize('languages', [('en',), ('zh',), ('en', 'zh')])
def test_short_multisentence_summary_repaired_after_retry(languages: tuple[str, ...]) -> None:
    from weekly_diff.validate import validate_item
    row = {**GOOD, 'zh': dict(GOOD['zh'])}
    cfg = load_config()
    for language in languages:
        copy = row['zh'] if language == 'zh' else row
        copy['summary'] += ('开发者可以配置压缩时机。' if language == 'zh'
                            else ' Builders can configure when a subagent compacts its context.')
    assert len(row['summary'].split()) <= cfg.content.max_summary_words
    assert len(row['zh']['summary']) <= cfg.content.max_summary_chars_zh
    fake = FakeLLM([row, row])
    item = summarise(SCORED, SOURCE, cfg, fake)
    assert item is not None
    assert item.summary == GOOD['summary']
    assert item.zh['summary'] == GOOD['zh']['summary']
    assert not validate_item(item, SOURCE, cfg)
    assert len(fake.calls) == 2
    assert 'must be a single sentence' in fake.calls[1]['user']
    assert 'exactly one sentence' in fake.calls[0]['system']
    assert '中文以一个句号结尾' in fake.calls[0]['system']


@pytest.mark.parametrize('chinese', [False, True])
@pytest.mark.parametrize('unsupported', [False, True])
def test_sentence_repair_does_not_hide_evidence_errors(chinese: bool, unsupported: bool) -> None:
    row = {**GOOD, 'zh': dict(GOOD['zh'])}
    copy = row['zh'] if chinese else row
    copy['summary'] = ('支持 99999 个工具。开发者可以配置。' if chinese
                       else 'Supports 99999 tools. Builders can configure them.')
    row['supported'] = not unsupported
    fake = FakeLLM([row, row])
    assert summarise(SCORED, SOURCE, load_config(), fake) is None


def test_sentence_repair_revalidates_empty_first_sentence() -> None:
    row = {**GOOD, 'summary': 'First.Second'}
    fake = FakeLLM([row, row])
    assert summarise(SCORED, SOURCE, load_config(), fake) is None
    assert len(fake.calls) == 2
