"""Shared, exact-host image policy for the website and Discord."""
from urllib.parse import urlsplit

from weekly_diff.config import Config


def allowed_image(url: str | None, cfg: Config) -> bool:
    if not url:
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme in {'http', 'https'} and not parts.username
                and parts.hostname in {host.lower() for host in cfg.site.image_domains_allowlist})
    except ValueError:
        return False
