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
    {'bullets': [{'text': 'word ' * 31, 'item_keys': ['0']}]*3},
    {'bullets': [{'text': '@everyone', 'item_keys': ['0']}]*3},
    {'bullets': []}, {'bullets': [None]*3}])
def test_retry_then_fallback(bad: dict) -> None:
    for bullet in bad['bullets']:
        if isinstance(bullet, dict):
            bullet.setdefault('text_zh', '工具更新')
    fake = FakeLLM([bad, GOOD])
    assert sixty(ITEMS, fake, load_config()) == ([item.headline for item in ITEMS], [item.zh['headline'] for item in ITEMS])
    assert json.loads(fake.calls[1]['user'])['validation_problems']
    fake = FakeLLM([bad, bad])
    assert sixty(ITEMS, fake, load_config()) == ([item.headline for item in ITEMS], [item.zh['headline'] for item in ITEMS])
    assert len(fake.calls) == 2


def test_success_once() -> None:
    fake = FakeLLM([GOOD])
    assert sixty(ITEMS, fake, load_config()) == ([item.headline for item in ITEMS], [item.zh['headline'] for item in ITEMS])
    assert len(fake.calls) == 1


@pytest.mark.parametrize('text', ['', '新' * 61, '支持 999 个工具', '标题 2', '@everyone'])
def test_chinese_bullet_retry_and_matching_fallback(text: str) -> None:
    bad = {'bullets': [{**bullet, 'text_zh': text} for bullet in GOOD['bullets']]}
    fake = FakeLLM([bad, bad])
    english, chinese = sixty(ITEMS, fake, load_config())
    assert english == [item.headline for item in ITEMS]
    assert chinese == [item.zh['headline'] for item in ITEMS]
    assert json.loads(fake.calls[1]['user'])['validation_problems']


def test_bullet_provenance_success_and_fallback() -> None:
    keys: list[list[str]] = []
    sixty(ITEMS, FakeLLM([{'bullets': list(reversed(GOOD['bullets']))}]), load_config(), keys)
    assert keys == [[item.key] for item in reversed(ITEMS)]
    sixty(ITEMS, FakeLLM([{'bullets': []}] * 2), load_config(), keys)
    assert keys == [[item.key] for item in ITEMS]
