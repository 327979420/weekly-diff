from argparse import Namespace
from datetime import datetime
import json
from types import SimpleNamespace

import pytest
import responses

from weekly_diff import collect, paths, pipeline
from weekly_diff.collectors import hackernews, rss
from weekly_diff.config import Config
from weekly_diff.http import Http
from weekly_diff.models import Candidate
from conftest import fixture


def test_failure_isolation_report_and_roundtrip(cfg: Config, window: tuple[datetime, datetime],
                                               offline_http: responses.RequestsMock,
                                               monkeypatch: pytest.MonkeyPatch,
                                               caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(collect, 'COLLECTORS', (hackernews, rss))
    monkeypatch.setenv('GITHUB_TOKEN', 'test-secret-value')
    def fail(cfg: Config, window: tuple[datetime, datetime], http: Http) -> list[Candidate]:
        raise ValueError('test-secret-value')
    monkeypatch.setattr(hackernews, 'collect', fail)
    offline_http.get(cfg.sources.rss[0].url, body=fixture('rss.xml'))
    result = collect.run_collect(cfg, window[1], True)
    assert result
    encoded = json.loads((paths.BUILD / 'candidates.json').read_text())
    assert [Candidate.from_dict(item) for item in encoded] == result
    report_text = (paths.BUILD / 'collect-report.json').read_text()
    report = json.loads(report_text)
    assert report['hackernews']['count'] == 0
    assert report['hackernews']['error'] == 'source failed: hackernews: ***'
    assert report['rss']['count'] == len(result) and report['rss']['error'] is None
    assert all(entry['duration'] >= 0 for entry in report.values())
    assert 'test-secret-value' not in report_text + caplog.text
    assert not paths.STARS.exists()


def test_all_sources_fail_gracefully(cfg: Config, window: tuple[datetime, datetime],
                                     offline_http: responses.RequestsMock) -> None:
    # Unregistered requests are blocked by responses, including retries.
    assert collect.run_collect(cfg, window[1], True) == []
    report = json.loads((paths.BUILD / 'collect-report.json').read_text())
    assert len(report) == 7
    assert report['reddit']['count'] == 0 and report['reddit']['error'] is None
    assert all(entry['error'] for name, entry in report.items() if name != 'reddit')


def test_cli_summary_and_dry_run(cfg: Config, monkeypatch: pytest.MonkeyPatch,
                                capsys: pytest.CaptureFixture[str]) -> None:
    def fake(cfg: Config, window: tuple[datetime, datetime], http: Http) -> list[Candidate]:
        assert http.dry_run
        return []
    monkeypatch.setattr(collect, 'COLLECTORS', (SimpleNamespace(__name__='test.source', collect=fake),))
    pipeline.collect(cfg, Namespace(dry_run=True))
    assert capsys.readouterr().out.startswith('source: 0 candidates in ')
