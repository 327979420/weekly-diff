"""Provider-independent structured completion contract and safe parsing."""
from decimal import Decimal
import json
import re
from typing import Any, Protocol

from weekly_diff.log import redact


class LLMError(RuntimeError):
    """A provider call failed without exposing request or response content."""


class LLMNotConfigured(LLMError):
    """No credential is available for the selected provider."""


class InvalidJSON(LLMError):
    """A completion was not a JSON object; scoring may retry once."""


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> dict:
        ...


def parse_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise InvalidJSON('Invalid JSON completion') from None


def strict_schema(schema: dict) -> dict:
    """Return a copy with every object closed and all properties required."""
    result = {}
    for key, value in schema.items():
        if isinstance(value, dict):
            result[key] = {k: strict_schema(v) if isinstance(v, dict) else v
                           for k, v in value.items()} if key in {'properties', '$defs'} else strict_schema(value)
        elif isinstance(value, list):
            result[key] = [strict_schema(v) if isinstance(v, dict) else v for v in value]
        else:
            result[key] = value
    if result.get('type') == 'object':
        result['additionalProperties'] = False
        result['required'] = list(result.get('properties', {}))
    return result


def validate_constraints(value: Any, schema: dict, field: str = '$') -> None:
    """Enforce constraints omitted from the Anthropic wire schema."""
    valid = True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        checks = {'minimum': lambda limit: value >= limit,
                  'maximum': lambda limit: value <= limit,
                  'exclusiveMinimum': lambda limit: value > limit,
                  'exclusiveMaximum': lambda limit: value < limit,
                  'multipleOf': lambda limit: Decimal(str(value)) % Decimal(str(limit)) == 0}
        valid = all(check(schema[key]) for key, check in checks.items() if key in schema)
    elif isinstance(value, str):
        valid = (len(value) >= schema.get('minLength', 0)
                 and len(value) <= schema.get('maxLength', float('inf'))
                 and ('pattern' not in schema or re.search(schema['pattern'], value) is not None))
    elif isinstance(value, list):
        valid = (len(value) >= schema.get('minItems', 0)
                 and len(value) <= schema.get('maxItems', float('inf'))
                 and (not schema.get('uniqueItems')
                      or all(item not in value[:i] for i, item in enumerate(value))))
    if not valid:
        raise InvalidJSON(f'response did not match schema: {field}')
    if isinstance(value, dict):
        for name, child in schema.get('properties', {}).items():
            if name in value:
                validate_constraints(value[name], child, f'{field}.{name}')
    elif isinstance(value, list) and isinstance(schema.get('items'), dict):
        for index, item in enumerate(value):
            validate_constraints(item, schema['items'], f'{field}[{index}]')


def api_status_message(provider: str, status: int, body: object) -> str:
    """Read only API error fields, redacting before truncation to avoid partial secrets."""
    error = body.get('error', body) if isinstance(body, dict) else {}
    if not isinstance(error, dict):
        error = {}
    kind = error.get('type')
    message = error.get('message')
    kind = redact(kind)[:300] if isinstance(kind, str) else 'unknown_error'
    message = redact(message)[:300] if isinstance(message, str) else 'No error detail'
    return f'{provider} API error {status} {kind}: {message}'
