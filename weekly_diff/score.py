"""Bounded heuristic preselection followed by validated LLM scoring."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

from weekly_diff.config import Config
from weekly_diff.llm.base import InvalidJSON, LLMClient, LLMError, strict_schema
from weekly_diff.models import Candidate, JSONModel
from weekly_diff.urls import domain_of, is_primary


@dataclass
class Scored(JSONModel):
    candidate: Candidate
    relevant: bool
    section: str
    tag: str
    score: int
    reason: str
    try_now: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Scored':
        return cls(**{**data, 'candidate': Candidate.from_dict(data['candidate'])})


def signal_score(candidate: Candidate) -> float:
    return sum(math.log1p(max(0, candidate.signals.get(name, 0)))
               for name in ('hn_points', 'stars_gained', 'likes', 'release_count', 'reddit_score'))


def _heuristic(candidate: Candidate, cfg: Config, now: datetime) -> float:
    age = max(0, (now - candidate.published_at).total_seconds() / 86400) if candidate.published_at else None
    recency = 1 / (1 + age) if age is not None else 0
    return 2 * is_primary(candidate.url, cfg.sources.primary_domains) + signal_score(candidate) + recency


def _shortlist(candidates: list[Candidate], cfg: Config) -> list[Candidate]:
    now = datetime.now(timezone.utc)
    ranked = sorted(candidates, key=lambda c: (-_heuristic(c, cfg, now), c.key))
    github = sorted((c for c in candidates if c.source_type == 'github_trending'),
                    key=lambda c: (-c.signals.get('stars_gained', 0), c.key))[:10]
    reserved = {c.key for c in github}
    # Reserve slots within the cap; the explicit top-ten guarantee wins for smaller caps.
    others = [c for c in ranked if c.key not in reserved]
    kept = github + others[:max(0, cfg.llm.max_candidates_to_score - len(github))]
    return sorted(kept, key=lambda c: (-_heuristic(c, cfg, now), c.key))


def _schema(cfg: Config) -> dict:
    properties = {'id': {'type': 'string'}, 'relevant': {'type': 'boolean'},
                  'try_now': {'type': 'boolean'},
                  'section': {'type': 'string', 'enum': [s.key for s in cfg.issue.sections]},
                  'tag': {'type': 'string', 'enum': list(cfg.tags)},
                  'score': {'type': 'integer', 'minimum': 0, 'maximum': 10},
                  'reason': {'type': 'string', 'description': 'At most 20 words'}}
    return strict_schema({'type': 'object', 'properties': {
        'items': {'type': 'array', 'items': {'type': 'object', 'properties': properties}}}})


def _validate(data: dict, ids: set[str], cfg: Config) -> dict[str, dict]:
    if not isinstance(data, dict) or set(data) != {'items'} or not isinstance(data['items'], list):
        raise InvalidJSON('Invalid scoring response')
    result = {}
    fields = set(_schema(cfg)['properties']['items']['items']['properties'])
    for row in data['items']:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            raise InvalidJSON('Invalid scoring item')
        if row['id'] not in ids:
            continue
        if (set(row) != fields or type(row['relevant']) is not bool
                or type(row['try_now']) is not bool
                or type(row['score']) is not int or not 0 <= row['score'] <= 10
                or not isinstance(row['section'], str)
                or row['section'] not in [s.key for s in cfg.issue.sections]
                or not isinstance(row['tag'], str) or row['tag'] not in cfg.tags
                or not isinstance(row['reason'], str)
                or len(row['reason'].split()) > 20 or row['id'] in result):
            raise InvalidJSON('Invalid scoring item')
        result[row['id']] = row
    return result


def _batch(batch: list[Candidate], cfg: Config, llm: LLMClient, system: str) -> list[Scored]:
    user = json.dumps([{'id': c.key, 'title': c.title, 'source_name': c.source_name,
                        'domain': domain_of(c.url), 'signals': c.signals, 'text': c.text[:300]}
                       for c in batch])
    schema = _schema(cfg)
    for attempt in range(2):
        try:
            # A conservative budget derived from payload/schema size, scaling with the batch.
            response = llm.complete_json(system, user, schema, max_tokens=len(user) + len(json.dumps(schema)))
            rows = _validate(response, {c.key for c in batch}, cfg)
            break
        except (InvalidJSON, json.JSONDecodeError):
            if attempt:
                raise LLMError('Invalid scoring response after retry') from None
    result = []
    forced = {'github_trending': 'github', 'github_release': 'tools', 'huggingface': 'models'}
    for candidate in batch:
        row = rows.get(candidate.key, {'relevant': False, 'section': 'quick', 'tag': 'watch', 'try_now': False,
                                      'score': 0, 'reason': 'Missing from scoring response'})
        section = ('quick' if candidate.key.startswith('hfspace:')
                   else forced.get(candidate.source_type, row['section']))
        result.append(Scored(candidate, row['relevant'], section,
                             row['tag'], row['score'], row['reason'], row['try_now']))
    return result


def score(candidates: list[Candidate], cfg: Config, llm: LLMClient) -> list[Scored]:
    if cfg.llm.score_batch_size <= 0:
        raise ValueError('llm.score_batch_size must be positive')
    system = Path(__file__).with_name('prompts').joinpath('score.md').read_text(encoding='utf-8')
    system += '\nConfigured primary domains and labs: ' + ', '.join(cfg.sources.primary_domains)
    system += '\nLab sources: ' + ', '.join(s.name for s in (*cfg.sources.rss, *cfg.sources.html_index.pages))
    system += '\nSections: ' + json.dumps({s.key: s.title for s in cfg.issue.sections})
    system += '\nTags: ' + json.dumps(cfg.tags)
    shortlisted = _shortlist(candidates, cfg)
    return [item for start in range(0, len(shortlisted), cfg.llm.score_batch_size)
            for item in _batch(shortlisted[start:start + cfg.llm.score_batch_size], cfg, llm, system)]
