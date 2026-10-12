from argparse import Namespace
from dataclasses import replace
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import requests
import responses

import run
from weekly_diff import discord, paths, pipeline
from weekly_diff.config import Config, load_config
from weekly_diff.http import Http
from weekly_diff.models import Issue

FIXTURES = Path(__file__).parent / 'fixtures'
CASES = json.loads((FIXTURES / 'discord/responses.json').read_text())


@pytest.fixture
def cfg() -> Config:
    return load_config(FIXTURES / 'config.yaml')


@pytest.fixture
def issue() -> Issue:
    result = Issue.from_dict(json.loads((FIXTURES / 'issues/2026-42.json').read_text()))
    result.top = [item.key for item in result.items()][:5][::-1]
    return result


def test_payload(cfg: Config, issue: Issue) -> None:
    payload = discord.build_payload(issue, cfg, False, None)
    assert payload['username'] == cfg.name
    assert payload['allowed_mentions'] == {'parse': []}
    assert len(payload['embeds']) == 1
    embed = payload['embeds'][0]
    assert embed['title'] == f'{cfg.name} — Issue {issue.id}'
    assert embed['url'] == cfg.issue_url(issue.id)
    assert embed['color'] == cfg.discord.color
    assert embed['description'].startswith('**This week in 60 seconds**\n• ')
    assert embed['description'].count('\n• ') == 3
    assert embed['description'].endswith(f'[Read the full issue →]({cfg.issue_url(issue.id)})')
    items = {item.key: item for item in issue.items()}
    for n, (key, field) in enumerate(zip(issue.top, embed['fields']), 1):
        headline = items[key].headline.replace('>', '\\>')
        value = f"{items[key].summary}\n**Why you'd care:** {discord._escape(items[key].why_it_matters)}"
        if items[key].for_builders:
            value += f"\n**How to try it:** {discord._escape(items[key].for_builders)}"
        assert field == {'name': headline,
                         'value': value + f' [Source]({items[key].source_url})',
                         'inline': False}
    assert 'footer' not in embed
    run_url = 'https://github.com/example/roundup/actions/runs/1234'
    preview = discord.build_payload(issue, cfg, True, run_url)['embeds'][0]
    assert preview['title'] == '[PREVIEW] ' + embed['title']
    assert preview['footer']['text'] == 'Preview — not posted publicly'
    assert f'[View workflow run]({run_url})' in preview['description']
    assert run_url not in str(discord.build_payload(issue, cfg, False, run_url))


def test_escaping(cfg: Config, issue: Issue) -> None:
    item = next(issue.items())
    issue.top = [item.key]
    item.headline = item.summary = CASES['markdown']
    issue.sixty_seconds = [CASES['markdown']] * 3
    embed = discord.build_payload(issue, cfg, True, None)['embeds'][0]
    for text in [embed['description'], embed['fields'][0]['name'], embed['fields'][0]['value']]:
        for character in '*_~`|>':
            assert '\\' + character in text
        assert '@everyone' not in text and '@here' not in text
        assert '@\u200beveryone' in text and '@\u200bhere' in text
        assert '\\[link\\]' in text
    assert embed['fields'][0]['value'].endswith(f'[Source]({item.source_url})')


@pytest.mark.parametrize('language', ['en', 'zh'])
@pytest.mark.parametrize('count', [5, 30])
def test_limits(cfg: Config, issue: Issue, count: int, language: str) -> None:
    original = next(issue.items())
    issue.sections = {'models': [replace(original, key=str(n), headline='🛠️*' * 1000,
                                         summary=CASES['markdown'] * 1000) for n in range(count)]}
    issue.top = [item.key for item in issue.items()]
    issue.sixty_seconds = [CASES['markdown'] * 1000] * 3
    cfg = replace(cfg, name='Roundup' * 100)
    for item in issue.items():
        item.zh = {'headline': item.headline, 'summary': item.summary}
    issue.sixty_seconds_zh = issue.sixty_seconds[:]
    embed = discord.build_payload(issue, cfg, True, None, language)['embeds'][0]
    source = '原文' if language == 'zh' else 'Source'
    def size(text: str) -> int:
        return len(text.encode('utf-16-le')) // 2
    assert size(embed['title']) <= 256
    assert size(embed['description']) <= 4096
    assert len(embed['fields']) == min(count, 25)
    total = size(embed['title']) + size(embed['description']) + size(embed['footer']['text'])
    for field in embed['fields']:
        assert size(field['name']) <= 256
        assert size(field['value']) <= 1024
        assert field['value'].endswith(f'[{source}]({original.source_url})')
        total += size(field['name']) + size(field['value'])
    assert total <= 6000
    assert '…' in str(embed)
    assert embed['description'].endswith(f']({embed["url"]})')


