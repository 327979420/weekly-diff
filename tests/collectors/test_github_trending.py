from dataclasses import replace
from datetime import datetime, timedelta
import json
import logging
from urllib.parse import parse_qs, urlsplit

import pytest
import responses

from weekly_diff import paths
from weekly_diff.collectors import github_trending
from weekly_diff.config import Config
from weekly_diff.http import Http
from conftest import data


def search(cfg: Config, mock: responses.RequestsMock, name: str = 'repo-large.json') -> dict:
    payload = data(name)
    mock.get(f'{cfg.sources.github_api_url}/search/repositories', json=payload)
    return payload['items'][0]


def save(snapshot: dict) -> None:
    paths.STARS.parent.mkdir(exist_ok=True)
    paths.STARS.write_text(json.dumps(snapshot))


def test_new_repo(cfg: Config, window: tuple[datetime, datetime], http: Http,
                  offline_http: responses.RequestsMock) -> None:
    payload = data('repo-small.json')
    repo = payload['items'][0]
    repo['created_at'] = window[0].isoformat()
    offline_http.get(f'{cfg.sources.github_api_url}/search/repositories', json=payload)
    item = github_trending.collect(cfg, window, http)[0]
    assert item.signals == {'stars_gained': 150, 'stars_total': 150}
    assert item.extra['gain_method'] == 'new'
    assert 'gain_since' not in item.extra
    assert len(offline_http.calls) == 1
    assert json.loads(paths.STARS.read_text()) == {
        'version': 1, 'repos': {repo['full_name'].lower(): [
            {'at': window[1].isoformat(), 'stars': 150}]}}


@pytest.mark.parametrize('days,expected', [(4, None), (5, 100), (7, 100), (9, 100), (10, None)])
def test_flat_snapshot_compatibility(cfg: Config, window: tuple[datetime, datetime], http: Http,
                                     offline_http: responses.RequestsMock, days: int,
                                     expected: int | None, caplog: pytest.LogCaptureFixture) -> None:
    repo = search(cfg, offline_http)
    snapshots = data('snapshots.json')
    previous = snapshots[repo['full_name'].lower()]
    previous['at'] = (window[1] - timedelta(days=days)).isoformat()
    save(snapshots)
    with caplog.at_level(logging.DEBUG):
        result = github_trending.collect(cfg, window, http)
    if expected is None:
        assert result == []
        assert 'skipped 1 repos' in caplog.text
        assert 'No weekly star baseline' in caplog.text
    else:
        assert result[0].signals['stars_gained'] == expected
        assert result[0].extra['gain_method'] == 'snapshot'
        assert result[0].extra['gain_since'] == previous['at']
    assert not http.errors
    history = json.loads(paths.STARS.read_text())
    assert history['repos'][repo['full_name'].lower()] == [
        previous, {'at': window[1].isoformat(), 'stars': 40100}]
    assert len(offline_http.calls) == 1


@pytest.mark.parametrize('closest_days', [7, 6.5])
def test_closest_snapshot(cfg: Config, window: tuple[datetime, datetime], http: Http,
                          offline_http: responses.RequestsMock, closest_days: float) -> None:
    repo = search(cfg, offline_http)
    entries = [{'at': (window[1] - timedelta(days=days)).isoformat(), 'stars': stars}
               for days, stars in [(9, 38000), (closest_days, 40000), (5, 40050), (1, 40090)]]
    save({'version': 1, 'repos': {repo['full_name'].lower(): entries}})
    item = github_trending.collect(cfg, window, http)[0]
    assert item.signals['stars_gained'] == 100
    assert item.extra['gain_since'] == entries[1]['at']


def test_history_cap_pruning_and_all_search_results(cfg: Config, window: tuple[datetime, datetime],
                                                   http: Http, offline_http: responses.RequestsMock) -> None:
    payload = data('repos.json')
    first, second = payload['items']
    second['archived'] = True
    settings = replace(cfg.sources.github_trending, candidates=1, queries=('first', 'second'))
    cfg = replace(cfg, sources=replace(cfg.sources, github_trending=settings))
    offline_http.get(f'{cfg.sources.github_api_url}/search/repositories', json=payload)
    entries = [{'at': (window[1] - timedelta(days=days)).isoformat(), 'stars': 40000}
               for days in range(10, 0, -1)]
    save({'version': 1, 'repos': {
        first['full_name'].lower(): entries,
        'stale/repo': [{'at': (window[1] - timedelta(days=31)).isoformat(), 'stars': 10}],
        'retained/repo': [{'at': (window[1] - timedelta(days=30)).isoformat(), 'stars': 10}]}})
    assert len(github_trending.collect(cfg, window, http)) == 1
    history = json.loads(paths.STARS.read_text())['repos']
    assert history[first['full_name'].lower()] == entries[-5:] + [
        {'at': window[1].isoformat(), 'stars': first['stargazers_count']}]
    assert history[second['full_name'].lower()] == [
        {'at': window[1].isoformat(), 'stars': second['stargazers_count']}]
    assert 'stale/repo' not in history and 'retained/repo' in history
    assert len(offline_http.calls) == 2
    github_trending.collect(cfg, window, http)
    assert json.loads(paths.STARS.read_text())['repos'] == history


