"""Collapse each tool's recent releases into one candidate."""
from datetime import datetime

from weekly_diff.collectors import in_window, primary, valid_url
from weekly_diff.config import Config
from weekly_diff.http import Http
from weekly_diff.models import Candidate
from weekly_diff.text import parse_date


def collect(cfg: Config, window: tuple[datetime, datetime], http: Http) -> list[Candidate]:
    result = []
    settings = cfg.sources.github_releases
    for repo in settings.repos:
        try:
            data = http.get_json(f'{cfg.sources.github_api_url}/repos/{repo.repo}/releases',
                                 params={'per_page': settings.per_page})
            releases = [r for r in data if not r['draft']
                        and (settings.include_prereleases or not r['prerelease'])
                        and in_window(parse_date(r.get('published_at')), window)
                        and valid_url(r.get('html_url', ''))]
            releases.sort(key=lambda r: parse_date(r['published_at']), reverse=True)
            if not releases:
                continue
            latest = releases[0]
            tags = [r['tag_name'] for r in releases]
            text = '\n\n'.join(f"{r['tag_name']}\n{r.get('body') or ''}" for r in releases)
            result.append(Candidate(f'release:{repo.repo}:{tags[0]}', f'{repo.name} {tags[0]}',
                                    latest['html_url'], repo.name, 'github_release',
                                    parse_date(latest['published_at']), text[:settings.max_text_chars],
                                    primary(latest['html_url'], cfg), 'tools',
                                    {'release_count': len(releases)}, {'tags': tags}))
        except Exception as error:
            http.failure(repo.name, error)
    return result
