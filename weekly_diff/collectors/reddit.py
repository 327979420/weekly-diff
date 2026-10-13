"""Weekly community posts, retaining outward source URLs when available."""
from datetime import datetime, timezone
from urllib.parse import urljoin

from weekly_diff.collectors import in_window, primary, valid_url
from weekly_diff.config import Config
from weekly_diff.http import Http
from weekly_diff.models import Candidate
from weekly_diff.text import html_to_text


def collect(cfg: Config, window: tuple[datetime, datetime], http: Http) -> list[Candidate]:
    settings = cfg.sources.reddit
    if not settings.enabled:
        return []
    result = []
    for sub in settings.subreddits:
        try:
            response = http.get_json(settings.api_url.format(sub=sub),
                                     params={'t': 'week', 'limit': settings.limit}, retry=False)
            posts = response['data']['children']
        except Exception as error:
            http.failure(f'{settings.name} r/{sub}', error)
            continue
        for entry in posts:
            try:
                post = entry['data']
                date = datetime.fromtimestamp(post['created_utc'], timezone.utc)
                if not in_window(date, window) or post['score'] < settings.min_score:
                    continue
                permalink = urljoin(settings.base_url, post['permalink'])
                url = permalink if post.get('is_self') else post.get('url') or permalink
                if not valid_url(url):
                    continue
                # Community commentary is not evidence for claims made by an outward source.
                text = html_to_text(post.get('selftext') or post['title']) if post.get('is_self') else ''
                result.append(Candidate(f"reddit:{post['id']}", post['title'], url,
                                        f'{settings.name} r/{sub}', 'reddit', date, text,
                                        primary(url, cfg), 'quick', {'reddit_score': post['score']},
                                        {'reddit_url': permalink}))
            except Exception as error:
                http.failure(f'{settings.name} r/{sub} post', error)
    return result
