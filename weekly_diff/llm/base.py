"""Provider-independent structured completion contract and safe parsing."""
import json
from typing import Any, Protocol


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
