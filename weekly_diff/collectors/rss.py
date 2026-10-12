"""RSS and Atom feeds fetched through the shared transport."""
from datetime import datetime, timezone
import calendar

import feedparser

from weekly_diff.collectors import in_window, primary, valid_url
from weekly_diff.config import Config
from weekly_diff.http import Http
from weekly_diff.models import Candidate
from weekly_diff.text import html_to_text


def collect(cfg: Config, window: tuple[datetime, datetime], http: Http) -> list[Candidate]:
    result = []
    for source in cfg.sources.rss:
        try:
            feed = feedparser.parse(http.get_bytes(source.url))
            if feed.bozo and not feed.entries:
                raise ValueError('malformed feed')
            for entry in feed.entries:
                stamp = entry.get('published_parsed') or entry.get('updated_parsed')
                date = datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc) if stamp else None
                url = entry.get('link', '')
                if not in_window(date, window) or not valid_url(url):
                    continue
                content = ' '.join(item.get('value', '') for item in entry.get('content', []))
                result.append(Candidate(url, html_to_text(entry.get('title', '')), url,
                                        source.name, 'rss', date,
                                        html_to_text(content or entry.get('summary', '')),
                                        primary(url, cfg), source.section, {}, {}))
        except Exception as error:
            http.failure(source.name, error)
    return result
