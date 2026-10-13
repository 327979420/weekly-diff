"""Merge URL identities, model variants and nearby stories without losing provenance."""
from copy import deepcopy
from datetime import timedelta
import re

from weekly_diff.config import Config
from weekly_diff.models import Candidate
from weekly_diff.seen import Seen, is_seen
from weekly_diff.urls import canonical_url, is_primary

_STOPWORDS = frozenset('a an and are as at be by for from in is it of on or that the this to with'.split())
_SUFFIX = re.compile(r'[-_](?:\d+(?:\.\d+)?[bm]|instruct|base|fp\d+|bf\d+|gguf|awq|gptq|int\d+|q\d+(?:_[a-z0-9]+)*)$', re.I)


def _family(candidate: Candidate) -> tuple[str, str] | None:
    if candidate.source_type != 'huggingface':
        return None
    author, _, name = candidate.title.partition('/')
    if not name:
        return None
    while (shorter := _SUFFIX.sub('', name)) != name:
        name = shorter
    return str(candidate.extra.get('author') or author).lower(), name.lower()


def _preference(candidate: Candidate, cfg: Config) -> tuple[bool, bool, float]:
    return (is_primary(candidate.url, cfg.sources.primary_domains), candidate.primary,
            sum(candidate.signals.values()))


def _near(left: Candidate, right: Candidate, cfg: Config) -> bool:
    # Different model families/authors must not disappear through fuzzy title matching.
    if _family(left) and _family(right):
        return _family(left) == _family(right)
    left_names, right_names = product_names(left.title), product_names(right.title)
    if left_names and right_names and not left_names & right_names:
        return False
    if left.published_at is None or right.published_at is None:
        return False
    if abs(left.published_at - right.published_at) > timedelta(days=3):
        return False
    a = set(re.findall(r'\w+', left.title.lower())) - _STOPWORDS
    b = set(re.findall(r'\w+', right.title.lower())) - _STOPWORDS
    return bool(a and b) and len(a & b) / len(a | b) >= cfg.dedupe.title_similarity


def _merge(left: Candidate, right: Candidate, cfg: Config, variants: bool) -> Candidate:
    if variants:
        winner, other = sorted((left, right), key=lambda c: c.signals.get('likes', 0), reverse=True)
    elif canonical_url(left.url) == canonical_url(right.url):
        # HN inherits the linked domain's primary flag, but its text is commentary.
        winner, other = sorted((left, right), key=lambda c: (
            c.source_type != 'hackernews', *_preference(c, cfg)), reverse=True)
    elif product_names(left.title) & product_names(right.title):
        winner, other = sorted((left, right), key=lambda c: (is_primary(c.url, cfg.sources.primary_domains),
            c.primary, c.source_type in {'rss', 'html_index', 'github_release'},
            *_preference(c, cfg)), reverse=True)
    else:
        winner, other = sorted((left, right), key=lambda c: _preference(c, cfg), reverse=True)
    result = deepcopy(winner)
    for key, value in other.signals.items():
        result.signals[key] = max(result.signals.get(key, value), value)
    sources = {other.source_name, *left.extra.get('also_seen_on', []), *right.extra.get('also_seen_on', [])}
    result.extra['also_seen_on'] = sorted(sources - {winner.source_name})
    aliases = [*left.extra.get('dedupe_aliases', []), *right.extra.get('dedupe_aliases', []),
               {'key': other.key, 'url': other.url, 'title': other.title}]
    result.extra['dedupe_aliases'] = list({(a['key'], a['url']): a for a in aliases
                                         if a['key'] != winner.key or a['url'] != winner.url}.values())
    names = {*left.extra.get('variants', []), *right.extra.get('variants', [])}
    if variants:
        names.add(other.title)
    if names:
        result.extra['variants'] = sorted(names - {winner.title})
    return result


def dedupe(candidates: list[Candidate], cfg: Config, seen: Seen, issue_id: str) -> list[Candidate]:
    result: list[Candidate] = []
    for candidate in candidates:
        merged = deepcopy(candidate)
        # Restart after a merge so bridge candidates cannot leave duplicate groups behind.
        index = 0
        while index < len(result):
            other = result[index]
            variants = _family(merged) is not None and _family(merged) == _family(other)
            same_product = bool(product_names(merged.title) & product_names(other.title))
            if variants or same_product or canonical_url(merged.url) == canonical_url(other.url) or _near(merged, other, cfg):
                merged = _merge(merged, result.pop(index), cfg, variants)
                index = 0
            else:
                index += 1
        result.append(merged)
    return [c for c in result if not any(is_seen(seen, a['key'], a['url'], issue_id)
            for a in [{'key': c.key, 'url': c.url}, *c.extra.get('dedupe_aliases', [])])]


def product_names(title: str) -> set[str]:
    """Conservative name+version identities, independent of org and packaging."""
    title = re.sub(r'\b[\w.-]+/', '', title.casefold())
    title = re.sub(r'[\s_-]+v(?=\d)', ' ', title)
    # A named version is evidence of identity; generic numbers/specs are not.
    matches = re.finditer(r'\b([a-z]+(?:[-_][a-z]+)*)[\s_-]*v?(\d+(?:[._-]\d+)*)\b', title)
    generic = _STOPWORDS | {'version', 'release', 'model', 'models', 'supports', 'with', 'top', 'v'}
    return {re.sub(r'[-_]', '', match[1]) + ':' + re.sub(r'[_-]', '.', match[2])
            for match in matches if match[1] not in generic}
