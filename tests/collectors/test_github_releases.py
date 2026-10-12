from dataclasses import replace
from datetime import datetime, timedelta

import responses

from weekly_diff.collectors import github_releases
from weekly_diff.config import Config
from weekly_diff.http import Http
from conftest import data


def url(cfg: Config) -> str:
    return f'{cfg.sources.github_api_url}/repos/{cfg.sources.github_releases.repos[0].repo}/releases'


def test_collapses(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    releases = data('releases.json')
    offline_http.get(url(cfg), json=releases)
    items = github_releases.collect(cfg, window, http)
    assert len(items) == 1
    item = items[0]
    assert item.signals['release_count'] == 3
    assert item.extra['tags'] == [r['tag_name'] for r in releases]
    assert item.url == releases[0]['html_url']
    assert item.title.endswith(releases[0]['tag_name'])
    assert len(item.text) <= cfg.sources.github_releases.max_text_chars
    assert github_releases.collect(cfg, (window[0] - timedelta(days=30), window[0] - timedelta(days=20)), http) == []


def test_flags(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    offline_http.get(url(cfg), json=data('release-flags.json'))
    assert github_releases.collect(cfg, window, http)[0].signals['release_count'] == 1
    cfg = replace(cfg, sources=replace(cfg.sources, github_releases=replace(cfg.sources.github_releases, include_prereleases=True)))
    assert github_releases.collect(cfg, window, http)[0].signals['release_count'] == 2


def test_failure(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    offline_http.get(url(cfg), json=data('error.json'), status=500)
    assert github_releases.collect(cfg, window, http) == []
    assert http.errors
