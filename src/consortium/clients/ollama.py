"""Ollama LLM client.

Wraps the `ollama` Python client to expose the LLMClient interface. Uses
Ollama's native structured-output support (`format=<JSON schema>`) for
structured calls, which constrains generation at the token level.

Requires Ollama server >= 0.5 for structured output. The `ollama` Python
package handles both server versions; structured output silently falls
back to free-text on older servers, so this client validates the result
against the schema on the client side as well.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import ollama
from pydantic import BaseModel, ValidationError

from consortium.clients.base import LLMClient, Message


class OllamaClient(LLMClient):
    """LLMClient backed by a local or remote Ollama server.

    The `model` argument is passed to Ollama directly and must match a
    tag that Ollama has pulled (e.g. 'llama3.1:8b', 'qwen2.5:7b').
    """

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        name: Optional[str] = None,
        default_options: Optional[dict[str, Any]] = None,
    ):
        self.model = model
        self.host = host
        self.name = name or f"ollama:{model}"
        self.default_options = dict(default_options or {})
        self._client = ollama.Client(host=host)

    def _build_options(
        self,
        temperature: float,
        max_tokens: Optional[int],
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        options = dict(self.default_options)
        options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        options.update(extra)
        return options

    @staticmethod
    def _extract_content(response: Any) -> str:
        """Tolerate dict-style or attribute-style responses from ollama-python."""
        if isinstance(response, dict):
            return response["message"]["content"]
        return response.message.content

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        options = self._build_options(temperature, max_tokens, kwargs)
        response = self._client.chat(
            model=self.model,
            messages=[m.model_dump() for m in messages],
            options=options,
        )
        return self._extract_content(response)

    def chat_structured(
        self,
        messages: list[Message],
        *,
        response_model: type[BaseModel],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> BaseModel:
        options = self._build_options(temperature, max_tokens, kwargs)
        schema = response_model.model_json_schema()
        response = self._client.chat(
            model=self.model,
            messages=[m.model_dump() for m in messages],
            options=options,
            format=schema,
        )
        raw_content = self._extract_content(response)

        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"OllamaClient[{self.model}]: response was not valid JSON "
                f"despite structured-output constraint. "
                f"Content preview: {raw_content[:500]!r}"
            ) from e

        try:
            return response_model.model_validate(parsed)
        except ValidationError as e:
            raise ValueError(
                f"OllamaClient[{self.model}]: JSON did not validate against "
                f"{response_model.__name__}. Errors: {e}. "
                f"Content preview: {raw_content[:500]!r}"
            ) from e