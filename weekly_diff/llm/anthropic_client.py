"""Anthropic structured outputs, with safe failure messages."""
import logging

import anthropic

from weekly_diff.config import Config
from weekly_diff.llm.base import LLMError, parse_json, strict_schema

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
                output_config={'format': {'type': 'json_schema', 'schema': strict_schema(schema)},
                               'effort': self.cfg.llm.effort})
        except anthropic.RateLimitError:
            raise LLMError('Anthropic rate limit') from None
        except anthropic.APIStatusError:
            raise LLMError('Anthropic API status error') from None
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
                return parse_json(block.text)
        raise LLMError('Anthropic returned no text')
