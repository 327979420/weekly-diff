"""Independent source collectors and shared candidate checks."""
from datetime import datetime
from urllib.parse import urlsplit

from weekly_diff.config import Config


def valid_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return parts.scheme in {'http', 'https'} and bool(parts.hostname)
    except ValueError:
        return False


def primary(url: str, cfg: Config) -> bool:
    host = (urlsplit(url).hostname or '').lower()
    return any(host == domain.lower() or host.endswith('.' + domain.lower())
               for domain in cfg.sources.primary_domains)


def in_window(date: datetime | None, window: tuple[datetime, datetime]) -> bool:
    return date is not None and window[0] <= date <= window[1]
