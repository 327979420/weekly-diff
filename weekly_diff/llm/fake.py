"""Deterministic completions and call recording for offline pipeline tests."""
from collections import deque
from collections.abc import Callable, Iterable
from copy import deepcopy
from typing import Any

from weekly_diff.llm.base import LLMError


class FakeLLM:
    def __init__(self, responses: Iterable[dict | Exception] | Callable[..., dict] = ()) -> None:
        self.handler = responses if callable(responses) else None
        self.responses = deque(() if callable(responses) else responses)
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> dict:
        call = dict(system=system, user=user, schema=deepcopy(schema), max_tokens=max_tokens)
        self.calls.append(call)
        if self.handler is not None:
            return deepcopy(self.handler(**call))
        if not self.responses:
            raise LLMError('FakeLLM response queue exhausted')
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return deepcopy(response)
