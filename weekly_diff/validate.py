"""Pure structural and numeric evidence checks for generated copy."""
from collections import Counter
import re
from urllib.parse import urlsplit

from weekly_diff.config import Config
from weekly_diff.models import Issue, Item
from weekly_diff.urls import canonical_url

# Keep decimals and dotted versions intact; grouped thousands compare without separators.
_NUMBER = re.compile(r'(?<!\d)(?:\d{1,3}(?:[,\s]\d{3})+(?!\d)|\d+)(?:\.\d+)*')


def numbers(text: str) -> set[str]:
    return {re.sub(r'[,\s]', '', match.group()) for match in _NUMBER.finditer(text)}


def number_problems(text: str, evidence: str) -> list[str]:
    return ['unsupported number: ' + number for number in sorted(numbers(text) - numbers(evidence))]


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def single_sentence(text: str) -> bool:
    # Decimal/version dots and common abbreviations do not end a sentence.
    cleaned = re.sub(r'(?<=\d)\.(?=\d)', '', text)
    cleaned = re.sub(r'\b(?:e\.g\.|i\.e\.|Mr\.|Mrs\.|Dr\.|vs\.)', '', cleaned)
    return not re.search(r'[.!?]+[\"\u201d\u2019\)]*\s*\S', cleaned.rstrip('.!?"\u201d\u2019) '))


def validate_item(item: Item, source_text: str, cfg: Config) -> list[str]:
    problems = []
    for field in ('key', 'headline', 'summary', 'why_it_matters', 'source_name', 'source_url'):
        if not _nonempty(getattr(item, field)):
            problems.append(f'{field} must be non-empty')
    if item.for_builders is not None and not _nonempty(item.for_builders):
        problems.append('for_builders must be null or non-empty')
    if isinstance(item.headline, str) and len(item.headline) > 80:
        problems.append('headline exceeds 80 characters')
    for field, limit in (('summary', 35), ('why_it_matters', 40), ('for_builders', 30)):
        value = getattr(item, field)
        if isinstance(value, str) and len(value.split()) > limit:
            problems.append(f'{field} exceeds {limit} words')
    if isinstance(item.summary, str) and not single_sentence(item.summary):
        problems.append('summary must be a single sentence')
    if not isinstance(item.tag, str) or item.tag not in vars(cfg.tags):
        problems.append('invalid tag')
    if not isinstance(item.section, str) or item.section not in {section.key for section in cfg.issue.sections}:
        problems.append('invalid section')
    try:
        url = urlsplit(item.source_url)
        if url.scheme not in {'http', 'https'} or not url.hostname or re.search(r'\s', item.source_url):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        problems.append('source_url must be an http(s) URL')
    generated = ' '.join(value for value in (item.headline, item.summary, item.why_it_matters,
                                            item.for_builders) if isinstance(value, str))
    if re.search(r'@(?:everyone|here)\b', generated, re.I):
        problems.append('broadcast mention is forbidden')
    if isinstance(item.headline, str) and re.search('[\U0001f000-\U0001faff\u2600-\u27bf]', item.headline):
        problems.append('headline must not contain emoji')
    problems.extend(number_problems(generated, source_text + '\n' + item.extra.get('candidate_title', '')))
    return problems


def validate_issue(issue: Issue, cfg: Config) -> list[str]:
    problems = []
    items = list(issue.items())
    if len(issue.sixty_seconds) != 3 or any(not _nonempty(bullet) or len(bullet.split()) > 30
                                          for bullet in issue.sixty_seconds):
        problems.append('sixty_seconds must contain exactly 3 non-empty bullets of at most 30 words')
    if not cfg.issue.hard_min_items <= len(items) <= cfg.issue.max_items:
        problems.append('item count outside configured bounds')
    keys = [item.key for item in items]
    if len(set(keys)) != len(keys):
        problems.append('duplicate item key')
    urls = []
    for section, rows in issue.sections.items():
        if section not in {setting.key for setting in cfg.issue.sections}:
            problems.append('invalid issue section')
        for item in rows:
            if item.section != section:
                problems.append('item section does not match its container')
            problems.extend(validate_item(item, item.extra.get('source_text', ''), cfg))
            try:
                urls.append(canonical_url(item.source_url))
            except (ValueError, TypeError):
                pass
    if len(set(urls)) != len(urls):
        problems.append('duplicate source URL')
    if (len(issue.top) != min(cfg.issue.top_items, len(items)) or len(set(issue.top)) != len(issue.top)
            or not set(issue.top) <= set(keys)):
        problems.append('top must contain the configured number of distinct existing keys')
    counts = Counter(item.section for item in items if item.key in issue.top)
    if any(count > cfg.issue.max_top_per_section for count in counts.values()):
        problems.append('top exceeds per-section limit')
    return problems
