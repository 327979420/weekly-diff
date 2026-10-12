from datetime import datetime

import pytest

from weekly_diff.collectors import in_window, primary, valid_url
from weekly_diff.config import Config


@pytest.mark.parametrize('url,expected', [('https://openai.com/news', True),
                                          ('https://blog.openai.com/news', True),
                                          ('https://notopenai.com', False),
                                          ('https://openai.com.evil.example', False)])
def test_primary_domains(cfg: Config, url: str, expected: bool) -> None:
    assert primary(url, cfg) is expected


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'ftp://example.com', '/relative', 'https://[invalid'])
def test_non_web_links(url: str) -> None:
    assert not valid_url(url)


def test_window_boundaries(window: tuple[datetime, datetime]) -> None:
    assert in_window(window[0], window)
    assert in_window(window[1], window)
    assert not in_window(None, window)
