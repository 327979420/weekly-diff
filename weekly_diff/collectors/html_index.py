"""Dated articles linked from configured news indexes."""
from datetime import datetime
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from weekly_diff.collectors import in_window, primary, valid_url
from weekly_diff.config import Config
from weekly_diff.http import Http
from weekly_diff.models import Candidate
from weekly_diff.text import extract_main_text, extract_published_at, extract_title


def collect(cfg: Config, window: tuple[datetime, datetime], http: Http) -> list[Candidate]:
    result = []
    settings = cfg.sources.html_index
    for page in settings.pages:
        try:
            soup = BeautifulSoup(http.get_text(page.url), 'html.parser')
            pattern = re.compile(page.link_pattern)
            links = dict.fromkeys(urljoin(page.url, a['href']) for a in soup.select('a[href]'))
            links = [url for url in links if valid_url(url) and pattern.search(url)]
        except Exception as error:
            http.failure(page.name, error)
            continue
        for url in links[:settings.max_articles_per_index]:
            try:
                html = http.get_text(url)
                date = extract_published_at(html)
                if in_window(date, window):
                    result.append(Candidate(url, extract_title(html), url, page.name,
                                            'html_index', date, extract_main_text(html),
                                            primary(url, cfg), page.section, {}, {}))
            except Exception as error:
                http.failure(page.name, error)
    return result
