from dataclasses import replace
from datetime import datetime, timedelta

import responses

from weekly_diff.collectors import rss
from weekly_diff.config import Config
from weekly_diff.http import Http
from conftest import fixture


def test_feed(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    offline_http.get(cfg.sources.rss[0].url, body=fixture('rss.xml'))
    result = rss.collect(cfg, window, http)
    assert result and all(item.primary and item.section_hint == 'models' for item in result)
    assert all(item.key == item.url and '<p>' not in item.text for item in result)
    assert rss.collect(cfg, (window[0] - timedelta(days=500), window[0] - timedelta(days=490)), http) == []


def test_failed_feed_does_not_stop_next(cfg: Config, window: tuple[datetime, datetime], http: Http,
                                      offline_http: responses.RequestsMock) -> None:
    source = cfg.sources.rss[0]
    bad = replace(source, url='https://example.com/broken')
    cfg = replace(cfg, sources=replace(cfg.sources, rss=(bad, source)))
    offline_http.get(bad.url, status=500)
    offline_http.get(source.url, body=fixture('rss.xml'))
    assert rss.collect(cfg, window, http)
    assert len(http.errors) == 1


def test_malformed(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    offline_http.get(cfg.sources.rss[0].url, body=fixture('malformed.txt'))
    assert rss.collect(cfg, window, http) == []
    assert http.errors


def test_atom_updated_and_content(cfg: Config, window: tuple[datetime, datetime], http: Http,
                                  offline_http: responses.RequestsMock) -> None:
    offline_http.get(cfg.sources.rss[0].url, body=fixture('atom.xml'))
    items = rss.collect(cfg, window, http)
    assert len(items) == 3
    assert all(item.text != 'Fallback summary' and '<p>' not in item.text for item in items)
