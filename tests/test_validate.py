from dataclasses import replace
import json
from pathlib import Path

import pytest

from weekly_diff.config import load_config
from weekly_diff.models import Item, Issue
from weekly_diff.validate import number_problems, single_sentence, validate_item, validate_issue

DATA = json.loads((Path(__file__).parent / 'fixtures/models.json').read_text())
BASE = replace(Item.from_dict(DATA['item']), tag='try')


@pytest.mark.parametrize(('change', 'problem'), [
    ({'summary': 'Improves by 999%.'}, 'unsupported number'),
    ({'summary': 'First sentence. Another sentence.'}, 'single sentence'),
    ({'headline': ''}, 'non-empty'), ({'source_url': 'ftp://example.com'}, 'http(s)'),
    ({'source_url': 'https:///missing'}, 'http(s)'),
    ({'tag': 'invalid'}, 'invalid tag'), ({'section': 'invalid'}, 'invalid section'),
    ({'summary': '@everyone read this.'}, 'mention'), ({'why_it_matters': '@here'}, 'mention'),
    ({'for_builders': ''}, 'non-empty'), ({'headline': 'x' * 91}, '90'),
    ({'summary': 'word ' * 26}, '25'), ({'why_it_matters': 'word ' * 41}, '40'),
    ({'for_builders': 'word ' * 31}, '30'), ({'headline': '🚀 New'}, 'emoji')])
def test_item_rejections(change: dict, problem: str) -> None:
    assert any(problem in p for p in validate_item(replace(BASE, **change), '', load_config()))


def test_number_normalisation_and_title() -> None:
    assert not number_problems('$1,000 and 40% on v2.1 with 4.5', '$1 000 40% v2.1 4.5')
    assert number_problems('40', '140 4.0')
    assert number_problems('2.1', '2.10')
    assert not validate_item(replace(BASE, headline='Version v2.1', extra={'candidate_title': 'v2.1'}), '', load_config())


@pytest.mark.parametrize('text', ['Version v2.1 ships.', 'Costs $4.5 per call.', 'Try it, e.g. locally.'])
def test_single_sentence_versions(text: str) -> None:
    assert single_sentence(text)


def issue() -> Issue:
    result = Issue.from_dict(DATA['issue'])
    result.sixty_seconds_zh = ['新闻', '工具', '模型']
    result.sixty_seconds = ['First', 'Second', 'Third']
    result.sections = {section: [replace(BASE, section=section, key=f'{section}{i}', source_url=f'https://example.com/{section}/{i}')
                                 for i in range(2)] for section in ('models', 'tools', 'github')}
    result.top = [item.key for item in result.items()][:5]
    return result


def test_issue_valid_and_duplicate_url() -> None:
    good = issue()
    assert not validate_issue(good, load_config())
    good.sections['tools'][0].source_url = good.sections['models'][0].source_url + '?utm_source=test'
    assert 'duplicate source URL' in validate_issue(good, load_config())


@pytest.mark.parametrize('kind', ['bullets', 'count', 'keys', 'top', 'section', 'item'])
def test_issue_rejections(kind: str) -> None:
    bad = issue()
    if kind == 'bullets':
        bad.sixty_seconds = ['', 'long ' * 31]
    elif kind == 'count':
        bad.sections = {}
    elif kind == 'keys':
        bad.sections['models'][1].key = bad.sections['models'][0].key
    elif kind == 'top':
        bad.top = ['nonexistent'] * 5
    elif kind == 'section':
        bad.sections['models'][0].section = 'tools'
    else:
        bad.sections['models'][0].summary = 'Invented 100.'
    assert validate_issue(bad, load_config())


def test_saved_evidence_is_revalidated() -> None:
    original = issue()
    item = original.sections['models'][0]
    item.summary = 'You can use v2.1 for 1,000 requests.'
    item.extra = {'source_text': 'Supports 1 000 requests.', 'candidate_title': 'Version v2.1'}
    restored = Issue.from_dict(original.to_dict())
    assert not validate_issue(restored, load_config())
    restored.sections['models'][0].summary = 'You can use v2.1 for 2,000 requests.'
    assert any('unsupported number' in problem for problem in validate_issue(restored, load_config()))


