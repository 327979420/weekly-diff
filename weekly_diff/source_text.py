"""Fetch the evidence used to write an item."""
import logging
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from weekly_diff.http import Http
from weekly_diff.models import Candidate
from weekly_diff.text import extract_main_text


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if max_chars <= 0:
        return ''
    if len(text) <= max_chars:
        return text
    prefix = text[:max_chars]
    boundaries = list(re.finditer(r'\n\s*\n', prefix))
    return prefix[:boundaries[-1].start()].rstrip() if boundaries else prefix.rstrip()


def _page_image(html: str, url: str) -> str | None:
    soup = BeautifulSoup(html, 'html.parser')
    for kind in ('og:image', 'twitter:image'):
        for meta in soup.find_all('meta'):
            if meta.get('property') != kind and meta.get('name') != kind:
                continue
            content = meta.get('content')
            if not isinstance(content, str) or not content.strip():
                continue
            try:
                image = urljoin(url, content.strip())
                parsed = urlsplit(image)
                if parsed.scheme in {'http', 'https'} and parsed.hostname and not re.search(r'\s', image):
                    return image
            except ValueError:
                continue
    return None


def fetch_source_text(candidate: Candidate, http: Http, max_chars: int) -> str:
    text = ''
    # Reset any collected metadata: only this fetch supplies the trusted image.
    candidate.extra['image_url'] = None
    try:
        parsed = urlsplit(candidate.url)
        parts = parsed.path.strip('/').split('/')
        if parsed.hostname == 'github.com' and len(parts) >= 2:
            repo = '/'.join(parts[:2])
            candidate.extra['image_url'] = f'{http.cfg.sources.github_image_url}/{repo}'

        if candidate.source_type == 'github_release':
            text = candidate.text
        elif candidate.source_type == 'github_trending':
            repo = urlsplit(candidate.url).path.strip('/')
            readme = http.get_text(f'{http.cfg.sources.github_api_url}/repos/{repo}/readme',
                                   headers={'Accept': 'application/vnd.github.raw'})
            text = '\n\n'.join(part for part in (candidate.text, readme) if part.strip())
        elif candidate.source_type == 'huggingface':
            model = urlsplit(candidate.url).path.strip('/')
            text = http.get_text(f'{http.cfg.sources.huggingface.base_url}/{model}/raw/main/README.md')
            text = re.sub(r'\A\ufeff?---[^\S\n]*\r?\n.*?\r?\n(?:---|\.\.\.)[^\S\n]*(?:\r?\n|$)',
                          '', text, count=1, flags=re.S)
        else:
            html = http.get_text(candidate.url)
            if candidate.extra['image_url'] is None:
                candidate.extra['image_url'] = _page_image(html, candidate.url)
            text = extract_main_text(html)
            if len(text.strip()) < 200:
                text = candidate.text
    except Exception:
        # Do not log exception text, which can contain credentials or response bodies.
        logging.getLogger(__name__).warning('Source text fetch failed (%s)', candidate.source_type)
        if candidate.source_type not in {'huggingface', 'github_trending'}:
            text = candidate.text
    return _truncate(text, max_chars)
