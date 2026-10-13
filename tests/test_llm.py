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
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    cfg = replace(cfg, llm=replace(cfg.llm, provider=provider, timeout_seconds=240, max_retries=4))
    if expected is None:
        with pytest.raises(LLMNotConfigured, match='Set ANTHROPIC_API_KEY or OPENAI_API_KEY'):
            get_client(cfg)
        assert not any(mock.called for mock in sdk_mocks.values())
    else:
        get_client(cfg)
        sdk_mocks[expected].assert_called_once_with(timeout=cfg.llm.timeout_seconds,
            max_retries=cfg.llm.max_retries, default_headers={'User-Agent': cfg.sources.user_agent})


@pytest.mark.parametrize('provider', ['anthropic', 'openai'])
def test_request_and_usage(provider: str, sdk_mocks: dict[str, Mock], monkeypatch: pytest.MonkeyPatch,
                           caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv(f'{provider.upper()}_API_KEY', 'test-placeholder')
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    monkeypatch.setattr(f'weekly_diff.llm.{provider}_client.monotonic', Mock(side_effect=[10.0, 12.5]))
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
    assert 'duration_seconds=2.500' in caplog.text
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
        get_client(load_config(Path(__file__).parent / 'fixtures/config.yaml')).complete_json('', '', {}, 10)
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
        get_client(load_config(Path(__file__).parent / 'fixtures/config.yaml')).complete_json('', '', {}, 10)
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


CONSTRAINTS = json.loads((Path(__file__).parent / 'fixtures/llm_constraints.json').read_text())


def sdk_response(provider: str, payload: dict) -> object:
    raw = deepcopy(DATA[provider])
    if provider == 'anthropic':
        raw['content'][0]['text'] = json.dumps(payload)
    else:
        raw['output_text'] = json.dumps(payload)
    return namespace(raw)


@pytest.mark.parametrize('provider', ['anthropic', 'openai'])
@pytest.mark.parametrize('scenario', ['score', 'sixty'])
def test_constraint_payload_validation_and_retry(provider: str, scenario: str,
        sdk_mocks: dict[str, Mock], monkeypatch: pytest.MonkeyPatch) -> None:
    from weekly_diff.llm.fake import FakeLLM
    from weekly_diff.models import Candidate, Item
    from weekly_diff.score import _schema, score
    from weekly_diff.sixty import sixty

    monkeypatch.setenv(f'{provider.upper()}_API_KEY', 'test-placeholder')
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    client = get_client(cfg)
    sdk = sdk_mocks[provider].return_value
    method = sdk.messages.create if provider == 'anthropic' else sdk.responses.create
    if scenario == 'score':
        schema = _schema(cfg)
        good = {'items': [DATA['row']]}
        bad = {'items': [{**DATA['row'], 'score': 14}]}
        field = '$.items[0].score'
        def run() -> object:
            return score([Candidate.from_dict(DATA['candidate'])], cfg, client)
    else:
        item_data = json.loads((Path(__file__).parent / 'fixtures/models.json').read_text())['item']
        items = [replace(Item.from_dict(item_data), key=str(i)) for i in range(3)]
        good = {'bullets': [{'text': item.headline, 'text_zh': item.zh['headline'], 'item_keys': [item.key]} for item in items]}
        bad = {'bullets': good['bullets'][:2]}
        fake = FakeLLM([good])
        sixty(items, fake, cfg)
        schema = fake.calls[0]['schema']
        field = '$.bullets'
        def run() -> object:
            return sixty(items, client, cfg)
    original = deepcopy(schema)
    method.return_value = sdk_response(provider, bad)
    with pytest.raises(LLMError) as error:
        client.complete_json('', '', schema, 512)
    assert str(error.value) == f'response did not match schema: {field}'
    call = method.call_args.kwargs
    sent = (call['output_config']['format'] if provider == 'anthropic' else call['text']['format'])['schema']
    if provider == 'anthropic':
        for keyword in ('minimum', 'maximum', 'minItems', 'maxItems'):
            assert keyword not in json.dumps(sent)
    else:
        assert sent == strict_schema(schema)
    assert schema == original
    method.reset_mock()
    method.side_effect = [sdk_response(provider, bad), sdk_response(provider, good)]
    result = run()
    assert method.call_count == 2
    if scenario == 'score':
        assert result[0].score == DATA['row']['score']
    else:
        assert result == ([item.headline for item in items], [item.zh['headline'] for item in items])


@pytest.mark.parametrize(('schema', 'bad', 'good'), CONSTRAINTS['cases'])
def test_all_removed_constraints(schema: dict, bad: object, good: object) -> None:
    from weekly_diff.llm.anthropic_client import anthropic_schema
    from weekly_diff.llm.base import validate_constraints

    nested = {'type': 'object', 'properties': {'value': schema}}
    validate_constraints({'value': good}, nested)
    with pytest.raises(LLMError, match=r'response did not match schema: \$\.value'):
        validate_constraints({'value': bad}, nested)
    assert anthropic_schema(strict_schema(nested))['properties']['value'] == {}


@pytest.mark.parametrize('minimum', [0, 1, 2])
def test_sanitizer_preserves_supported_schema_and_property_names(minimum: int) -> None:
    from weekly_diff.llm.anthropic_client import anthropic_schema

    schema = {'type': 'object', 'properties': {'maximum': {'type': 'array', 'minItems': minimum,
              'items': {'anyOf': [{'type': 'string', 'maxLength': 2}, {'type': 'integer', 'maximum': 2}]}}}}
    original = deepcopy(schema)
    result = anthropic_schema(strict_schema(schema))
    array = result['properties']['maximum']
    assert array.get('minItems') == (minimum if minimum < 2 else None)
    assert array['items']['anyOf'] == [{'type': 'string'}, {'type': 'integer'}]
    assert result['required'] == ['maximum'] and result['additionalProperties'] is False
    assert schema == original


@pytest.mark.parametrize('provider', ['anthropic', 'openai'])
@pytest.mark.parametrize('status', [400, 429])
def test_status_error_details_redacted(provider: str, status: int, sdk_mocks: dict[str, Mock],
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f'{provider.upper()}_API_KEY', 'test-placeholder')
    module = anthropic if provider == 'anthropic' else openai
    body = {'error': deepcopy(CONSTRAINTS['error'])}
    body['error']['message'] += ' ' + 'x' * 280 + 'test-placeholder' + 'x' * 100
    body['request'] = 'private request body'
    error_class = module.RateLimitError if status == 429 else module.APIStatusError
    sdk = sdk_mocks[provider].return_value
    method = sdk.messages.create if provider == 'anthropic' else sdk.responses.create
    method.side_effect = error_class('private prompt and headers', response=Mock(status_code=status), body=body)
    with pytest.raises(LLMError) as error:
        get_client(load_config(Path(__file__).parent / 'fixtures/config.yaml')).complete_json('', '', {}, 10)
    message = str(error.value)
    label = 'Anthropic' if provider == 'anthropic' else 'OpenAI'
    assert message.startswith(f'{label} API error {status} invalid_request_error: Unsupported schema constraint; ***')
    assert len(message.split(': ', 1)[1]) == 300
    assert 'private' not in message and 'test-placeholder' not in message
    assert error.value.__suppress_context__


@pytest.mark.parametrize('provider', ['anthropic', 'openai'])
@pytest.mark.parametrize('timeout', [180, 240.5])
def test_sdk_timeout(provider: str, timeout: float, sdk_mocks: dict[str, Mock],
                     monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv(f'{provider.upper()}_API_KEY', 'test-placeholder')
    module = anthropic if provider == 'anthropic' else openai
    sdk = sdk_mocks[provider].return_value
    method = sdk.messages.create if provider == 'anthropic' else sdk.responses.create
    method.side_effect = module.APITimeoutError(request=Mock())
    monkeypatch.setattr(f'weekly_diff.llm.{provider}_client.monotonic', Mock(side_effect=[10.0, 12.5]))
    cfg = load_config(Path(__file__).parent / 'fixtures/config.yaml')
    cfg = replace(cfg, llm=replace(cfg.llm, timeout_seconds=timeout))
    with caplog.at_level(logging.INFO), pytest.raises(LLMError) as caught:
        get_client(cfg).complete_json('private system', 'private prompt', {}, 10)
    label = 'Anthropic' if provider == 'anthropic' else 'OpenAI'
    assert str(caught.value) == f'{label} request timed out after {timeout:g}s'
    assert caught.value.__suppress_context__
    assert 'duration_seconds=2.500' in caplog.text
    assert 'private' not in caplog.text and 'test-placeholder' not in caplog.text
