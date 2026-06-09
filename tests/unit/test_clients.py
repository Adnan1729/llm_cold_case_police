"""Tests for the LLM client interface and the mock implementation."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from consortium.clients import Message, MockClient


class _DummySchema(BaseModel):
    foo: str
    n: int


def test_mock_chat_returns_queued_responses_in_order():
    client = MockClient(responses=["one", "two"])
    assert client.chat([Message(role="user", content="hi")]) == "one"
    assert client.chat([Message(role="user", content="hi")]) == "two"


def test_mock_chat_returns_placeholder_when_queue_empty():
    client = MockClient()
    response = client.chat([Message(role="user", content="hi")])
    assert "MOCK_RESPONSE" in response


def test_mock_chat_structured_returns_queued_model():
    queued = _DummySchema(foo="bar", n=1)
    client = MockClient(structured_responses=[queued])
    result = client.chat_structured(
        [Message(role="user", content="hi")],
        response_model=_DummySchema,
    )
    assert result == queued


def test_mock_chat_structured_rejects_wrong_type():
    class _Other(BaseModel):
        x: str

    client = MockClient(structured_responses=[_Other(x="y")])
    with pytest.raises(TypeError):
        client.chat_structured(
            [Message(role="user", content="hi")],
            response_model=_DummySchema,
        )


def test_mock_chat_structured_raises_when_no_queued_response():
    client = MockClient()
    with pytest.raises(NotImplementedError):
        client.chat_structured(
            [Message(role="user", content="hi")],
            response_model=_DummySchema,
        )


def test_mock_records_calls_with_metadata():
    client = MockClient(responses=["a"])
    client.chat(
        [Message(role="user", content="test")],
        temperature=0.7,
        max_tokens=100,
    )
    assert len(client.call_log) == 1
    entry = client.call_log[0]
    assert entry["method"] == "chat"
    assert entry["temperature"] == 0.7
    assert entry["max_tokens"] == 100
    assert entry["messages"][0]["content"] == "test"