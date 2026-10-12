from dataclasses import replace
from datetime import datetime, timedelta

import responses
from responses.matchers import query_param_matcher

from weekly_diff.collectors import huggingface
from weekly_diff.config import Config
from weekly_diff.http import Http
from conftest import data


def test_trending(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    offline_http.get(cfg.sources.huggingface.api_url, json=data('hf.json'))
    result = huggingface.collect(cfg, window, http)
    assert len(result) == 2
    assert all(item.published_at and item.primary and 'trending_score' in item.signals for item in result)
    assert 'full=true' in offline_http.calls[0].request.url
    assert huggingface.collect(cfg, (window[0] + timedelta(days=90), window[1] + timedelta(days=90)), http) == []


def test_org_window_and_failure_isolation(cfg: Config, window: tuple[datetime, datetime], http: Http,
                                          offline_http: responses.RequestsMock) -> None:
    cfg = replace(cfg, sources=replace(cfg.sources, huggingface=replace(cfg.sources.huggingface, orgs=('google',))))
    settings = cfg.sources.huggingface
    offline_http.get(settings.api_url, status=500, match=[query_param_matcher({
        'sort':'trendingScore','direction':'-1','limit':str(settings.trending_limit),'full':'true'})])
    offline_http.get(settings.api_url, json=data('hf-org.json'), match=[query_param_matcher({
        'author':'google','sort':'createdAt','direction':'-1','limit':str(settings.org_limit),'full':'true'})])
    result = huggingface.collect(cfg, window, http)
    assert len(result) == 1 and http.errors


def test_malformed(cfg: Config, window: tuple[datetime, datetime], http: Http, offline_http: responses.RequestsMock) -> None:
    offline_http.get(cfg.sources.huggingface.api_url, json=data('error.json'))
    assert huggingface.collect(cfg, window, http) == []
    assert http.errors


def test_repacks_are_dropped_and_official_formats_kept(cfg: Config, window: tuple[datetime, datetime],
                                                      http: Http, offline_http: responses.RequestsMock) -> None:
    cases = data('hf-repack-cases.json')
    settings = replace(cfg.sources.huggingface, orgs=('google', 'unsloth'))
    cfg = replace(cfg, sources=replace(cfg.sources, huggingface=settings))
    offline_http.get(settings.api_url, json=[case['model'] for case in cases])
    result = huggingface.collect(cfg, window, http)
    assert {item.title for item in result} == {case['model']['id'] for case in cases if case['keep']}
    assert not http.errors


def test_orphan_repack_does_not_create_original(cfg: Config, window: tuple[datetime, datetime],
                                               http: Http, offline_http: responses.RequestsMock) -> None:
    offline_http.get(cfg.sources.huggingface.api_url, json=[data('hf-repack-cases.json')[-1]['model']])
    assert huggingface.collect(cfg, window, http) == []
    assert not http.errors
