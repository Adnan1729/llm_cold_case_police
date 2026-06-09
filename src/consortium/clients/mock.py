"""Mock LLM client for offline development and testing.

The mock returns queued responses in FIFO order. It does not attempt to
infer responses from context; tests and development scripts are expected
to pre-load the queue with the responses they expect. This keeps the
mock behaviour fully deterministic.

For free-text calls without a queued response, returns a fixed
placeholder. For structured calls without a queued response, raises
NotImplementedError with a clear message.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from consortium.clients.base import LLMClient, Message


class MockClient(LLMClient):
    """Deterministic mock for offline tests and pipeline development."""

    def __init__(
        self,
        name: str = "mock-default",
        responses: Optional[list[str]] = None,
        structured_responses: Optional[list[BaseModel]] = None,
    ):
        self.name = name
        self._responses: list[str] = list(responses or [])
        self._structured_responses: list[BaseModel] = list(structured_responses or [])
        self.call_log: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        self.call_log.append(
            {
                "method": "chat",
                "messages": [m.model_dump() for m in messages],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "kwargs": kwargs,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return "MOCK_RESPONSE: free-text placeholder (no queued response)."

    def chat_structured(
        self,
        messages: list[Message],
        *,
        response_model: type[BaseModel],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> BaseModel:
        self.call_log.append(
            {
                "method": "chat_structured",
                "messages": [m.model_dump() for m in messages],
                "schema": response_model.__name__,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "kwargs": kwargs,
            }
        )
        if not self._structured_responses:
            raise NotImplementedError(
                f"MockClient has no queued structured response for "
                f"{response_model.__name__}. Provide one via the "
                f"`structured_responses` constructor argument."
            )
        response = self._structured_responses.pop(0)
        if not isinstance(response, response_model):
            raise TypeError(
                f"MockClient: queued structured response is of type "
                f"{type(response).__name__}, expected {response_model.__name__}."
            )
        return response