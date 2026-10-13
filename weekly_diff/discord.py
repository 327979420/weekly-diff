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

from weekly_diff.images import hero_item, local_image
from weekly_diff.site import _period
from weekly_diff.tags import tag_labels
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


def _embed_length(embed: dict[str, Any]) -> int:
    return sum(_length(embed.get(key, '')) for key in ('title', 'description')) + _length(
        embed.get('footer', {}).get('text', ''))


def _payload(issue: Issue, cfg: Config, preview: bool, run_url: str | None,
             notice: str = '', language: str = 'zh') -> dict[str, Any]:
    chinese = language == 'zh'
    name = cfg.name_zh if chinese else cfg.name
    root = f'{cfg.site.base_url}/' + ('zh/' if chinese else '')
    page = _link_url(f'{root}issues/{issue.id}/')
    label = f'第 {int(issue.id[5:])} 期' if chinese else f'Issue {int(issue.id[5:])}'
    period = _period(issue, cfg.site.timezone, language)
    period = period.removesuffix(f' · {issue.period_end.year}') if chinese else period
    prefix = ('【预览】' if chinese else '[PREVIEW] ') if preview else ''
    content = _truncate(prefix + f'📰 **{_escape(name)} · {label}** '
                        + ('已更新' if chinese else 'is out') + f' · {period}', 2000)
    bullets = [_escape(issue.sixty_seconds_zh[i] if chinese and i < len(issue.sixty_seconds_zh)
                       and issue.sixty_seconds_zh[i] else bullet)
               for i, bullet in enumerate(issue.sixty_seconds[:3])]
    description = '\n'.join(f'**{i}.** {_truncate(bullet, 1000)}' for i, bullet in enumerate(bullets, 1))
    header: dict[str, Any] = {
        'title': '本周要点' if chinese else 'This week', 'url': page,
        'description': _truncate(description, DESCRIPTION_LIMIT), 'color': cfg.discord.color,
    }
    hero = hero_item(issue)
    if hero and (relative := local_image(hero, issue.id)):
        header['image'] = {'url': _link_url(f'{cfg.site.base_url}/{relative}')}
    items = {item.key: item for item in issue.items()}
    keys = issue.top[:min(cfg.issue.top_items, 8)]
    if any(key not in items for key in keys):
        raise DiscordError('Issue top references a missing item')
    cards = []
    labels = tag_labels(cfg.tags_zh if chinese else cfg.tags)
    for key in keys:
        item = items[key]
        text = (item.zh or {}) if chinese else {}
        url = _link_url(item.source_url)
        if _length(url) > 2048:
            raise DiscordError('Source link exceeds Discord URL limit')
        summary = _escape(text.get('summary') or item.summary)
        builders = text.get('for_builders') or item.for_builders
        if builders:
            summary += '\n' + ('**上手：** ' if chinese else '**Try it:** ') + _escape(builders)
        card: dict[str, Any] = {
            'title': _truncate(_escape(f"{item.emoji or ''} {text.get('headline') or item.headline}".strip()), TITLE_LIMIT),
            'url': url, 'description': _truncate(summary, DESCRIPTION_LIMIT),
            'footer': {'text': _truncate(_escape(f'{urlsplit(item.source_url).hostname} · {labels[item.tag]}'), 2048)},
            'color': cfg.discord.color,
        }
        if relative := local_image(item, issue.id):
            card['thumbnail'] = {'url': _link_url(f'{cfg.site.base_url}/{relative}')}
        cards.append(card)
    read, archive = ('阅读完整一期 →', '往期') if chinese else ('Read the full issue →', 'Past issues')
    links = f'[{read}]({page}) · [{archive}]({_link_url(root + "archive/")}) · [RSS]({_link_url(root + "feed.xml")})'
    if preview and run_url:
        links += f'\n[View workflow run]({_link_url(run_url)})'
    if notice:
        links += '\n' + notice
    footer = '每周一 08:00（墨尔本）更新' if chinese else 'Updated every Monday at 08:00 (Melbourne)'
    if preview:
        footer += ' · ' + PREVIEW_FOOTER
    if _length(links) > DESCRIPTION_LIMIT:
        raise DiscordError('Links exceed Discord payload limits')
    last = {'description': links, 'footer': {'text': footer}, 'color': cfg.discord.color}
    while cards and sum(_embed_length(embed) for embed in [header, *cards, last]) > TOTAL_LIMIT:
        cards.pop()
    if _embed_length(header) + _embed_length(last) > TOTAL_LIMIT:
        header['description'] = _truncate(header['description'], max(1, TOTAL_LIMIT - _embed_length(last) - _length(header['title'])))
    return {'username': name, 'content': content, 'allowed_mentions': {'parse': []},
            'embeds': [header, *cards, last]}


def build_payload(issue: Issue, cfg: Config, preview: bool,
                  run_url: str | None, language: str = 'zh') -> dict[str, Any]:
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
                for language in cfg.discord.languages]
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
        for index, payload in enumerate(payloads):
            try:
                send(payload, webhook, http)
            except DiscordError as error:
                if index:
                    raise DiscordError(f'{cfg.discord.languages[index]} message failed after earlier messages were sent: {error}') from None
                raise
    finally:
        http.close()
    return target
