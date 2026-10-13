from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from collections.abc import Iterator
from typing import Any

import pytest

from weekly_diff import paths
from weekly_diff.config import Config, load_config
from weekly_diff.http import Http

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'collectors'


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    cfg = load_config(FIXTURES.parent / 'config.yaml')
    sources = replace(cfg.sources, backoff_seconds=0, rss=cfg.sources.rss[:1],
                      primary_domains=(*cfg.sources.primary_domains, 'openai.com', 'github.com'),
                      html_index=replace(cfg.sources.html_index, pages=cfg.sources.html_index.pages[:1]),
                      github_releases=replace(cfg.sources.github_releases, repos=cfg.sources.github_releases.repos[:1]),
                      github_trending=replace(cfg.sources.github_trending, queries=cfg.sources.github_trending.queries[:1]),
                      huggingface=replace(cfg.sources.huggingface, orgs=()))
    monkeypatch.setattr(paths, 'STARS', tmp_path / 'data' / 'stars.json')
    monkeypatch.setattr(paths, 'BUILD', tmp_path / 'build')
    return replace(cfg, sources=sources)


@pytest.fixture
def window() -> tuple[datetime, datetime]:
    return datetime(2026, 10, 5, tzinfo=timezone.utc), datetime(2026, 10, 12, tzinfo=timezone.utc)


@pytest.fixture
def http(cfg: Config) -> Iterator[Http]:
    client = Http(cfg)
    yield client
    client.close()


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def data(name: str) -> Any:
    return json.loads(fixture(name))