@pytest.mark.parametrize(('enabled', 'flag', 'target'), [
    (False, False, 'preview'), (True, False, 'public'),
    (True, True, 'preview'), (False, True, 'preview'),
])
def test_routing(cfg: Config, issue: Issue, offline_http: responses.RequestsMock,
                 enabled: bool, flag: bool, target: str) -> None:
    env = {'DISCORD_WEBHOOK_URL': CASES['public'], 'DISCORD_PREVIEW_WEBHOOK_URL': CASES['preview'],
           **CASES['run_env']}
    offline_http.post(CASES[target] + '?wait=true', json=CASES['success'])
    assert discord.publish(replace(cfg, publish_enabled=enabled), issue, flag, False, env) == target
    assert len(offline_http.calls) == 2
    for language, call in zip(('en', 'zh'), offline_http.calls):
        request = call.request
        assert request.url == CASES[target] + '?wait=true'
        assert request.headers['User-Agent'] == cfg.sources.user_agent
        payload = json.loads(request.body)
        assert payload['allowed_mentions'] == {'parse': []}
        embed = payload['embeds'][0]
        assert embed['title'].startswith('[PREVIEW]') == (target == 'preview')
        assert embed['description'].startswith(discord.DISABLED_NOTICE) == (not enabled and not flag)
        assert ('/actions/runs/1234' in embed['description']) == (target == 'preview')
        assert ('/zh/issues/' in embed['url']) == (language == 'zh')
        assert ('第 42 期' in embed['title']) == (language == 'zh')


def test_missing_hooks(cfg: Config, issue: Issue, offline_http: responses.RequestsMock,
                       caplog: pytest.LogCaptureFixture) -> None:
    assert discord.publish(cfg, issue, True, False, {}) == 'skipped: DISCORD_PREVIEW_WEBHOOK_URL not set'
    assert 'skipping preview' in caplog.text
    with pytest.raises(discord.DiscordError, match='^DISCORD_WEBHOOK_URL not set$'):
        discord.publish(replace(cfg, publish_enabled=True), issue, False, False, {})
    assert not offline_http.calls


@pytest.mark.parametrize('enabled', [False, True])
def test_dry_run(cfg: Config, issue: Issue, offline_http: responses.RequestsMock,
                 capsys: pytest.CaptureFixture[str], enabled: bool) -> None:
    assert discord.publish(replace(cfg, publish_enabled=enabled), issue, False, True, {}) == 'dry-run'
    output = json.loads(capsys.readouterr().out)
    assert output['target'] == ('public' if enabled else 'preview')
    assert len(output['payloads']) == 2
    assert all(payload['allowed_mentions'] == {'parse': []} for payload in output['payloads'])
    assert '/api/webhooks/' not in str(output)
    assert not offline_http.calls


def test_retry(cfg: Config, offline_http: responses.RequestsMock) -> None:
    url = CASES['public'] + '?wait=true'
    offline_http.post(url, status=429, json=CASES['rate_limit'])
    offline_http.post(url, status=429, json=CASES['rate_limit'])
    offline_http.post(url, status=200, json=CASES['success'])
    http = Http(cfg)
    try:
        with patch('weekly_diff.discord.time.sleep') as sleep, patch.object(http.session, 'post', wraps=http.session.post) as post:
            discord.send({}, CASES['public'], http)
            assert sleep.call_count == 2
            sleep.assert_called_with(0.25)
            assert post.call_args.kwargs['timeout'] == cfg.sources.timeout_seconds
            assert post.call_args.kwargs['allow_redirects'] is False
        assert len(offline_http.calls) == 3
    finally:
        http.close()


@pytest.mark.parametrize('status', [302, 429, 500])
def test_failure_is_safe(cfg: Config, issue: Issue, offline_http: responses.RequestsMock,
                         monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
                         status: int) -> None:
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', CASES['public'])
    offline_http.post(CASES['public'] + '?wait=true', status=status, json=CASES['rate_limit'])
    with patch('weekly_diff.discord.time.sleep'), caplog.at_level(logging.DEBUG):
        with pytest.raises(discord.DiscordError) as caught:
            discord.publish(replace(cfg, publish_enabled=True), issue, False, False,
                            {'DISCORD_WEBHOOK_URL': CASES['public']})
    assert str(caught.value) == str(status)
    assert CASES['public'] not in caplog.text
    assert 'fake-public-token' not in caplog.text
    assert len(offline_http.calls) == (3 if status == 429 else 1)


