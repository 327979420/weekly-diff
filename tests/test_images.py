from dataclasses import replace
from pathlib import Path

import pytest

from weekly_diff.config import load_config
from weekly_diff.images import allowed_image


@pytest.mark.parametrize(('url', 'expected'), [
    ('https://opengraph.githubassets.com/1/org/repo', True),
    ('https://OPENGRAPH.GITHUBASSETS.COM/1/org/repo', True),
    ('https://opengraph.githubassets.com.evil.test/image', False),
    ('https://opengraph.githubassets.com@evil.test/image', False),
    ('https://user@opengraph.githubassets.com/image', False),
    ('https://example.com/image', False), ('javascript:alert(1)', False),
    ('https://[broken', False), (None, False),
])
def test_exact_image_host(url: str | None, expected: bool) -> None:
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    assert allowed_image(url, cfg) is expected


def test_configured_hosts_and_disabled_images() -> None:
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    custom = replace(cfg, site=replace(cfg.site, image_domains_allowlist=('example.com',)))
    assert allowed_image('https://example.com/image', custom)
    assert not allowed_image('https://opengraph.githubassets.com/1/org/repo', custom)
    assert not allowed_image('https://example.com/image', replace(custom, site=replace(custom.site, image_domains_allowlist=())))
