"""Plain-text and publication metadata extraction for fetched sources."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
from typing import Any

from bs4 import BeautifulSoup


def parse_date(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        try:
            date = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            return None
    return date.replace(tzinfo=date.tzinfo or timezone.utc).astimezone(timezone.utc)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    for element in soup.select('script,style'):
        element.decompose()
    return ' '.join(soup.get_text(' ', strip=True).split())


def extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    for element in soup.select('script,style,nav,header,footer,aside,form'):
        element.decompose()
    main = soup.find('article') or soup.find('main') or soup.find('body') or soup
    return ' '.join(main.get_text(' ', strip=True).split())


def _dates(value: Any) -> list[str]:
    if isinstance(value, list):
        return [date for item in value for date in _dates(item)]
    if isinstance(value, dict):
        dates = [value['datePublished']] if isinstance(value.get('datePublished'), str) else []
        return dates + [date for item in value.values() if isinstance(item, (dict, list))
                        for date in _dates(item)]
    return []


def extract_published_at(html: str) -> datetime | None:
    soup = BeautifulSoup(html, 'html.parser')
    meta = soup.find('meta', property='article:published_time')
    if meta and (date := parse_date(meta.get('content'))):
        return date
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            values = _dates(json.loads(script.get_text()))
        except (ValueError, TypeError):
            continue
        for value in values:
            if date := parse_date(value):
                return date
    element = soup.find('time', datetime=True)
    return parse_date(element.get('datetime')) if element else None


def extract_title(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    meta = soup.find('meta', property='og:title')
    if meta and meta.get('content'):
        return ' '.join(meta['content'].split())
    return ' '.join(soup.title.get_text(' ', strip=True).split()) if soup.title else ''
