from dataclasses import replace
import json
from pathlib import Path

import pytest

from weekly_diff.config import load_config
from weekly_diff.llm.fake import FakeLLM
from weekly_diff.models import Item
from weekly_diff.sixty import sixty

BASE = Item.from_dict(json.loads((Path(__file__).parent / 'fixtures/models.json').read_text())['item'])
ITEMS = [replace(BASE, key=str(i), headline=f'Headline {i}', summary='Supports v2.1.', zh={**BASE.zh, 'headline': f'标题 {i}'}) for i in range(3)]
GOOD = {'bullets': [{'text': item.headline, 'text_zh': item.zh['headline'], 'item_keys': [item.key]} for item in ITEMS]}


@pytest.mark.parametrize('bad', [
    {'bullets': [{'text': 'Gained 999.', 'item_keys': ['0']}]*3},
    {'bullets': [{'text': 'Headline 2', 'item_keys': ['0']}]*3},
    {'bullets': [{'text': 'News', 'item_keys': ['missing']}]*3},
    {'bullets': [{'text': 'News', 'item_keys': []}]*3},
    {'bullets': [{'text': '@everyone', 'item_keys': ['0']}]*3},
    {'bullets': []}, {'bullets': [None]*3}])
def test_retry_then_fallback(bad: dict) -> None:
    for bullet in bad['bullets']:
        if isinstance(bullet, dict):
            bullet.setdefault('text_zh', '工具更新')
    fake = FakeLLM([bad, GOOD])
    assert sixty(ITEMS, fake, load_config(Path(__file__).parent / 'fixtures/config.yaml')) == ([item.headline for item in ITEMS], [item.zh['headline'] for item in ITEMS])
    assert json.loads(fake.calls[1]['user'])['validation_problems']
    fake = FakeLLM([bad, bad])
    assert sixty(ITEMS, fake, load_config(Path(__file__).parent / 'fixtures/config.yaml')) == ([item.headline for item in ITEMS], [item.zh['headline'] for item in ITEMS])
    assert len(fake.calls) == 2


def test_success_once() -> None:
    fake = FakeLLM([GOOD])
    assert sixty(ITEMS, fake, load_config(Path(__file__).parent / 'fixtures/config.yaml')) == ([item.headline for item in ITEMS], [item.zh['headline'] for item in ITEMS])
    assert len(fake.calls) == 1


@pytest.mark.parametrize('text', ['', '支持 999 个工具', '标题 2', '@everyone'])
def test_chinese_bullet_retry_and_matching_fallback(text: str) -> None:
    bad = {'bullets': [{**bullet, 'text_zh': text} for bullet in GOOD['bullets']]}
    fake = FakeLLM([bad, bad])
    english, chinese = sixty(ITEMS, fake, load_config(Path(__file__).parent / 'fixtures/config.yaml'))
    assert english == [item.headline for item in ITEMS]
    assert chinese == [item.zh['headline'] for item in ITEMS]
    assert json.loads(fake.calls[1]['user'])['validation_problems']


def test_bullet_provenance_success_and_fallback() -> None:
    keys: list[list[str]] = []
    sixty(ITEMS, FakeLLM([{'bullets': list(reversed(GOOD['bullets']))}]), load_config(Path(__file__).parent / 'fixtures/config.yaml'), keys)
    assert keys == [[item.key] for item in reversed(ITEMS)]
    sixty(ITEMS, FakeLLM([{'bullets': []}] * 2), load_config(Path(__file__).parent / 'fixtures/config.yaml'), keys)
    assert keys == [[item.key] for item in ITEMS]


@pytest.mark.parametrize('chinese', [False, True])
def test_overlong_bullets_shortened_after_retry(chinese: bool, caplog: pytest.LogCaptureFixture) -> None:
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    field = 'text_zh' if chinese else 'text'
    prefix = '工具可以使用。' if chinese else 'The tool is available. '
    text = prefix + ('更多工具' * cfg.content.max_bullet_chars_zh if chinese
                     else 'more tools ' * cfg.content.max_bullet_words)
    row = {'bullets': [{**bullet, field: text} for bullet in GOOD['bullets']]}
    fake = FakeLLM([row, row])
    keys: list[list[str]] = []
    english, zh = sixty(ITEMS, fake, cfg, keys)
    assert (zh if chinese else english) == [prefix.strip()] * 3
    assert keys == [[item.key] for item in ITEMS]
    assert len(fake.calls) == 2
    assert 'using top headlines' not in caplog.text
    assert row['bullets'][0][field] == text


def test_length_repair_never_hides_unsupported_bullet_number() -> None:
    row = {'bullets': [{**bullet, 'text': 'You can use tools; ' + 'tools ' * 31 + '999'}
                       for bullet in GOOD['bullets']]}
    assert sixty(ITEMS, FakeLLM([row, row]), load_config(Path(__file__).parent / 'fixtures/config.yaml'))[0] == [item.headline for item in ITEMS]


@pytest.mark.parametrize('chinese', [False, True])
def test_banned_highlights_retry_then_clean(chinese: bool) -> None:
    field = 'text_zh' if chinese else 'text'
    phrase = '重磅' if chinese else 'Revolutionary '
    row = {'bullets': [{**bullet, field: phrase + bullet[field]} for bullet in GOOD['bullets']]}
    fake = FakeLLM([row, row])
    assert sixty(ITEMS, fake, load_config(Path(__file__).parent / 'fixtures/config.yaml')) == ([i.headline for i in ITEMS], [i.zh['headline'] for i in ITEMS])
    assert len(fake.calls) == 2
    assert 'banned phrase:' in fake.calls[1]['user']


@pytest.mark.parametrize('chinese', [False, True])
def test_full_first_sentence_survives_length_target_after_retry(chinese: bool) -> None:
    field = 'text_zh' if chinese else 'text'
    first = '完整句子' * 30 + '。' if chinese else 'Complete sentence ' * 20 + '.'
    row = {'bullets': [{**bullet, field: first + (' 后续句子。' if chinese else ' Later details.')}
                       for bullet in GOOD['bullets']]}
    fake = FakeLLM([row, row])
    result = sixty(ITEMS, fake, load_config(Path(__file__).parent / 'fixtures/config.yaml'))
    assert result[int(chinese)] == [first] * 3
    assert len(fake.calls) == 2


def test_fallback_never_crops_a_headline() -> None:
    from weekly_diff.sixty import _fallback
    assert _fallback('A headline with more words than fit', 3, words=True) == 'A headline with more words than fit.'
    assert _fallback('完整的标题不能在中间截断', 4, words=False) == '完整的标题不能在中间截断。'
