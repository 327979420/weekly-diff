"""Select the sole provider boundary from configuration and environment."""
import os

from weekly_diff.config import Config
from weekly_diff.llm.base import LLMClient, LLMError, LLMNotConfigured

__all__ = ['get_client', 'LLMClient', 'LLMError', 'LLMNotConfigured']


def get_client(cfg: Config) -> LLMClient:
    provider = cfg.llm.provider
    if provider == 'auto':
        provider = 'anthropic' if os.environ.get('ANTHROPIC_API_KEY') else 'openai'
    if not os.environ.get(f'{provider.upper()}_API_KEY'):
        raise LLMNotConfigured('Set ANTHROPIC_API_KEY or OPENAI_API_KEY')
    if provider == 'anthropic':
        from weekly_diff.llm.anthropic_client import AnthropicClient
        return AnthropicClient(cfg)
    from weekly_diff.llm.openai_client import OpenAIClient
    return OpenAIClient(cfg)
