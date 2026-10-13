from dataclasses import replace
from datetime import datetime

import pytest
import responses
from responses.matchers import query_param_matcher

from weekly_diff.collectors import reddit
from weekly_diff.config import Config
from weekly_diff.http import Http
from conftest import data


def enabled(cfg: Config, subs: tuple[str, ...] = ('vibecoding',)) -> Config:
    return replace(cfg, sources=replace(cfg.sources, reddit=replace(
        cfg.sources.reddit, enabled=True, subreddits=subs)))


def test_posts(cfg: Config, window: tuple[datetime, datetime], http: Http,
               offline_http: responses.RequestsMock) -> None:
    cfg = enabled(cfg)
    settings = cfg.sources.reddit
    offline_http.get(settings.api_url.format(sub='vibecoding'), json=data('reddit.json'),
                     match=[query_param_matcher({'t': 'week', 'limit': str(settings.limit)})])
    items = reddit.collect(cfg, window, http)
    assert [i.key for i in items] == ['reddit:external', 'reddit:self']
    assert items[0].url == 'https://github.com/example/tool' and items[0].primary
    assert items[0].text == ''
    assert items[1].url == settings.base_url + '/r/vibecoding/comments/self/app/'
    assert items[1].text == 'I used a starter template.'
    assert items[1].signals == {'reddit_score': 300}
    assert offline_http.calls[0].request.headers['User-Agent'] == cfg.sources.user_agent


@pytest.mark.parametrize('status', [403, 429])
def test_blocked_sub_skips_and_continues(cfg: Config, window: tuple[datetime, datetime],
                                       http: Http, offline_http: responses.RequestsMock,
                                       status: int) -> None:
    cfg = enabled(cfg, ('blocked', 'vibecoding'))
    offline_http.get(cfg.sources.reddit.api_url.format(sub='blocked'), status=status)
    offline_http.get(cfg.sources.reddit.api_url.format(sub='vibecoding'), json=data('reddit.json'))
    assert len(reddit.collect(cfg, window, http)) == 2
    assert http.errors and str(status) in http.errors[0]
    assert len(offline_http.calls) == 2


def test_disabled(cfg: Config, window: tuple[datetime, datetime], http: Http,
                  offline_http: responses.RequestsMock) -> None:
    assert reddit.collect(cfg, window, http) == []
    assert not offline_http.calls
