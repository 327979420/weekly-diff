"""Keyword-filtered Hacker News stories with source links."""
from datetime import datetime
import re

from weekly_diff.collectors import in_window, primary, valid_url
from weekly_diff.config import Config
from weekly_diff.http import Http
from weekly_diff.models import Candidate
from weekly_diff.text import html_to_text, parse_date


def collect(cfg: Config, window: tuple[datetime, datetime], http: Http) -> list[Candidate]:
    settings = cfg.sources.hackernews
    pattern = re.compile(r'\b(?:' + '|'.join(map(re.escape, settings.keywords)) + r')\b', re.I)
    result = []
    data = http.get_json(settings.api_url, params={
        'tags': 'story', 'numericFilters': f'created_at_i>{int(window[0].timestamp())},points>={settings.min_points}',
        'hitsPerPage': settings.hits_per_page})
    for story in data['hits']:
        date = parse_date(story.get('created_at'))
        title = story.get('title') or ''
        if (not in_window(date, window) or (story.get('points') or 0) < settings.min_points
                or not settings.keywords or not pattern.search(title)):
            continue
        hn_url = f"{settings.item_url}?id={story['objectID']}"
        url = story.get('url') or hn_url
        if valid_url(url):
            result.append(Candidate(url, title, url, settings.name, 'hackernews', date,
                                    html_to_text(story.get('story_text') or title), primary(url, cfg),
                                    'quick', {'hn_points': story['points'],
                                              'hn_comments': story.get('num_comments') or 0},
                                    {'hn_url': hn_url}))
    return result
