import pytest

from weekly_diff.urls import canonical_url, domain_of, is_primary


@pytest.mark.parametrize(('url', 'expected'), [
    ('http://WWW.Example.com/a/?z=2&utm_source=x&ref=r&a=1#part', 'https://example.com/a?a=1&z=2'),
    ('https://example.com?fbclid=x&gclid=y&source=x', 'https://example.com/'),
    ('http://example.com:80/', 'https://example.com/'),
    ('https://example.com:8443/a///?b=&a=2&a=1&UTM_MEDIUM=x', 'https://example.com:8443/a?a=1&a=2&b='),
])
def test_canonical(url: str, expected: str) -> None:
    assert canonical_url(url) == expected
    assert canonical_url(expected) == expected


def test_domains() -> None:
    assert domain_of('https://WWW.OpenAI.com/x') == 'openai.com'
    assert is_primary('https://blog.openai.com/x', ['openai.com'])
    assert not is_primary('https://fakeopenai.com/x', ['openai.com'])
    assert not is_primary('https://openai.com.evil.test/x', ['openai.com'])
    with pytest.raises(ValueError):
        canonical_url('javascript:alert(1)')
