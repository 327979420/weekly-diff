"""Write and verify a short issue overview, with deterministic fallback."""
from copy import deepcopy
import json
import logging
from pathlib import Path
import re

from weekly_diff.config import Config
from weekly_diff.editorial import banned_problems, strip_banned
from weekly_diff.llm.base import LLMClient, LLMError, strict_schema
from weekly_diff.models import Item
from weekly_diff.shorten import only_length_problems, shorten_sentence, full_sentence
from weekly_diff.validate import number_problems


def _validate(response: dict, items: list[Item], cfg: Config, *, sentence_fallback: bool = False) -> list[str]:
    if not isinstance(response, dict) or set(response) != {'bullets'}:
        return ['invalid overview response']
    bullets = response['bullets']
    if not isinstance(bullets, list) or len(bullets) != 3:
        return ['exactly three bullets required']
    evidence = {item.key: '\n'.join((item.headline, item.summary,
                (item.zh or {}).get('headline', ''), (item.zh or {}).get('summary', ''))) for item in items}
    problems = []
    for bullet in bullets:
        if (not isinstance(bullet, dict) or set(bullet) != {'text', 'text_zh', 'item_keys'}
                or not isinstance(bullet['text_zh'], str) or not isinstance(bullet['text'], str) or not isinstance(bullet['item_keys'], list)):
            problems.append('invalid bullet fields')
            continue
        text, keys = bullet['text'], bullet['item_keys']
        for field, limit, words in (('text', cfg.content.max_bullet_words, True),
                                    ('text_zh', cfg.content.max_bullet_chars_zh, False)):
            value = bullet[field]
            problems.extend(banned_problems(value))
            if not value.strip():
                problems.append(f'{field} must be non-empty')
            elif ((len(value.split()) if words else len(value)) > limit
                  and not (sentence_fallback and full_sentence(value))):
                unit = 'words' if words else 'characters'
                problems.append(f'{field} exceeds {limit} {unit}')
        if re.search(r'@(?:everyone|here)\b', text + ' ' + bullet['text_zh'], re.I):
            problems.append('broadcast mention is forbidden')
        if not keys or any(not isinstance(key, str) or key not in evidence for key in keys):
            problems.append('bullet must reference existing item keys')
        else:
            for value in (text, bullet['text_zh']):
                problems.extend(number_problems(value, '\n'.join(evidence[key] for key in keys)))
    return problems


def sixty(items: list[Item], llm: LLMClient, cfg: Config,
          item_keys: list[list[str]] | None = None) -> tuple[list[str], list[str]]:
    if len(items) < 3:
        raise ValueError('At least three items needed for sixty seconds')
    schema = strict_schema({'type': 'object', 'properties': {'bullets': {
        'type': 'array', 'minItems': 3, 'maxItems': 3, 'items': {'type': 'object', 'properties': {
            'text': {'type': 'string'}, 'text_zh': {'type': 'string'}, 'item_keys': {'type': 'array', 'items': {'type': 'string'}}}}}}})
    system = Path(__file__).with_name('prompts').joinpath('sixty.md').read_text(encoding='utf-8')
    system = system.format(**vars(cfg.content))
    payload = [{'key': item.key, 'headline': item.headline, 'summary': item.summary, 'zh': item.zh} for item in items]
    problems: list[str] = []
    for attempt in range(2):
        user = json.dumps({'items': payload, 'validation_problems': problems})
        try:
            response = llm.complete_json(system, user, schema, max_tokens=len(system) + len(json.dumps(schema)))
            problems = _validate(response, items, cfg)
            if attempt == 1 and problems and all(p.startswith('banned phrase:') for p in problems):
                response = deepcopy(response)
                for bullet in response['bullets']:
                    for field in ('text', 'text_zh'):
                        bullet[field] = strip_banned(bullet[field])
                problems = _validate(response, items, cfg)
            if attempt == 1 and only_length_problems(problems):
                response = deepcopy(response)
                for bullet in response['bullets']:
                    bullet['text'] = shorten_sentence(bullet['text'], cfg.content.max_bullet_words, words=True)
                    bullet['text_zh'] = shorten_sentence(bullet['text_zh'], cfg.content.max_bullet_chars_zh)
                problems = _validate(response, items, cfg, sentence_fallback=True)
            if not problems:
                if item_keys is not None:
                    item_keys[:] = [bullet['item_keys'] for bullet in response['bullets']]
                return ([bullet['text'] for bullet in response['bullets']],
                        [bullet['text_zh'] for bullet in response['bullets']])
        except (LLMError, json.JSONDecodeError):
            problems = ['overview completion failed']
    logging.getLogger(__name__).warning('Sixty seconds failed validation; using top headlines')
    if item_keys is not None:
        item_keys[:] = [[item.key] for item in items[:3]]
    return ([_fallback(item.headline, cfg.content.max_bullet_words, words=True) for item in items[:3]],
            [_fallback((item.zh or {}).get('headline', ''), cfg.content.max_bullet_chars_zh,
                       words=False) for item in items[:3]])


def _fallback(text: str, limit: int, *, words: bool) -> str:
    if (len(text.split()) if words else len(text)) <= limit:
        return text
    # A headline fallback must never be sliced in the middle of a clause either.
    return shorten_sentence(text if full_sentence(text) else text + ('.' if words else '。'),
                            limit, words=words)
