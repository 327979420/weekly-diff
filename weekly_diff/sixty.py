"""Write and verify a short issue overview, with deterministic fallback."""
import json
import logging
from pathlib import Path
import re

from weekly_diff.llm.base import LLMClient, LLMError, strict_schema
from weekly_diff.models import Item
from weekly_diff.validate import number_problems


def _validate(response: dict, items: list[Item]) -> list[str]:
    if not isinstance(response, dict) or set(response) != {'bullets'}:
        return ['invalid overview response']
    bullets = response['bullets']
    if not isinstance(bullets, list) or len(bullets) != 3:
        return ['exactly three bullets required']
    evidence = {item.key: item.headline + '\n' + item.summary for item in items}
    problems = []
    for bullet in bullets:
        if (not isinstance(bullet, dict) or set(bullet) != {'text', 'item_keys'}
                or not isinstance(bullet['text'], str) or not isinstance(bullet['item_keys'], list)):
            problems.append('invalid bullet fields')
            continue
        text, keys = bullet['text'], bullet['item_keys']
        if not text.strip() or len(text.split()) > 30:
            problems.append('bullet must contain 1 to 30 words')
        if re.search(r'@(?:everyone|here)\b', text, re.I):
            problems.append('broadcast mention is forbidden')
        if not keys or any(not isinstance(key, str) or key not in evidence for key in keys):
            problems.append('bullet must reference existing item keys')
        else:
            problems.extend(number_problems(text, '\n'.join(evidence[key] for key in keys)))
    return problems


def sixty(items: list[Item], llm: LLMClient) -> list[str]:
    if len(items) < 3:
        raise ValueError('At least three items needed for sixty seconds')
    schema = strict_schema({'type': 'object', 'properties': {'bullets': {
        'type': 'array', 'minItems': 3, 'maxItems': 3, 'items': {'type': 'object', 'properties': {
            'text': {'type': 'string'}, 'item_keys': {'type': 'array', 'items': {'type': 'string'}}}}}}})
    system = Path(__file__).with_name('prompts').joinpath('sixty.md').read_text(encoding='utf-8')
    payload = [{'key': item.key, 'headline': item.headline, 'summary': item.summary} for item in items]
    problems: list[str] = []
    for attempt in range(2):
        user = json.dumps({'items': payload, 'validation_problems': problems})
        try:
            response = llm.complete_json(system, user, schema, max_tokens=len(system) + len(json.dumps(schema)))
            problems = _validate(response, items)
            if not problems:
                return [bullet['text'] for bullet in response['bullets']]
        except (LLMError, json.JSONDecodeError):
            problems = ['overview completion failed']
    logging.getLogger(__name__).warning('Sixty seconds failed validation; using top headlines')
    return [' '.join(item.headline.split()[:30]) for item in items[:3]]
