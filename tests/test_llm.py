from copy import deepcopy
from dataclasses import replace
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import anthropic
import openai
import pytest

from weekly_diff.config import load_config
from weekly_diff.llm import LLMError, LLMNotConfigured, get_client
from weekly_diff.llm.base import InvalidJSON, parse_json, strict_schema

DATA = json.loads((Path(__file__).parent / 'fixtures/shortlist.json').read_text())


def namespace(value: object) -> object:
    if isinstance(value, dict):
        return SimpleNamespace(**{key: namespace(item) for key, item in value.items()})
    if isinstance(value, list):
        return [namespace(item) for item in value]
    return value


@pytest.fixture
def sdk_mocks(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    result = {}
    for name, module, constructor in [('anthropic', anthropic, 'Anthropic'), ('openai', openai, 'OpenAI')]:
        monkeypatch.delenv(f'{name.upper()}_API_KEY', raising=False)
        factory = Mock()
        factory.return_value.messages.create.return_value = namespace(DATA['anthropic'])
        factory.return_value.responses.create.return_value = namespace(DATA['openai'])
        monkeypatch.setattr(module, constructor, factory)
        result[name] = factory
    return result


@pytest.mark.parametrize(('provider', 'keys', 'expected'), [
    ('auto', [], None), ('auto', ['openai'], 'openai'), ('auto', ['anthropic', 'openai'], 'anthropic'),
    ('anthropic', ['openai'], None), ('openai', ['anthropic'], None),
    ('openai', ['anthropic', 'openai'], 'openai'), ('anthropic', ['anthropic'], 'anthropic'),
])
def test_provider_selection(provider: str, keys: list[str], expected: str | None,
                            sdk_mocks: dict[str, Mock], monkeypatch: pytest.MonkeyPatch) -> None:
    for key in keys:
        monkeypatch.setenv(f'{key.upper()}_API_KEY', 'test-placeholder')
    cfg = load_config()
    cfg = replace(cfg, llm=replace(cfg.llm, provider=provider))
    if expected is None:
        with pytest.raises(LLMNotConfigured, match='Set ANTHROPIC_API_KEY or OPENAI_API_KEY'):
            get_client(cfg)
        assert not any(mock.called for mock in sdk_mocks.values())
    else:
        get_client(cfg)
        sdk_mocks[expected].assert_called_once_with(timeout=cfg.sources.timeout_seconds,
            max_retries=cfg.sources.retries, default_headers={'User-Agent': cfg.sources.user_agent})


@pytest.mark.parametrize('provider', ['anthropic', 'openai'])
def test_request_and_usage(provider: str, sdk_mocks: dict[str, Mock], monkeypatch: pytest.MonkeyPatch,
                           caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv(f'{provider.upper()}_API_KEY', 'test-placeholder')
    cfg = load_config()
    client = get_client(cfg)
    with caplog.at_level(logging.INFO):
        assert client.complete_json('private system', 'private prompt', {'type': 'object', 'properties': {}}, 512) == {'items': []}
    sdk = sdk_mocks[provider].return_value
    call = (sdk.messages.create if provider == 'anthropic' else sdk.responses.create).call_args.kwargs
    assert call['model'] == getattr(cfg.llm, f'{provider}_model')
    assert not {'temperature', 'top_p', 'thinking'} & call.keys()
    format_config = call['output_config']['format'] if provider == 'anthropic' else call['text']['format']
    assert format_config['type'] == 'json_schema'
    assert format_config['schema']['additionalProperties'] is False
    assert format_config['schema']['required'] == []
    if provider == 'anthropic':
        assert call['output_config']['effort'] == cfg.llm.effort
        assert call['max_tokens'] == 512
    else:
        assert call['reasoning']['effort'] == cfg.llm.effort
        assert call['text']['format']['strict'] is True
        assert call['max_output_tokens'] == 512
    assert 'input_tokens=12 output_tokens=6' in caplog.text
    assert call['model'] in caplog.text
    assert 'private' not in caplog.text and 'test-placeholder' not in caplog.text


@pytest.mark.parametrize(('provider', 'failure'), [('anthropic', 'refusal'), ('anthropic', 'max_tokens'),
                                                  ('openai', 'refusal'), ('openai', 'incomplete')])
def test_refusal_and_truncation(provider: str, failure: str, sdk_mocks: dict[str, Mock],
                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f'{provider.upper()}_API_KEY', 'test-placeholder')
    raw = deepcopy(DATA[provider])
    if provider == 'anthropic':
        raw['stop_reason'] = failure
    elif failure == 'refusal':
        raw['output'][0]['content'] = [{'type': 'refusal', 'refusal': 'private refusal'}]
    else:
        raw['status'] = failure
    sdk = sdk_mocks[provider].return_value
    method = sdk.messages.create if provider == 'anthropic' else sdk.responses.create
    method.return_value = namespace(raw)
    with pytest.raises(LLMError) as error:
        get_client(load_config()).complete_json('', '', {}, 10)
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('provider', ['anthropic', 'openai'])
@pytest.mark.parametrize('kind', ['RateLimitError', 'APIStatusError', 'APIConnectionError'])
def test_sdk_errors_are_safe(provider: str, kind: str, sdk_mocks: dict[str, Mock],
                             monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f'{provider.upper()}_API_KEY', 'test-placeholder')
    module = anthropic if provider == 'anthropic' else openai
    if kind == 'APIConnectionError':
        error = module.APIConnectionError(message='private key and request', request=Mock())
    else:
        error = getattr(module, kind)('private key and request', response=Mock(status_code=429), body=None)
    sdk = sdk_mocks[provider].return_value
    (sdk.messages.create if provider == 'anthropic' else sdk.responses.create).side_effect = error
    with pytest.raises(LLMError) as caught:
        get_client(load_config()).complete_json('', '', {}, 10)
    assert 'private' not in str(caught.value)
    assert caught.value.__suppress_context__


def test_json_parsing_and_nested_schema() -> None:
    for text in ('not json', '[]', 'null'):
        with pytest.raises(InvalidJSON):
            parse_json(text)
    schema = {'type': 'object', 'properties': {'items': {'type': 'array', 'items': {
        'type': 'object', 'properties': {'id': {'type': 'string'}}}}}}
    result = strict_schema(schema)
    nested = result['properties']['items']['items']
    assert nested['additionalProperties'] is False and nested['required'] == ['id']
    assert 'required' not in schema
