"""Pure structural and numeric evidence checks for generated copy."""
from collections import Counter
import re
from urllib.parse import urlsplit

import regex

from weekly_diff.config import Config
from weekly_diff.dedupe import product_names
from weekly_diff.editorial import banned_problems
from weekly_diff.shorten import full_sentence
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


def valid_emoji(value: object, max_codepoints: int) -> bool:
    if not isinstance(value, str) or not regex.fullmatch(r'\X', value):
        return False
    # Each ZWJ component is a short emoji, optionally with a skin tone or selector.
    component = r'(?:\p{Extended_Pictographic}\uFE0F?\p{Emoji_Modifier}?|[\p{Regional_Indicator}]{2}|[0-9#*]\uFE0F?\u20E3)'
    if not regex.fullmatch(component + '(?:\u200D' + component + ')*', value):
        return False
    return all(len(part.replace('\ufe0f', '')) <= max_codepoints
               for part in value.split('\u200d'))


def _copy_problems(copy: dict, cfg: Config, *, chinese: bool) -> list[str]:
    prefix = 'zh.' if chinese else ''
    limits = (('headline', cfg.content.max_headline_chars_zh if chinese else cfg.issue.max_headline_chars),
              ('summary', cfg.content.max_summary_chars_zh if chinese else cfg.content.max_summary_words),
              ('why_it_matters', cfg.content.max_why_chars_zh if chinese else cfg.content.max_why_words),
              ('for_builders', cfg.content.max_builders_chars_zh if chinese else cfg.content.max_builders_words))
    problems = []
    for field, limit in limits:
        value = copy.get(field)
        if field == 'for_builders' and value is None:
            continue
        if not _nonempty(value):
            problems.append(f'{prefix}{field} must be non-empty')
            continue
        characters = chinese or field == 'headline'
        length = len(value) if characters else len(value.split())
        if length > limit:
            unit = 'characters' if characters else 'words'
            problems.append(f'{prefix}{field} exceeds {limit} {unit}')
        problems.extend(banned_problems(value))
        if regex.search(r'\p{Extended_Pictographic}|\p{Regional_Indicator}|\u20e3', value):
            problems.append(f'{prefix}{field} must not contain emoji')
    summary = copy.get('summary')
    if isinstance(summary, str) and not single_sentence(summary.translate(str.maketrans('。！？', '.!?'))):
        problems.append(f'{prefix}summary must be a single sentence')
    return problems


def validate_item(item: Item, source_text: str, cfg: Config) -> list[str]:
    problems = []
    for field in ('key', 'source_name', 'source_url'):
        if not _nonempty(getattr(item, field)):
            problems.append(f'{field} must be non-empty')
    if not valid_emoji(item.emoji, cfg.content.max_emoji_codepoints):
        problems.append('emoji must be one short emoji grapheme')
    problems.extend(_copy_problems(vars(item), cfg, chinese=False))
    fields = {'headline', 'summary', 'why_it_matters', 'for_builders'}
    if not isinstance(item.zh, dict) or set(item.zh) != fields:
        problems.append('zh must contain all four content fields')
    else:
        problems.extend(_copy_problems(item.zh, cfg, chinese=True))
    if not isinstance(item.tag, str) or item.tag not in cfg.tags:
        problems.append('invalid tag')
    if not isinstance(item.section, str) or item.section not in {section.key for section in cfg.issue.sections}:
        problems.append('invalid section')
    try:
        url = urlsplit(item.source_url)
        if url.scheme not in {'http', 'https'} or not url.hostname or re.search(r'\s', item.source_url):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        problems.append('source_url must be an http(s) URL')
    generated = [value for value in (item.headline, item.summary, item.why_it_matters,
                                     item.for_builders) if isinstance(value, str)]
    if isinstance(item.zh, dict):
        generated.extend(value for value in item.zh.values() if isinstance(value, str))
    evidence = source_text + '\n' + item.extra.get('candidate_title', '')
    for value in generated:
        if re.search(r'@(?:everyone|here)\b', value, re.I):
            problems.append('broadcast mention is forbidden')
        problems.extend(number_problems(value, evidence))
    fallbacks = item.extra.get('sentence_fallbacks', {})
    for field, value in fallbacks.items():
        actual = (item.zh or {}).get('summary') if field == 'zh.summary' else item.summary
        if field in {'summary', 'zh.summary'} and actual == value and full_sentence(value):
            problems = [p for p in problems if not p.startswith(field + ' exceeds ')]
    return problems


def validate_issue(issue: Issue, cfg: Config) -> list[str]:
    problems = []
    items = list(issue.items())
    if len(issue.sixty_seconds) != 3 or any(not _nonempty(bullet) or (len(bullet.split()) > cfg.content.max_bullet_words and not full_sentence(bullet))
                                          for bullet in issue.sixty_seconds):
        problems.append('sixty_seconds must contain exactly 3 non-empty bullets within the length target or full-sentence fallback')
    if (len(issue.sixty_seconds_zh) != 3
            or any(not _nonempty(bullet) or (len(bullet) > cfg.content.max_bullet_chars_zh and not full_sentence(bullet))
                   for bullet in issue.sixty_seconds_zh)):
        problems.append('sixty_seconds_zh must contain exactly 3 non-empty, bounded bullets')
    if not cfg.issue.hard_min_items <= len(items) <= cfg.issue.max_items:
        problems.append('item count outside configured bounds')
    products: set[str] = set()
    for item in items:
        names = product_names(item.extra.get('candidate_title', '')) | product_names(item.headline)
        if products & names:
            problems.append('duplicate product name')
        products.update(names)
    for bullet in [*issue.sixty_seconds, *issue.sixty_seconds_zh]:
        problems.extend(banned_problems(bullet))
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
