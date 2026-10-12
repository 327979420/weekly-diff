from dataclasses import replace
import json
from pathlib import Path

import pytest

from weekly_diff.llm.fake import FakeLLM
from weekly_diff.models import Item
from weekly_diff.sixty import sixty

BASE = Item.from_dict(json.loads((Path(__file__).parent / 'fixtures/models.json').read_text())['item'])
ITEMS = [replace(BASE, key=str(i), headline=f'Headline {i}', summary='Supports v2.1.') for i in range(3)]
GOOD = {'bullets': [{'text': item.headline, 'item_keys': [item.key]} for item in ITEMS]}


@pytest.mark.parametrize('bad', [
    {'bullets': [{'text': 'Gained 999.', 'item_keys': ['0']}]*3},
    {'bullets': [{'text': 'Headline 2', 'item_keys': ['0']}]*3},
    {'bullets': [{'text': 'News', 'item_keys': ['missing']}]*3},
    {'bullets': [{'text': 'News', 'item_keys': []}]*3},
    {'bullets': [{'text': 'word ' * 31, 'item_keys': ['0']}]*3},
    {'bullets': [{'text': '@everyone', 'item_keys': ['0']}]*3},
    {'bullets': []}, {'bullets': [None]*3}])
def test_retry_then_fallback(bad: dict) -> None:
    fake = FakeLLM([bad, GOOD])
    assert sixty(ITEMS, fake) == [item.headline for item in ITEMS]
    assert json.loads(fake.calls[1]['user'])['validation_problems']
    fake = FakeLLM([bad, bad])
    assert sixty(ITEMS, fake) == [item.headline for item in ITEMS]
    assert len(fake.calls) == 2


def test_success_once() -> None:
    fake = FakeLLM([GOOD])
    assert sixty(ITEMS, fake) == [item.headline for item in ITEMS]
    assert len(fake.calls) == 1
