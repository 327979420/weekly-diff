"""Discord payloads and explicitly routed webhook delivery."""
import json
import logging
import math
import re
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, urlsplit

import requests

from weekly_diff.config import Config
from weekly_diff.http import Http
from weekly_diff.log import redact
from weekly_diff.models import Issue

# Discord protocol limits, independent of editorial configuration.
TITLE_LIMIT = 256
DESCRIPTION_LIMIT = 4096
FIELD_VALUE_LIMIT = 1024
TOTAL_LIMIT = 6000
FIELD_LIMIT = 25
RATE_LIMIT_RETRIES = 2
PREVIEW_FOOTER = 'Preview — not posted publicly'
DISABLED_NOTICE = 'publish_enabled is false — this was not posted publicly.'
WEBHOOK = re.compile(r'https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+')


class DiscordError(RuntimeError):
    """A delivery failure whose message never includes a webhook or response body."""


def _length(text: str) -> int:
    # Counting UTF-16 units also keeps astral emoji within Discord's limits.
    return len(text.encode('utf-16-le')) // 2


def _truncate(text: str, limit: int) -> str:
    if _length(text) <= limit:
        return text
    prefix = text.encode('utf-16-le')[:max(0, limit - 1) * 2].decode('utf-16-le', errors='ignore')
    # Do not leave a dangling Markdown escape before the ellipsis.
    if (len(prefix) - len(prefix.rstrip('\\'))) % 2:
        prefix = prefix[:-1]
    return prefix + '…'


def _escape(text: str) -> str:
    text = text.replace('@', '@\u200b')
    return re.sub(r'([\\*_~`|>\[\]])', r'\\\1', text)


def _link_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        valid = parsed.scheme in {'http', 'https'} and bool(parsed.hostname) and not parsed.username
    except ValueError:
        valid = False
    if not valid:
        raise DiscordError('Invalid link URL')
    # Encode Markdown delimiters without changing existing URL escapes.
    return quote(url, safe=":/?#!$&'*+,;=%-._~")


def _fit(texts: list[str], budget: int) -> list[str]:
    """Shorten the longest text first, retaining at least an ellipsis per part."""
    result = list(texts)
    if budget < len(result):
        raise DiscordError('Links exceed Discord payload limits')
    excess = sum(map(_length, result)) - budget
    while excess > 0:
        index = max(range(len(result)), key=lambda i: _length(result[i]))
        before = _length(result[index])
        result[index] = _truncate(result[index], max(1, before - excess))
        excess -= before - _length(result[index])
    return result


def _description(bullets: list[str], suffix: str, notice: str, heading: str) -> str:
    first = f'{notice}\n\n' if notice else ''
    return first + f'**{heading}**\n' + '\n'.join(f'• {b}' for b in bullets) + suffix


def _payload(issue: Issue, cfg: Config, preview: bool, run_url: str | None,
             notice: str = '', language: str = 'en') -> dict[str, Any]:
    chinese = language == 'zh'
    page = _link_url(f'{cfg.site.base_url}/zh/issues/{issue.id}/' if chinese else cfg.issue_url(issue.id))
    heading = '60 秒速览' if chinese else 'This week in 60 seconds'
    read = '阅读全文 →' if chinese else 'Read the full issue →'
    source = '原文' if chinese else 'Source'
    why = '对你有什么用' if chinese else "Why you'd care"
    builders = '怎么上手' if chinese else 'How to try it'
    suffix = f'\n\n[{read}]({page})'
    if preview and run_url:
        suffix = f'\n\n[View workflow run]({_link_url(run_url)})' + suffix
    bullets = [_escape(issue.sixty_seconds_zh[i] if chinese and i < len(issue.sixty_seconds_zh)
                       and issue.sixty_seconds_zh[i] else bullet)
               for i, bullet in enumerate(issue.sixty_seconds[:3])]
    fixed_description = _length(_description([''] * len(bullets), suffix, notice, heading))
    bullets = _fit(bullets, DESCRIPTION_LIMIT - fixed_description)
    items = {item.key: item for item in issue.items()}
    if any(key not in items for key in issue.top[:FIELD_LIMIT]):
        raise DiscordError('Issue top references a missing item')
    top = items[issue.top[0]] if issue.top else None
    emoji = f'{top.emoji} ' if top and top.emoji else ''
    label = f'第 {issue.id[5:]} 期' if chinese else f'Issue {issue.id}'
    title = _truncate(('[PREVIEW] ' if preview else '') +
                      _escape(f'{emoji}{cfg.name} — {label}'), TITLE_LIMIT)
    names, summaries, links = [], [], []
    for key in issue.top[:FIELD_LIMIT]:
        item = items[key]
        text = (item.zh or {}) if chinese else {}
        link = f' [{source}]({_link_url(item.source_url)})'
        if _length(link) >= FIELD_VALUE_LIMIT:
            raise DiscordError('Source link exceeds Discord field limit')
        names.append(_truncate(_escape(f'{item.emoji or ""} {text.get("headline") or item.headline}'.strip()), TITLE_LIMIT))
        copy = [_escape(text.get("summary") or item.summary),
                f'**{why}:** {_escape(text.get("why_it_matters") or item.why_it_matters)}']
        first_step = text.get("for_builders") or item.for_builders
        if first_step:
            copy.append(f'**{builders}:** {_escape(first_step)}')
        summaries.append(_truncate('\n'.join(copy), FIELD_VALUE_LIMIT - _length(link)))
        links.append(link)
    fixed = fixed_description + sum(map(_length, links))
    if preview:
        fixed += _length(PREVIEW_FOOTER)
    parts = _fit([title, *bullets, *names, *summaries], TOTAL_LIMIT - fixed)
    title = parts.pop(0)
    bullets, parts = parts[:len(bullets)], parts[len(bullets):]
    names, summaries = parts[:len(names)], parts[len(names):]
    embed: dict[str, Any] = {
        'title': title, 'url': page, 'color': cfg.discord.color,
        'description': _description(bullets, suffix, notice, heading),
        'fields': [{'name': name, 'value': summary + link, 'inline': False}
                   for name, summary, link in zip(names, summaries, links)],
    }
    if top and top.image_url:
        embed['image'] = {'url': _link_url(top.image_url)}
    if preview:
        embed['footer'] = {'text': PREVIEW_FOOTER}
    return {'username': cfg.name, 'allowed_mentions': {'parse': []}, 'embeds': [embed]}


