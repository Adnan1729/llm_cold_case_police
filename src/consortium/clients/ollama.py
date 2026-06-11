"""Ollama LLM client with retry-on-validation-failure and audit logging."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

import ollama
from pydantic import BaseModel, ValidationError

from consortium.clients.base import LLMClient, Message
from consortium.utils.audit import RunLogger, get_active_logger


class OllamaClient(LLMClient):
    """LLMClient backed by a local or remote Ollama server."""

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
        if isinstance(response, dict):
            return response["message"]["content"]
        return response.message.content

    # ------------------------------------------------------------------
    # Free-text chat
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        options = self._build_options(temperature, max_tokens, kwargs)
        started = datetime.now()
        prompt_chars = sum(len(m.content) for m in messages)
        logger = get_active_logger()

        try:
            response = self._client.chat(
                model=self.model,
                messages=[m.model_dump() for m in messages],
                options=options,
            )
            content = self._extract_content(response)
        except Exception as e:
            self._log_call(
                logger, method="chat", attempt=1, started=started,
                prompt_chars=prompt_chars, outcome="client_error", error=e,
            )
            raise

        self._log_call(
            logger, method="chat", attempt=1, started=started,
            prompt_chars=prompt_chars, outcome="success",
            response_chars=len(content),
        )
        return content

    # ------------------------------------------------------------------
    # Structured chat with retry and full instrumentation
    # ------------------------------------------------------------------

    def chat_structured(
        self,
        messages: list[Message],
        *,
        response_model: type[BaseModel],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        max_retries: int = 1,
        **kwargs: Any,
    ) -> BaseModel:
        options = self._build_options(temperature, max_tokens, kwargs)
        schema = response_model.model_json_schema()
        current = [m.model_dump() for m in messages]
        raw_content = ""
        logger = get_active_logger()

        for attempt in range(max_retries + 1):
            attempt_num = attempt + 1
            started = datetime.now()
            prompt_chars = sum(len(m["content"]) for m in current)

            try:
                response = self._client.chat(
                    model=self.model,
                    messages=current,
                    options=options,
                    format=schema,
                )
                raw_content = self._extract_content(response)
            except Exception as e:
                self._log_call(
                    logger, method="chat_structured", attempt=attempt_num,
                    started=started, prompt_chars=prompt_chars,
                    response_model=response_model.__name__,
                    outcome="client_error", error=e,
                )
                raise

            # Try JSON parse
            try:
                parsed = json.loads(raw_content)
            except json.JSONDecodeError as e:
                artefact = self._save_bad_output(
                    logger, attempt_num, response_model.__name__, raw_content
                )
                self._log_call(
                    logger, method="chat_structured", attempt=attempt_num,
                    started=started, prompt_chars=prompt_chars,
                    response_model=response_model.__name__,
                    response_chars=len(raw_content),
                    outcome="json_parse_error", error=e,
                    raw_output_artifact=artefact,
                )
                if attempt < max_retries:
                    current = self._with_retry_turn(
                        current, raw_content,
                        f"Your previous response was not valid JSON: {e}. "
                        f"Output ONLY a valid JSON object.",
                    )
                    if logger:
                        logger.event(
                            "llm_retry",
                            client=self.name,
                            after_attempt=attempt_num,
                            reason="json_parse_error",
                        )
                    continue
                raise ValueError(
                    f"OllamaClient[{self.model}]: response was not valid JSON "
                    f"after {max_retries + 1} attempt(s). "
                    f"Content preview: {raw_content[:500]!r}"
                ) from e

            # Try schema validation
            try:
                result = response_model.model_validate(parsed)
            except ValidationError as e:
                artefact = self._save_bad_output(
                    logger, attempt_num, response_model.__name__, raw_content
                )
                self._log_call(
                    logger, method="chat_structured", attempt=attempt_num,
                    started=started, prompt_chars=prompt_chars,
                    response_model=response_model.__name__,
                    response_chars=len(raw_content),
                    outcome="validation_error", error=e,
                    raw_output_artifact=artefact,
                )
                if attempt < max_retries:
                    current = self._with_retry_turn(
                        current, raw_content,
                        (
                            "Your previous response failed schema validation "
                            f"with these errors:\n{e}\n\n"
                            "Please regenerate the JSON, paying careful "
                            "attention to the constraints that were violated. "
                            "Output ONLY the corrected JSON object."
                        ),
                    )
                    if logger:
                        logger.event(
                            "llm_retry",
                            client=self.name,
                            after_attempt=attempt_num,
                            reason="validation_error",
                            validation_errors=str(e)[:500],
                        )
                    continue
                raise ValueError(
                    f"OllamaClient[{self.model}]: JSON did not validate "
                    f"against {response_model.__name__} after "
                    f"{max_retries + 1} attempt(s). Errors: {e}. "
                    f"Content preview: {raw_content[:500]!r}"
                ) from e

            # Success
            self._log_call(
                logger, method="chat_structured", attempt=attempt_num,
                started=started, prompt_chars=prompt_chars,
                response_model=response_model.__name__,
                response_chars=len(raw_content),
                outcome="success",
            )
            return result

        raise RuntimeError("chat_structured loop exited unexpectedly")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log_call(
        self,
        logger: Optional[RunLogger],
        *,
        method: str,
        attempt: int,
        started: datetime,
        prompt_chars: int,
        outcome: str,
        response_model: Optional[str] = None,
        response_chars: Optional[int] = None,
        error: Optional[BaseException] = None,
        raw_output_artifact: Optional[str] = None,
    ) -> None:
        if logger is None:
            return
        fields: dict[str, Any] = {
            "client": self.name,
            "model": self.model,
            "method": method,
            "attempt": attempt,
            "duration_seconds": (datetime.now() - started).total_seconds(),
            "prompt_chars": prompt_chars,
            "outcome": outcome,
        }
        if response_model is not None:
            fields["response_model"] = response_model
        if response_chars is not None:
            fields["response_chars"] = response_chars
        if error is not None:
            fields["error_type"] = type(error).__name__
            fields["error_message"] = str(error)[:500]
        if raw_output_artifact is not None:
            fields["raw_output_artifact"] = raw_output_artifact
        logger.event("llm_call", **fields)

    @staticmethod
    def _save_bad_output(
        logger: Optional[RunLogger],
        attempt: int,
        response_model: str,
        content: str,
    ) -> Optional[str]:
        if logger is None:
            return None
        return logger.save_artifact(
            f"attempt{attempt}_{response_model}",
            content,
        )

    @staticmethod
    def _with_retry_turn(
        current_messages: list[dict[str, Any]],
        bad_response: str,
        retry_instruction: str,
    ) -> list[dict[str, Any]]:
        return current_messages + [
            {"role": "assistant", "content": bad_response},
            {"role": "user", "content": retry_instruction},
        ]