@pytest.mark.parametrize('existing', [False, True])
def test_dry_run(cfg: Config, window: tuple[datetime, datetime], http: Http,
                 offline_http: responses.RequestsMock, existing: bool) -> None:
    search(cfg, offline_http)
    original = json.dumps(data('snapshots.json'))
    if existing:
        save(data('snapshots.json'))
    http.dry_run = True
    result = github_trending.collect(cfg, window, http)
    if existing:
        assert result[0].signals['stars_gained'] == 100
        assert paths.STARS.read_text() == original
    else:
        assert not result and not paths.STARS.exists()


def test_ranking_and_limit_after_gain(cfg: Config, window: tuple[datetime, datetime], http: Http,
                                      offline_http: responses.RequestsMock) -> None:
    payload = data('repos.json')
    first, second = payload['items']
    offline_http.get(f'{cfg.sources.github_api_url}/search/repositories', json=payload)
    save({'version': 1, 'repos': {
        repo['full_name'].lower(): [{'at': window[0].isoformat(),
                                    'stars': repo['stargazers_count'] - gain}]
        for repo, gain in [(first, 100), (second, 200)]}})
    http.dry_run = True
    result = github_trending.collect(cfg, window, http)
    assert [item.signals['stars_gained'] for item in result] == [200, 100]
    cfg = replace(cfg, sources=replace(cfg.sources, github_trending=replace(
        cfg.sources.github_trending, candidates=1)))
    http.dry_run = False
    assert github_trending.collect(cfg, window, http)[0].title == second['full_name']
    history = json.loads(paths.STARS.read_text())['repos']
    assert all(history[repo['full_name'].lower()][-1]['at'] == window[1].isoformat()
               for repo in payload['items'])


def test_failed_search(cfg: Config, window: tuple[datetime, datetime], http: Http,
                       offline_http: responses.RequestsMock) -> None:
    offline_http.get(f'{cfg.sources.github_api_url}/search/repositories', json=data('error.json'), status=500)
    assert github_trending.collect(cfg, window, http) == []
    assert http.errors and not paths.STARS.exists()


def test_filters_and_query_format(cfg: Config, window: tuple[datetime, datetime], http: Http,
                                  offline_http: responses.RequestsMock) -> None:
    repo = data('repo-small.json')['items'][0]
    settings = replace(cfg.sources.github_trending, exclude_repos=(repo['full_name'].upper(),),
                       queries=('created:>{created_since} pushed:>{since}',))
    cfg = replace(cfg, sources=replace(cfg.sources, github_trending=settings))
    search(cfg, offline_http, 'repo-small.json')
    assert github_trending.collect(cfg, window, http) == []
    query = parse_qs(urlsplit(offline_http.calls[0].request.url).query)
    assert query['q'] == ['created:>2026-09-12 pushed:>2026-10-05']
    assert repo['full_name'].lower() in json.loads(paths.STARS.read_text())['repos']


@pytest.mark.parametrize('field', ['fork', 'archived'])
def test_excluded_repo_flags(cfg: Config, window: tuple[datetime, datetime], http: Http,
                             offline_http: responses.RequestsMock, field: str) -> None:
    payload = data('repo-small.json')
    payload['items'][0][field] = True
    offline_http.get(f'{cfg.sources.github_api_url}/search/repositories', json=payload)
    assert github_trending.collect(cfg, window, http) == []
    assert len(offline_http.calls) == 1


def test_prune_without_results(cfg: Config, window: tuple[datetime, datetime], http: Http,
                               offline_http: responses.RequestsMock) -> None:
    payload = data('repos.json')
    payload['items'] = []
    offline_http.get(f'{cfg.sources.github_api_url}/search/repositories', json=payload)
    snapshots = data('snapshots.json')
    for entry in snapshots.values():
        entry['at'] = (window[1] - timedelta(days=31)).isoformat()
    save(snapshots)
    assert github_trending.collect(cfg, window, http) == []
    assert json.loads(paths.STARS.read_text()) == {'version': 1, 'repos': {}}