def build_payload(issue: Issue, cfg: Config, preview: bool,
                  run_url: str | None, language: str = 'en') -> dict[str, Any]:
    return _payload(issue, cfg, preview, run_url, language=language)


def _retry_after(response: requests.Response) -> float:
    try:
        delay = float(response.json()['retry_after'])
        if math.isfinite(delay) and delay >= 0:
            return delay
    except (ValueError, TypeError, KeyError, OverflowError):
        pass
    raise DiscordError('429')


def _safe_transport_log(record: logging.LogRecord) -> bool:
    # urllib3 debug messages contain the secret path without its hostname, so
    # the application's full-URL redactor alone cannot protect these records.
    return '/api/webhooks/' not in record.getMessage()


def _post(payload: dict[str, Any], webhook_url: str, http: Http) -> requests.Response:
    transport_log = logging.getLogger('urllib3.connectionpool')
    transport_log.addFilter(_safe_transport_log)
    try:
        return http.session.post(webhook_url + '?wait=true', json=payload,
                                 timeout=http.cfg.sources.timeout_seconds,
                                 allow_redirects=False)
    except requests.RequestException:
        raise DiscordError('Discord request failed') from None
    finally:
        transport_log.removeFilter(_safe_transport_log)


def send(payload: dict[str, Any], webhook_url: str, http: Http) -> None:
    if not WEBHOOK.fullmatch(webhook_url):
        raise DiscordError('Invalid Discord webhook URL')
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        response = _post(payload, webhook_url, http)
        try:
            status = response.status_code
            if 200 <= status < 300:
                return
            if status != 429 or attempt == RATE_LIMIT_RETRIES:
                raise DiscordError(str(status))
            delay = _retry_after(response)
        finally:
            response.close()
        time.sleep(delay)


def _run_url(env: Mapping[str, str]) -> str | None:
    parts = [env.get(key) for key in ('GITHUB_SERVER_URL', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID')]
    if not all(parts):
        return None
    server, repository, run_id = parts
    return f'{server.rstrip("/")}/{repository}/actions/runs/{run_id}'


def publish(cfg: Config, issue: Issue, preview_flag: bool, dry_run: bool,
            env: Mapping[str, str]) -> str:
    preview = preview_flag or not cfg.publish_enabled
    target = 'preview' if preview else 'public'
    notice = DISABLED_NOTICE if not preview_flag and not cfg.publish_enabled else ''
    payloads = [_payload(issue, cfg, preview, _run_url(env), notice, language)
                for language in ('en', 'zh')]
    if dry_run:
        output = json.dumps({'target': target, 'payloads': payloads}, ensure_ascii=False, indent=2)
        print(redact(output))
        return 'dry-run'
    key = 'DISCORD_PREVIEW_WEBHOOK_URL' if preview else 'DISCORD_WEBHOOK_URL'
    webhook = env.get(key)
    if not webhook:
        if not preview:
            raise DiscordError('DISCORD_WEBHOOK_URL not set')
        logging.getLogger(__name__).warning('DISCORD_PREVIEW_WEBHOOK_URL not set; skipping preview')
        return 'skipped: DISCORD_PREVIEW_WEBHOOK_URL not set'
    http = Http(cfg)
    try:
        send(payloads[0], webhook, http)
        try:
            send(payloads[1], webhook, http)
        except DiscordError as error:
            raise DiscordError(f'Chinese message failed after English was sent: {error}') from None
    finally:
        http.close()
    return target
