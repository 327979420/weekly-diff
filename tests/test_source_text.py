from dataclasses import replace
import json
from pathlib import Path

import pytest
import requests
import responses

from weekly_diff.config import load_config
from weekly_diff.http import Http
from weekly_diff.models import Candidate
from weekly_diff.source_text import fetch_source_text
from weekly_diff.text import extract_main_text

FIX = Path(__file__).parent / 'fixtures'
CANDIDATE = Candidate.from_dict(json.loads((FIX / 'summarise/candidates.json').read_text())[0])
SOURCE = (FIX / 'summarise/source.md').read_text()


def test_release_no_network(offline_http: responses.RequestsMock) -> None:
    http = Http(load_config(Path(__file__).parent / 'fixtures/config.yaml'))
    assert fetch_source_text(replace(CANDIDATE, source_type='github_release'), http, 12000) == SOURCE.strip()
    assert not offline_http.calls


def test_github_readme(offline_http: responses.RequestsMock) -> None:
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    candidate = replace(CANDIDATE, source_type='github_trending', url='https://github.com/owner/repo')
    offline_http.get(f'{cfg.sources.github_api_url}/repos/owner/repo/readme', body=SOURCE)
    text = fetch_source_text(candidate, Http(cfg), 12000)
    assert text == (candidate.text + '\n\n' + SOURCE).strip()
    headers = offline_http.calls[0].request.headers
    assert headers['Accept'] == 'application/vnd.github.raw'
    assert headers['User-Agent'] == cfg.sources.user_agent


def test_huggingface_card(offline_http: responses.RequestsMock) -> None:
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    candidate = replace(CANDIDATE, source_type='huggingface', url='https://huggingface.co/owner/model')
    offline_http.get(f'{cfg.sources.huggingface.base_url}/owner/model/raw/main/README.md',
                     body=(FIX / 'summarise/card.md').read_text())
    assert fetch_source_text(candidate, Http(cfg), 12000) == SOURCE.strip()


def test_article_and_truncation(offline_http: responses.RequestsMock) -> None:
    html = (FIX / 'collectors/article.html').read_text()
    offline_http.get(CANDIDATE.url, body=html)
    assert fetch_source_text(CANDIDATE, Http(load_config(Path(__file__).parent / 'fixtures/config.yaml')), 12000) == extract_main_text(html)[:12000]
    release = replace(CANDIDATE, source_type='github_release')
    first = SOURCE.split('\n\n')[0]
    assert fetch_source_text(release, Http(load_config(Path(__file__).parent / 'fixtures/config.yaml')), len(first) + 20) == first
    assert fetch_source_text(release, Http(load_config(Path(__file__).parent / 'fixtures/config.yaml')), 0) == ''
    assert len(fetch_source_text(replace(release, text='unbroken'), Http(load_config(Path(__file__).parent / 'fixtures/config.yaml')), 4)) == 4


@pytest.mark.parametrize('body', ['', requests.Timeout('untrusted exception')])
def test_fallback(offline_http: responses.RequestsMock, body: str | Exception) -> None:
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    cfg = replace(cfg, sources=replace(cfg.sources, retries=0))
    offline_http.get(CANDIDATE.url, body=body)
    assert fetch_source_text(CANDIDATE, Http(cfg), 12000) == SOURCE.strip()
    assert fetch_source_text(replace(CANDIDATE, text=''), Http(cfg), 12000) == ''


@pytest.mark.parametrize('kind', ['github_trending', 'huggingface'])
def test_missing_readme_is_unusable(kind: str) -> None:
    assert fetch_source_text(replace(CANDIDATE, source_type=kind), Http(load_config(Path(__file__).parent / 'fixtures/config.yaml')), 12000) == ''


@pytest.mark.parametrize('case', json.loads((FIX / 'summarise/images.json').read_text()))
def test_page_image_uses_existing_fetch(case: dict, offline_http: responses.RequestsMock) -> None:
    candidate = replace(CANDIDATE, url='https://example.com/news/article', extra={'image_url': 'untrusted'})
    offline_http.get(candidate.url, body=case['html'])
    assert fetch_source_text(candidate, Http(load_config(Path(__file__).parent / 'fixtures/config.yaml')), 12000) == SOURCE.strip()
    assert candidate.extra['image_url'] == case['expected']
    assert len(offline_http.calls) == 1


@pytest.mark.parametrize('kind', ['github_release', 'github_trending'])
def test_github_images(kind: str, offline_http: responses.RequestsMock) -> None:
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    url = 'https://github.com/owner/repo' + ('/releases/tag/v2.1' if kind == 'github_release' else '')
    candidate = replace(CANDIDATE, source_type=kind, url=url, extra={})
    if kind == 'github_trending':
        offline_http.get(f'{cfg.sources.github_api_url}/repos/owner/repo/readme', body=SOURCE)
    fetch_source_text(candidate, Http(cfg), 12000)
    assert candidate.extra['image_url'] == f'{cfg.sources.github_image_url}/owner/repo'
    assert len(offline_http.calls) == (1 if kind == 'github_trending' else 0)


def test_huggingface_has_no_image(offline_http: responses.RequestsMock) -> None:
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    candidate = replace(CANDIDATE, source_type='huggingface', url='https://huggingface.co/owner/model',
                        extra={'image_url': 'https://example.com/untrusted.png'})
    offline_http.get(f'{cfg.sources.huggingface.base_url}/owner/model/raw/main/README.md',
                     body=(FIX / 'summarise/card.md').read_text())
    fetch_source_text(candidate, Http(cfg), 12000)
    assert candidate.extra['image_url'] is None
