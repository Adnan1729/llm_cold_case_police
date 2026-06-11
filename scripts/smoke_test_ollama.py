"""Manual smoke test for the Ollama integration.

Verifies that:
1. Ollama is reachable at localhost:11434.
2. Our OllamaClient can do free-text chat.
3. Our OllamaClient can do structured output and validate it.

Run before invoking the full pipeline to catch setup issues fast.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from consortium.clients import OllamaClient
from consortium.clients.base import Message


class _Greeting(BaseModel):
    greeting: str = Field(description="A friendly greeting")
    language: str = Field(description="The language of the greeting, e.g. English")


def main() -> None:
    model = "llama3.2:3b"
    client = OllamaClient(model=model)

    print(f"Connecting to Ollama at {client.host} with model {model}...")

    print("\n[1/2] Free-text chat test")
    response = client.chat(
        [
            Message(role="system", content="You are terse."),
            Message(role="user", content="Reply with exactly: hello world."),
        ],
        temperature=0.0,
        max_tokens=20,
    )
    print(f"  -> {response!r}")

    print("\n[2/2] Structured chat test")
    result = client.chat_structured(
        [
            Message(
                role="user",
                content=(
                    "Produce a JSON object with a friendly greeting in English. "
                    "The greeting must be in the 'greeting' field; the language "
                    "must be in the 'language' field."
                ),
            ),
        ],
        response_model=_Greeting,
        temperature=0.0,
        max_tokens=100,
    )
    print(f"  -> {result.model_dump()}")

    print("\nAll OK.")


if __name__ == "__main__":
    main()