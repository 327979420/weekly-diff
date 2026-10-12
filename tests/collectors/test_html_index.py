from dataclasses import replace
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import responses

from weekly_diff.collectors import html_index
from weekly_diff.config import Config
from weekly_diff.http import Http
from conftest import fixture


def register(cfg: Config, mock: responses.RequestsMock, status: int = 200) -> None:
    page = cfg.sources.html_index.pages[0]
    mock.get(page.url, body=fixture('index.html'))
    links = BeautifulSoup(fixture('index.html'), 'html.parser').select('a[href]')
    for link in links:
        mock.get(urljoin(page.url, link['href']), body=fixture('article.html'), status=status)


def test_index(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    register(cfg, offline_http)
    result = html_index.collect(cfg, window, http)
    assert result and all(item.text and item.title and item.primary for item in result)
    assert len({item.url for item in result}) == len(result)
    assert html_index.collect(cfg, (window[0] - timedelta(days=30), window[0] - timedelta(days=20)), http) == []


def test_cap(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    register(cfg, offline_http)
    cfg = replace(cfg, sources=replace(cfg.sources, html_index=replace(cfg.sources.html_index, max_articles_per_index=1)))
    assert len(html_index.collect(cfg, window, http)) == 1
    assert len(offline_http.calls) == 2


def test_failures(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    register(cfg, offline_http, status=500)
    assert html_index.collect(cfg, window, http) == []
    assert http.errors


def test_missing_date(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    page = cfg.sources.html_index.pages[0]
    offline_http.get(page.url, body=fixture('index.html'))
    for link in BeautifulSoup(fixture('index.html'), 'html.parser').select('a[href]'):
        offline_http.get(urljoin(page.url, link['href']), body=fixture('index.html'))
    assert html_index.collect(cfg, window, http) == []
