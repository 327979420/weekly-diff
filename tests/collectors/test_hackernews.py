from datetime import datetime, timedelta

import pytest
import responses

from weekly_diff.collectors import hackernews
from weekly_diff.config import Config
from weekly_diff.http import Http
from weekly_diff.text import parse_date
from conftest import data


def test_hn(cfg: Config, http: Http, offline_http: responses.RequestsMock) -> None:
    stories = data('hn.json')
    offline_http.get(cfg.sources.hackernews.api_url, json=stories)
    end = parse_date(stories['hits'][0]['created_at'])
    window = (end - timedelta(days=7), end)
    result = hackernews.collect(cfg, window, http)
    assert len(result) == 1
    assert result[0].signals['hn_points'] == stories['hits'][0]['points']
    assert hackernews.collect(cfg, (end + timedelta(days=1), end + timedelta(days=7)), http) == []


def test_keywords_text_posts_and_points(cfg: Config, http: Http, offline_http: responses.RequestsMock) -> None:
    stories = data('hn-cases.json')
    offline_http.get(cfg.sources.hackernews.api_url, json=stories)
    end = parse_date(stories['hits'][0]['created_at'])
    result = hackernews.collect(cfg, (end - timedelta(days=7), end), http)
    assert len(result) == 1
    assert result[0].url == result[0].extra['hn_url']
    assert result[0].text == 'AI discussion'


def test_failure(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    offline_http.get(cfg.sources.hackernews.api_url, status=500)
    with pytest.raises(Exception):
        hackernews.collect(cfg, window, http)