@pytest.mark.parametrize('limit', [24, 90, 110])
def test_configured_headline_limit(limit: int) -> None:
    cfg = load_config()
    cfg = replace(cfg, issue=replace(cfg.issue, max_headline_chars=limit))
    assert not validate_item(replace(BASE, headline='x' * limit), '', cfg)
    assert validate_item(replace(BASE, headline='x' * (limit + 1)), '', cfg) == [
        f'headline exceeds {limit} characters']


@pytest.mark.parametrize(('field', 'value', 'problem'), [
    ('headline', '新' * 41, '40 characters'),
    ('summary', '', 'non-empty'),
    ('summary', '新' * 51, '50 characters'),
    ('why_it_matters', '新' * 81, '80 characters'),
    ('for_builders', '新' * 61, '60 characters'),
    ('for_builders', '', 'non-empty'),
    ('summary', '先更新。再运行。', 'single sentence'),
    ('summary', '使用工具🛠️', 'emoji'),
    ('summary', '@everyone', 'mention'),
])
def test_chinese_validation(field: str, value: str, problem: str) -> None:
    item = replace(BASE, zh={**BASE.zh, field: value})
    assert any(problem in p for p in validate_item(item, '', load_config()))


@pytest.mark.parametrize('field', ['headline', 'summary', 'why_it_matters', 'for_builders'])
def test_chinese_numbers_require_evidence(field: str) -> None:
    item = replace(BASE, zh={**BASE.zh, field: '你可以用 v2.1 处理 999 次请求'})
    assert any('999' in p for p in validate_item(item, 'v2.1', load_config()))
    assert not validate_item(item, 'v2.1 supports 999 requests', load_config())


@pytest.mark.parametrize('emoji', [None, '', 'abc', '🚀🚀', '🛠️工具', '\u200d', '👩\u200d'])
def test_invalid_emoji(emoji: str | None) -> None:
    assert any('emoji' in p for p in validate_item(replace(BASE, emoji=emoji), '', load_config()))


@pytest.mark.parametrize('emoji', ['🚀', '🛠️', '👩🏽\u200d💻', '🇨🇳', '1️⃣'])
def test_valid_emoji(emoji: str) -> None:
    assert not validate_item(replace(BASE, emoji=emoji), '', load_config())


@pytest.mark.parametrize(('summary', 'valid'), [
    ('You can use the tool.', True), ('It helps YOUR work.', True),
    ('A tool for young builders.', False), ('A tool for yourself.', False),
    ('The tool has been updated.', False),
])
def test_english_summary_addresses_reader(summary: str, valid: bool) -> None:
    problems = validate_item(replace(BASE, summary=summary), '', load_config())
    assert (not problems) == valid
    if not valid:
        assert problems == ['summary must address the reader using you or your']


@pytest.mark.parametrize(('summary', 'valid'), [('你可以使用这个工具。', True), ('工具已更新。', False)])
def test_chinese_summary_addresses_reader(summary: str, valid: bool) -> None:
    item = replace(BASE, zh={**BASE.zh, 'summary': summary})
    problems = validate_item(item, '', load_config())
    assert (not problems) == valid
    if not valid:
        assert problems == ['zh.summary must address the reader using 你']


@pytest.mark.parametrize('tag', ['try', 'learn', 'watch'])
def test_new_tags_accepted(tag: str) -> None:
    assert not validate_item(replace(BASE, tag=tag), '', load_config())


@pytest.mark.parametrize('tag', ['builders', 'work', 'beginner'])
def test_legacy_tags_not_generated(tag: str) -> None:
    assert 'invalid tag' in validate_item(replace(BASE, tag=tag), '', load_config())
