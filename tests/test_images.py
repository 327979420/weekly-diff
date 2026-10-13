from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from PIL import Image
import pytest
import requests
import responses
import yaml

from weekly_diff.config import ConfigError, load_config
from weekly_diff.images import cache_images, local_image
from weekly_diff.models import Issue
from weekly_diff.site import render_site

FIX = Path(__file__).parent / 'fixtures'


def sample() -> Issue:
    issue = Issue.from_dict(json.loads((FIX / 'bilingual_issues/2026-42.json').read_text()))
    for item in issue.items():
        item.image_url = None
    next(issue.items()).image_url = 'https://example.com/image.png'
    return issue


def test_download_resize_and_offline_render(tmp_path: Path, offline_http: responses.RequestsMock) -> None:
    cfg = load_config(FIX / 'config.yaml')
    issue = sample()
    item = next(issue.items())
    issue.sixty_seconds_keys = [[item.key]]
    offline_http.get(item.image_url, body=(FIX / 'images/source.png').read_bytes(), content_type='image/png')
    with patch('requests.Session.get', autospec=True, side_effect=requests.Session.get) as get:
        cache_images(issue, cfg, tmp_path / 'images')
        assert get.call_args.kwargs['timeout'] == 10
        assert get.call_args.kwargs['stream'] is True
    assert offline_http.calls[0].request.headers['User-Agent'] == cfg.sources.user_agent
    relative = local_image(item, issue.id)
    cached = tmp_path / 'images' / issue.id / Path(relative).name
    with Image.open(cached) as image:
        assert image.format == 'WEBP' and image.size == (640, 360)
    assert cached.stat().st_size <= cfg.images.target_bytes
    source = tmp_path / 'issues'
    source.mkdir()
    (source / 'issue.json').write_text(json.dumps(issue.to_dict()))
    out = tmp_path / 'site'
    for _ in range(2):
        with patch('requests.Session.request', side_effect=AssertionError('Network forbidden')):
            render_site(cfg, source, out)
        assert (out / relative).read_bytes() == cached.read_bytes()
        for route in ('index.html', 'issues/2026-42/index.html', 'zh/index.html'):
            page = BeautifulSoup((out / route).read_text(), 'html.parser')
            assert len(page.select('img.story-image')) == 1
            thumbnail = page.select_one('.story-image')
            assert thumbnail['src'] == cfg.base_path + '/' + relative
            assert thumbnail['loading'] == 'lazy' and thumbnail['decoding'] == 'async'
            assert thumbnail['width'] == '160' and thumbnail['height'] == '90'
            assert thumbnail['alt'] == (item.zh['headline'] if route.startswith('zh/') else item.headline)
            assert page.select_one('.issue-hero')
        assert (out / 'index.html').stat().st_size + (out / 'assets/style.css').stat().st_size < 50_000
    cached.unlink()
    render_site(cfg, source, out)
    assert not BeautifulSoup((out / 'index.html').read_text(), 'html.parser').select('img')


@pytest.mark.parametrize('failure', ['status', 'timeout', 'mime', 'declared_size', 'stream_size', 'invalid'])
def test_download_failure(tmp_path: Path, offline_http: responses.RequestsMock, failure: str) -> None:
    cfg = load_config(FIX / 'config.yaml')
    cfg = replace(cfg, images=replace(cfg.images, max_download_bytes=1000))
    issue = sample()
    item = next(issue.items())
    item.extra['image_local'] = f'assets/img/{issue.id}/stale.webp'
    kwargs = {'body': (FIX / 'images/source.png').read_bytes(), 'content_type': 'image/png'}
    if failure == 'status':
        kwargs['status'] = 404
    elif failure == 'timeout':
        kwargs['body'] = requests.Timeout('untrusted secret')
    elif failure == 'mime':
        kwargs['content_type'] = 'text/html'
    elif failure == 'declared_size':
        kwargs['headers'] = {'Content-Length': '50000000'}
    elif failure == 'invalid':
        kwargs['body'] = b'not an image'
    offline_http.get(item.image_url, **kwargs)
    cache_images(issue, cfg, tmp_path / 'images')
    assert 'image_local' not in item.extra
    assert not list(tmp_path.rglob('*.webp'))


@pytest.mark.parametrize('path', ['../../escape.webp', 'https://evil.test/img.webp',
                                   'assets/img/2026-41/wrong.webp', 'assets/img/2026-42/../../escape.webp'])
def test_local_path_validation(path: str) -> None:
    issue = sample()
    item = next(issue.items())
    item.extra['image_local'] = path
    assert local_image(item, issue.id) is None


@pytest.mark.parametrize('languages', [[], ['fr'], ['zh', 'zh'], 'zh', [1]])
def test_language_validation(tmp_path: Path, languages: object) -> None:
    raw = yaml.safe_load((FIX / 'config.yaml').read_text())
    raw['discord']['languages'] = languages
    source = tmp_path / 'config.yaml'
    source.write_text(yaml.safe_dump(raw))
    with pytest.raises(ConfigError, match='discord.languages'):
        load_config(source)


def test_language_default(tmp_path: Path) -> None:
    raw = yaml.safe_load((FIX / 'config.yaml').read_text())
    raw['discord'].pop('languages', None)
    source = tmp_path / 'config.yaml'
    source.write_text(yaml.safe_dump(raw))
    assert load_config(source).discord.languages == ('zh',)


def test_one_broken_image_does_not_stop_next(tmp_path: Path, offline_http: responses.RequestsMock) -> None:
    cfg = load_config(FIX / 'config.yaml')
    issue = sample()
    first, second = list(issue.items())[:2]
    second.image_url = 'https://example.com/good.png'
    offline_http.get(first.image_url, body=b'broken', content_type='image/png')
    offline_http.get(second.image_url, body=(FIX / 'images/source.png').read_bytes(), content_type='image/png')
    cache_images(issue, cfg, tmp_path)
    assert 'image_local' not in first.extra
    assert local_image(second, issue.id)


def test_webp_budget(tmp_path: Path, offline_http: responses.RequestsMock) -> None:
    cfg = load_config(FIX / 'config.yaml')
    cfg = replace(cfg, images=replace(cfg.images, target_bytes=100))
    issue = sample()
    item = next(issue.items())
    offline_http.get(item.image_url, body=(FIX / 'images/source.png').read_bytes(), content_type='image/png')
    cache_images(issue, cfg, tmp_path)
    target = next(tmp_path.rglob('*.webp'))
    assert target.stat().st_size <= 100
    with Image.open(target) as image:
        assert image.width < 640
