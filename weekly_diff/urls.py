"""Canonical identities for public source URLs."""
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def domain_of(url: str) -> str:
    host = (urlsplit(url).hostname or '').lower()
    return host.removeprefix('www.')


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    host = domain_of(url)
    if parts.scheme.lower() not in {'http', 'https'} or not host:
        raise ValueError('Expected an HTTP or HTTPS source URL')
    if ':' in host:
        host = f'[{host}]'
    if parts.port and parts.port not in {80, 443}:
        host = f'{host}:{parts.port}'
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith('utm_')
             and k.lower() not in {'ref', 'source', 'fbclid', 'gclid'}]
    return urlunsplit(('https', host, parts.path.rstrip('/') or '/',
                       urlencode(sorted(query)), ''))


def is_primary(url: str, primary_domains: Iterable[str]) -> bool:
    host = domain_of(url)
    return any(host == domain.lower() or host.endswith('.' + domain.lower())
               for domain in primary_domains)
