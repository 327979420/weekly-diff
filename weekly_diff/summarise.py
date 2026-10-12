"""Evidence-grounded item writing with one corrective retry."""
from copy import deepcopy
import json
import logging
from pathlib import Path

from weekly_diff.config import Config
from weekly_diff.llm.base import LLMClient, LLMError, strict_schema
from weekly_diff.models import Item
from weekly_diff.score import Scored
from weekly_diff.validate import validate_item


def _schema(cfg: Config) -> dict:
    properties = {field: {'type': 'string'} for field in ('headline', 'summary', 'why_it_matters')}
    properties.update(for_builders={'type': ['string', 'null']},
                      tag={'type': 'string', 'enum': list(vars(cfg.tags))}, supported={'type': 'boolean'})
    return strict_schema({'type': 'object', 'properties': properties})


def summarise(scored: Scored, source_text: str, cfg: Config, llm: LLMClient) -> Item | None:
    logger = logging.getLogger(__name__)
    candidate = scored.candidate
    if not source_text.strip():
        logger.warning('Dropped item: no source text')
        return None
    system = Path(__file__).with_name('prompts').joinpath('summarise.md').read_text(encoding='utf-8')
    payload = dict(section=scored.section, title=candidate.title, source_name=candidate.source_name,
                   url=candidate.url, SOURCE=source_text)
    schema = _schema(cfg)
    problems: list[str] = []
    for attempt in range(2):
        user = json.dumps({**payload, 'validation_problems': problems})
        try:
            row = llm.complete_json(system, user, schema, max_tokens=len(system) + len(json.dumps(schema)))
            if (not isinstance(row, dict) or set(row) != set(schema['properties'])
                    or type(row['supported']) is not bool
                    or any(not isinstance(row[field], str) for field in ('headline', 'summary', 'why_it_matters', 'tag'))
                    or (row['for_builders'] is not None and not isinstance(row['for_builders'], str))):
                problems = ['invalid summary response fields']
                continue
            if not row['supported']:
                logger.warning('Dropped item: unsupported by source')
                return None
            extra = {**deepcopy(candidate.extra), **candidate.signals,
                     'candidate_title': candidate.title, 'source_text': source_text}
            item = Item(candidate.key, scored.section, row['headline'], row['summary'], row['why_it_matters'],
                        row['for_builders'], row['tag'], candidate.url, candidate.source_name,
                        candidate.published_at, scored.score, extra)
            problems = validate_item(item, source_text, cfg)
            if not problems:
                return item
        except (LLMError, json.JSONDecodeError):
            problems = ['summary completion failed']
    logger.warning('Dropped item after retry: %s', '; '.join(problems))
    return None
