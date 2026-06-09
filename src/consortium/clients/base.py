"""LLM client interface — the contract every model backend implements.

This abstraction is used by the pipeline for any direct LLM call:
- Ingestion (parsing raw text into EvidenceCards).
- CEG generation (top hypothesis → ChainEventGraph).
- Validators that require LLM judgement.

The consortium stage itself uses AutoGen's native ChatCompletionClient
interface, not this one. Both ultimately call the same model server
(typically Ollama in this project), but via different client objects.
That separation is intentional: it lets the rest of the pipeline stay
synchronous and framework-agnostic while AutoGen runs async internally.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel


class Message(BaseModel):
    """A single chat message in OpenAI-compatible format."""

    role: str  # "system" | "user" | "assistant"
    content: str


class LLMClient(ABC):
    """Abstract interface for a single LLM endpoint.

    Implementations live in sibling modules: OllamaClient, MockClient, and
    (later) VLLMClient. Each implementation wraps one model on one server.

    The `name` attribute is used in logs and audit trails; it must be set
    by each implementation.
    """

    name: str

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Send a chat completion request and return the raw text response."""
        raise NotImplementedError

    @abstractmethod
    def chat_structured(
        self,
        messages: list[Message],
        *,
        response_model: type[BaseModel],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> BaseModel:
        """Send a chat completion request expecting JSON output that conforms
        to a Pydantic model. Returns a validated model instance.

        Implementations should use server-side structured-output enforcement
        where available (e.g. Ollama's `format=<schema>` parameter), and
        validate the result against the schema on the client side as a
        defence in depth. Raises ValueError if the output cannot be parsed
        or validated.
        """
        raise NotImplementedError