@pytest.mark.parametrize('url', [
    'http://discord.com/api/webhooks/123/fake', 'https://evil.test/api/webhooks/123/fake',
    'https://discord.com.evil.test/api/webhooks/123/fake',
    'https://discord.com@evil.test/api/webhooks/123/fake',
    'https://discord.com/api/webhooks/123/fake?redirect=1',
    'https://discord.com/api/webhooks/',
])
def test_reject_webhook(cfg: Config, offline_http: responses.RequestsMock, url: str) -> None:
    http = Http(cfg)
    try:
        with pytest.raises(discord.DiscordError) as caught:
            discord.send({}, url, http)
        assert url not in str(caught.value)
        assert not offline_http.calls
    finally:
        http.close()


def test_network_failure(cfg: Config, offline_http: responses.RequestsMock) -> None:
    offline_http.post(CASES['public'] + '?wait=true', body=requests.Timeout(CASES['public']))
    http = Http(cfg)
    try:
        with pytest.raises(discord.DiscordError, match='^Discord request failed$') as caught:
            discord.send({}, CASES['public'], http)
        assert caught.value.__suppress_context__
    finally:
        http.close()


@pytest.mark.parametrize('dry_run', [False, True])
def test_pipeline(cfg: Config, issue: Issue, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                  capsys: pytest.CaptureFixture[str], dry_run: bool) -> None:
    monkeypatch.setattr(paths, 'ISSUES', tmp_path / 'issues')
    monkeypatch.setattr(paths, 'DRY_RUN', tmp_path / 'dry-run')
    args = Namespace(issue=issue.id, dry_run=dry_run, preview=True)
    with pytest.raises(discord.DiscordError, match='build first'):
        pipeline.publish(cfg, args)
    paths.DRY_RUN.mkdir()
    (paths.DRY_RUN / f'{issue.id}.json').write_text(json.dumps(issue.to_dict()))
    if not dry_run:
        with pytest.raises(discord.DiscordError, match='build first'):
            pipeline.publish(cfg, args)
        paths.ISSUES.mkdir()
        (paths.ISSUES / f'{issue.id}.json').write_text(json.dumps(issue.to_dict()))
    with patch('weekly_diff.pipeline.publish_discord', return_value='dry-run' if dry_run else 'preview') as publish:
        pipeline.publish(cfg, args)
        assert publish.call_args.args[:4] == (cfg, issue, True, dry_run)
    assert capsys.readouterr().out.strip() == ('dry-run' if dry_run else 'preview')


