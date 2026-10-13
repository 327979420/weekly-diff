"""Evidence-grounded item writing with one corrective retry."""
from copy import deepcopy
from collections import Counter
import json
import logging
from pathlib import Path

from weekly_diff.config import Config
from weekly_diff.editorial import opening, strip_banned
from weekly_diff.llm.base import LLMClient, LLMError, strict_schema
from weekly_diff.models import Candidate, Item
from weekly_diff.score import Scored
from weekly_diff.shorten import only_length_problems, shorten, shorten_sentence, full_sentence
from weekly_diff.validate import validate_item


def _schema(cfg: Config) -> dict:
    properties = {field: {'type': 'string'} for field in ('headline', 'summary', 'why_it_matters')}
    chinese = {**properties, 'for_builders': {'type': ['string', 'null']}}
    properties.update(emoji={'type': 'string'}, zh={'type': 'object', 'properties': chinese},
                      for_builders={'type': ['string', 'null']},
                      tag={'type': 'string', 'enum': list(cfg.tags)}, supported={'type': 'boolean'})
    return strict_schema({'type': 'object', 'properties': properties})


def _shorten_item(item: Item, cfg: Config) -> None:
    limits = (
        ('headline', cfg.issue.max_headline_chars, cfg.content.max_headline_chars_zh),
        ('summary', cfg.content.max_summary_words, cfg.content.max_summary_chars_zh),
        ('why_it_matters', cfg.content.max_why_words, cfg.content.max_why_chars_zh),
        ('for_builders', cfg.content.max_builders_words, cfg.content.max_builders_chars_zh),
    )
    for field, english, chinese in limits:
        value = getattr(item, field)
        if value is not None:
            setattr(item, field, shorten_sentence(value, english, words=True) if field == 'summary'
                    else shorten(value, english, words=field != 'headline'))
        if item.zh[field] is not None:
            item.zh[field] = (shorten_sentence(item.zh[field], chinese) if field == 'summary'
                              else shorten(item.zh[field], chinese, chinese=True))
    item.extra['sentence_fallbacks'] = {field: value for field, value in
        (('summary', item.summary), ('zh.summary', item.zh['summary'])) if full_sentence(value)}


def summarise(scored: Scored, source_text: str, cfg: Config, llm: LLMClient, *, notes: list[str] | None = None,
              attempts: int = 2) -> Item | None:
    logger = logging.getLogger(__name__)
    candidate = scored.candidate
    if not source_text.strip():
        logger.warning('Dropped item: no source text')
        return None
    system = Path(__file__).with_name('prompts').joinpath('summarise.md').read_text(encoding='utf-8')
    system = system.format(max_headline_chars=cfg.issue.max_headline_chars, **vars(cfg.content))
    payload = dict(section=scored.section, title=candidate.title, source_name=candidate.source_name,
                   url=candidate.url, SOURCE=source_text)
    schema = _schema(cfg)
    problems: list[str] = []
    for attempt in range(attempts):
        user = json.dumps({**payload, 'validation_problems': [*(notes or []), *problems]})
        try:
            row = llm.complete_json(system, user, schema, max_tokens=cfg.content.summarise_max_tokens)
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
                     "try_now": scored.try_now,
                     'candidate_title': candidate.title, 'source_text': source_text}
            item = Item(candidate.key, scored.section, row['headline'], row['summary'], row['why_it_matters'],
                        row['for_builders'], row['tag'], candidate.url, candidate.source_name,
                        candidate.published_at, scored.score, extra, emoji=row['emoji'],
                        zh=deepcopy(row['zh']), image_url=candidate.extra.get('image_url'))
            problems = validate_item(item, source_text, cfg)
            if attempt == attempts - 1 and problems and all(p.startswith('banned phrase:') for p in problems):
                for field in ('headline', 'summary', 'why_it_matters', 'for_builders'):
                    if getattr(item, field) is not None:
                        setattr(item, field, strip_banned(getattr(item, field)))
                    if item.zh[field] is not None:
                        item.zh[field] = strip_banned(item.zh[field])
                problems = validate_item(item, source_text, cfg)
            length_problems = [p for p in problems if p not in {
                'summary must be a single sentence', 'zh.summary must be a single sentence'}]
            if attempt == attempts - 1 and only_length_problems(length_problems):
                _shorten_item(item, cfg)
                problems = validate_item(item, source_text, cfg)
            if not problems:
                return item
        except (LLMError, json.JSONDecodeError):
            problems = ['summary completion failed']
    action = 'Editorial rewrite rejected; keeping original' if notes else 'Dropped item after retry'
    logger.warning('%s: %s', action, '; '.join(problems))
    return None


def vary_openings(sections: dict[str, list[Item]], cfg: Config, llm: LLMClient) -> None:
    """One editorial rewrite for each excess opening; retain valid originals on failure."""
    counts: dict[str, Counter[str]] = {'en': Counter(), 'zh': Counter()}
    previous = {'en': '', 'zh': ''}
    for rows in sections.values():
        for index, item in enumerate(rows):
            notes = []
            for language, text in (('en', item.summary), ('zh', (item.zh or {}).get('summary', ''))):
                start = opening(text, chinese=language == 'zh')
                if start and (counts[language][start] >= 2 or
                              (start in {'you can', '你可以'} and previous[language] == start)):
                    notes.append(f'{language}: vary the opening; do not start with {start}')
            if notes:
                candidate = Candidate(item.key, item.extra.get('candidate_title', item.headline),
                                      item.source_url, item.source_name, 'rss', item.published_at,
                                      item.extra.get('source_text', ''), True, item.section, {},
                                      deepcopy(item.extra))
                scored = Scored(candidate, True, item.section, item.tag, item.score, 'Editorial variation',
                                try_now=item.extra.get('try_now', False))
                replacement = summarise(scored, candidate.text, cfg, llm, notes=notes, attempts=1)
                if replacement is not None:
                    rows[index] = item = replacement
            for language, text in (('en', item.summary), ('zh', (item.zh or {}).get('summary', ''))):
                start = opening(text, chinese=language == 'zh')
                counts[language][start] += 1
                previous[language] = start
