from dataclasses import replace
from pathlib import Path

import pytest
import requests
import responses

from weekly_diff.config import load_config
from weekly_diff.http import Http

FIXTURE = Path(__file__).parent / 'fixtures/collectors/hf.json'


def client() -> Http:
    cfg = load_config()
    return Http(replace(cfg, sources=replace(cfg.sources, backoff_seconds=0)))


def test_headers_auth_and_response_access(monkeypatch: pytest.MonkeyPatch, offline_http: responses.RequestsMock) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token-value')
    http = client()
    offline_http.get('https://api.github.com/test', body=FIXTURE.read_text(), headers={'Link': 'next'})
    assert http.get_json('https://api.github.com/test')
    headers = offline_http.calls[0].request.headers
    assert headers['Authorization'] == 'Bearer test-token-value'
    assert headers['User-Agent'] == http.cfg.sources.user_agent
    assert headers['X-GitHub-Api-Version'] == '2022-11-28'
    assert http.headers['Link'] == 'next'
    offline_http.get('https://example.com/test', body=FIXTURE.read_text())
    assert http.get_bytes('https://example.com/test') == FIXTURE.read_bytes()
    assert http.get_text('https://example.com/test') == FIXTURE.read_text()
    assert 'Authorization' not in offline_http.calls[-1].request.headers
    http.close()


@pytest.mark.parametrize('failure', [429, 500, 503, requests.ConnectionError('offline'), requests.Timeout('timeout')])
def test_two_retries(failure: int | Exception, offline_http: responses.RequestsMock,
                     monkeypatch: pytest.MonkeyPatch) -> None:
    delays = []
    monkeypatch.setattr('weekly_diff.http.time.sleep', delays.append)
    http = Http(load_config())
    kwargs = {'status': failure} if isinstance(failure, int) else {'body': failure}
    for _ in range(2):
        offline_http.get('https://example.com/test', **kwargs)
    offline_http.get('https://example.com/test', body=FIXTURE.read_text())
    assert http.get_json('https://example.com/test')
    assert len(offline_http.calls) == 3
    assert delays == [http.cfg.sources.backoff_seconds, http.cfg.sources.backoff_seconds * 2]


def test_no_retry_404_and_bounded_500(offline_http: responses.RequestsMock) -> None:
    http = client()
    offline_http.get('https://example.com/missing', status=404)
    with pytest.raises(requests.HTTPError):
        http.get_text('https://example.com/missing')
    assert len(offline_http.calls) == 1
    offline_http.get('https://example.com/broken', status=500)
    with pytest.raises(requests.HTTPError):
        http.get_text('https://example.com/broken')
    assert len(offline_http.calls) == 4


def test_timeout_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    http = client()
    def fail(url: str, **kwargs: object) -> None:
        assert kwargs['timeout'] == http.cfg.sources.timeout_seconds
        raise requests.Timeout('offline')
    monkeypatch.setattr(http.session, 'get', fail)
    with pytest.raises(requests.Timeout):
        http.get_text('https://example.com/test')


def test_redirect_does_not_leak_token(monkeypatch: pytest.MonkeyPatch, offline_http: responses.RequestsMock) -> None:
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token-value')
    offline_http.get('https://api.github.com/redirect', status=302, headers={'Location': 'https://example.com/destination'})
    offline_http.get('https://example.com/destination', body=FIXTURE.read_text())
    client().get_text('https://api.github.com/redirect')
    assert 'Authorization' not in offline_http.calls[-1].request.headers