def test_cli_dry_run(issue: Issue, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                     capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(paths, 'ISSUES', tmp_path)
    (tmp_path / f'{issue.id}.json').write_text(json.dumps(issue.to_dict()))
    assert run.main(['publish', '--issue', issue.id, '--preview', '--dry-run']) == 0
    assert capsys.readouterr().out.endswith('\ndry-run\n')


def test_verbose_transport_logs_hide_secret(cfg: Config, offline_http: responses.RequestsMock,
                                           caplog: pytest.LogCaptureFixture) -> None:
    def response_callback(request: requests.PreparedRequest) -> tuple[int, dict[str, str], str]:
        logging.getLogger('urllib3.connectionpool').debug('POST %s', request.path_url)
        return 200, {}, json.dumps(CASES['success'])

    offline_http.add_callback(responses.POST, CASES['public'] + '?wait=true', callback=response_callback)
    http = Http(cfg)
    try:
        with caplog.at_level(logging.DEBUG):
            discord.send({}, CASES['public'], http)
        assert 'fake-public-token' not in caplog.text
        assert discord._safe_transport_log not in logging.getLogger('urllib3.connectionpool').filters
    finally:
        http.close()


@pytest.mark.parametrize('delay', [None, -1, 'NaN', 'Infinity', 'invalid'])
def test_invalid_retry_delay(cfg: Config, offline_http: responses.RequestsMock, delay: Any) -> None:
    offline_http.post(CASES['public'] + '?wait=true', status=429, json={'retry_after': delay})
    http = Http(cfg)
    try:
        with patch('weekly_diff.discord.time.sleep') as sleep:
            with pytest.raises(discord.DiscordError, match='^429$'):
                discord.send({}, CASES['public'], http)
            sleep.assert_not_called()
        assert len(offline_http.calls) == 1
    finally:
        http.close()


def test_link_delimiters_and_invalid_links(cfg: Config, issue: Issue) -> None:
    item = next(issue.items())
    issue.top = [item.key]
    item.source_url = 'https://example.com/a_(b)?q=[test]&mention=@everyone'
    field = discord.build_payload(issue, cfg, False, None)['embeds'][0]['fields'][0]
    assert field['value'].endswith('[Source](https://example.com/a_%28b%29?q=%5Btest%5D&mention=%40everyone)')
    item.source_url = 'javascript:alert(1)'
    with pytest.raises(discord.DiscordError, match='Invalid link URL'):
        discord.build_payload(issue, cfg, False, None)
    item.source_url = 'https://example.com/' + 'x' * 1024
    with pytest.raises(discord.DiscordError, match='Source link exceeds'):
        discord.build_payload(issue, cfg, False, None)


def test_dry_run_prefers_saved_issue(cfg: Config, issue: Issue, tmp_path: Path,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, 'ISSUES', tmp_path / 'issues')
    monkeypatch.setattr(paths, 'DRY_RUN', tmp_path / 'dry-run')
    paths.ISSUES.mkdir()
    paths.DRY_RUN.mkdir()
    (paths.ISSUES / f'{issue.id}.json').write_text(json.dumps(issue.to_dict()))
    (paths.DRY_RUN / f'{issue.id}.json').write_text('{}')
    with patch('weekly_diff.pipeline.publish_discord', return_value='dry-run') as publish:
        pipeline.publish(cfg, Namespace(issue=issue.id, preview=False, dry_run=True))
        assert publish.call_args.args[1] == issue


def test_bilingual_payloads(cfg: Config, offline_http: responses.RequestsMock) -> None:
    issue = Issue.from_dict(json.loads((FIXTURES / 'bilingual_issues/2026-42.json').read_text()))
    item = next(issue.items())
    item.zh['headline'] = item.zh['summary'] = CASES['markdown']
    issue.sixty_seconds_zh[0] = CASES['markdown']
    offline_http.post(CASES['public'] + '?wait=true', json=CASES['success'])
    discord.publish(replace(cfg, publish_enabled=True), issue, False, False,
                    {'DISCORD_WEBHOOK_URL': CASES['public']})
    english, chinese = [json.loads(call.request.body)['embeds'][0] for call in offline_http.calls]
    assert english['title'] == f'{item.emoji} {cfg.name} — Issue {issue.id}'
    assert chinese['title'] == f'{item.emoji} {cfg.name} — 第 42 期'
    assert chinese['url'] == f'{cfg.site.base_url}/zh/issues/{issue.id}/'
    assert chinese['description'].startswith('**60 秒速览**')
    assert chinese['description'].endswith(f'[阅读全文 →]({chinese["url"]})')
    for embed in (english, chinese):
        assert embed['image'] == {'url': item.image_url}
        assert embed['fields'][0]['name'].startswith(item.emoji + ' ')
    assert chinese['fields'][0]['value'].endswith(f'[原文]({item.source_url})')
    for text in (chinese['description'], chinese['fields'][0]['name'], chinese['fields'][0]['value']):
        assert '@everyone' not in text and '@here' not in text
        assert '@\u200beveryone' in text
        assert '\\[link\\]' in text
    item.image_url = None
    item.zh = {'headline': '中文标题'}
    chinese = discord.build_payload(issue, cfg, False, None, 'zh')['embeds'][0]
    assert 'image' not in chinese
    assert chinese['fields'][0]['name'] == f'{item.emoji} 中文标题'
    assert chinese['fields'][0]['value'].startswith(item.summary)


@pytest.mark.parametrize('status', [500, 429])
def test_second_message_failure_never_resends_english(cfg: Config, issue: Issue,
                                                     offline_http: responses.RequestsMock,
                                                     status: int) -> None:
    url = CASES['public'] + '?wait=true'
    offline_http.post(url, json=CASES['success'])
    offline_http.post(url, status=status, json=CASES['rate_limit'])
    with patch('weekly_diff.discord.time.sleep'):
        with pytest.raises(discord.DiscordError, match=f'Chinese message failed after English was sent: {status}'):
            discord.publish(replace(cfg, publish_enabled=True), issue, False, False,
                            {'DISCORD_WEBHOOK_URL': CASES['public']})
    titles = [json.loads(call.request.body)['embeds'][0]['title'] for call in offline_http.calls]
    assert len(titles) == (4 if status == 429 else 2)
    assert 'Issue 2026-42' in titles[0]
    assert all('第 42 期' in title for title in titles[1:])


@pytest.mark.parametrize('language', ['en', 'zh'])
@pytest.mark.parametrize('first_step', [False, True])
def test_reader_labels_and_safe_details(cfg: Config, issue: Issue, language: str, first_step: bool) -> None:
    item = next(issue.items())
    issue.top = [item.key]
    item.why_it_matters = CASES['markdown']
    item.for_builders = CASES['markdown'] if first_step else None
    item.zh = {'why_it_matters': item.why_it_matters, 'for_builders': item.for_builders}
    value = discord.build_payload(issue, cfg, False, None, language)['embeds'][0]['fields'][0]['value']
    why, how = ('对你有什么用', '怎么上手') if language == 'zh' else ("Why you'd care", 'How to try it')
    assert f'**{why}:** {discord._escape(CASES["markdown"])}' in value
    assert (f'**{how}:**' in value) == first_step
    assert '@everyone' not in value and '@here' not in value
