"""Anthropic structured outputs, with safe failure messages."""
import logging

import anthropic

from weekly_diff.config import Config
from weekly_diff.llm.base import (LLMError, api_status_message, parse_json,
                                  strict_schema, validate_constraints)

logger = logging.getLogger(__name__)


class AnthropicClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        # SDK debug logging includes request bodies; the application logs usage only.
        logging.getLogger('anthropic').setLevel(logging.WARNING)
        self.client = anthropic.Anthropic(timeout=cfg.sources.timeout_seconds,
                                          max_retries=cfg.sources.retries,
                                          default_headers={'User-Agent': cfg.sources.user_agent})

    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> dict:
        try:
            response = self.client.messages.create(
                model=self.cfg.llm.anthropic_model, max_tokens=max_tokens, system=system,
                messages=[{'role': 'user', 'content': user}],
                output_config={'format': {'type': 'json_schema', 'schema': anthropic_schema(strict_schema(schema))},
                               'effort': self.cfg.llm.effort})
        except anthropic.APIStatusError as error:
            raise LLMError(api_status_message('Anthropic', error.status_code, error.body)) from None
        except anthropic.APIConnectionError:
            raise LLMError('Anthropic connection error') from None
        except anthropic.APIError:
            raise LLMError('Anthropic API error') from None
        logger.info('LLM model=%s input_tokens=%s output_tokens=%s',
                    self.cfg.llm.anthropic_model, response.usage.input_tokens, response.usage.output_tokens)
        if response.stop_reason in {'refusal', 'max_tokens'}:
            raise LLMError('Anthropic refused or truncated completion')
        for block in response.content:
            if block.type == 'text':
                result = parse_json(block.text)
                validate_constraints(result, schema)
                return result
        raise LLMError('Anthropic returned no text')


def anthropic_schema(schema: dict) -> dict:
    """Copy a strict schema, omitting constraints unsupported by Anthropic."""
    unsupported = {'minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum',
                   'multipleOf', 'minLength', 'maxLength', 'pattern', 'maxItems', 'uniqueItems'}
    result = {}
    for key, value in schema.items():
        if key in unsupported or (key == 'minItems' and value not in (0, 1)):
            continue
        if key in {'properties', '$defs'}:
            result[key] = {name: anthropic_schema(child) for name, child in value.items()}
        elif isinstance(value, dict):
            result[key] = anthropic_schema(value)
        elif isinstance(value, list):
            result[key] = [anthropic_schema(child) if isinstance(child, dict) else child for child in value]
        else:
            result[key] = value
    return result
