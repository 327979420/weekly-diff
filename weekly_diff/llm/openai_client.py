"""OpenAI Responses strict structured outputs."""
import logging

import openai

from weekly_diff.config import Config
from weekly_diff.llm.base import (LLMError, api_status_message, parse_json,
                                  strict_schema, validate_constraints)

logger = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        logging.getLogger('openai').setLevel(logging.WARNING)
        self.client = openai.OpenAI(timeout=cfg.sources.timeout_seconds,
                                    max_retries=cfg.sources.retries,
                                    default_headers={'User-Agent': cfg.sources.user_agent})

    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> dict:
        try:
            response = self.client.responses.create(
                model=self.cfg.llm.openai_model, instructions=system, input=user,
                max_output_tokens=max_tokens, reasoning={'effort': self.cfg.llm.effort},
                text={'format': {'type': 'json_schema', 'name': 'completion',
                                 'strict': True, 'schema': strict_schema(schema)}}, store=False)
        except openai.APIStatusError as error:
            raise LLMError(api_status_message('OpenAI', error.status_code, error.body)) from None
        except openai.APIConnectionError:
            raise LLMError('OpenAI connection error') from None
        except openai.APIError:
            raise LLMError('OpenAI API error') from None
        if response.usage is not None:
            logger.info('LLM model=%s input_tokens=%s output_tokens=%s', self.cfg.llm.openai_model,
                        response.usage.input_tokens, response.usage.output_tokens)
        if response.status != 'completed':
            raise LLMError('OpenAI incomplete completion')
        if any(block.type == 'refusal' for item in response.output
               for block in getattr(item, 'content', [])):
            raise LLMError('OpenAI refused completion')
        result = parse_json(response.output_text)
        validate_constraints(result, schema)
        return result
