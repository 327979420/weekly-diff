"""Bounded, configured HTTP transport shared by all collectors."""
import logging
import os
import time
from typing import Any, Mapping
from urllib.parse import urlsplit

import requests

from weekly_diff.config import Config
from weekly_diff.log import redact


class Http:
    def __init__(self, cfg: Config, *, dry_run: bool = False) -> None:
        self.cfg = cfg
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers['User-Agent'] = cfg.sources.user_agent
        self.headers: Mapping[str, str] = {}
        self.errors: list[str] = []

    def failure(self, name: str, error: Exception) -> None:
        message = redact(f"source failed: {name}: {error}")
        self.errors.append(message)
        logging.getLogger(__name__).warning('%s', message)

    def get(self, url: str, *, params: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None, retry: bool = True) -> requests.Response:
        request_headers = dict(headers or {})
        if urlsplit(url).hostname == 'api.github.com':
            request_headers['X-GitHub-Api-Version'] = self.cfg.sources.github_api_version
            if token := os.environ.get('GITHUB_TOKEN'):
                request_headers['Authorization'] = f'Bearer {token}'
        self.headers = {}
        retries = self.cfg.sources.retries if retry else 0
        for attempt in range(retries + 1):
            try:
                response = self.session.get(url, params=params, headers=request_headers,
                                            timeout=self.cfg.sources.timeout_seconds)
                self.headers = response.headers
                should_retry = response.status_code == 429 or 500 <= response.status_code < 600
                if not should_retry or attempt == retries:
                    response.raise_for_status()
                    return response
                response.close()
            except (requests.ConnectionError, requests.Timeout):
                if attempt == retries:
                    raise
            time.sleep(self.cfg.sources.backoff_seconds * 2 ** attempt)
        raise RuntimeError('HTTP retry budget must be nonnegative')

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.get(url, **kwargs).json()

    def get_text(self, url: str, **kwargs: Any) -> str:
        response = self.get(url, **kwargs)
        if not response.encoding or response.encoding.lower() == 'iso-8859-1':
            response.encoding = response.apparent_encoding
        return response.text

    def get_bytes(self, url: str, **kwargs: Any) -> bytes:
        return self.get(url, **kwargs).content

    def close(self) -> None:
        self.session.close()
