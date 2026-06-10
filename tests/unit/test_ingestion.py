"""Tests for the ingestion stage.

These tests use MockClient. The actual prompt quality (does the model
produce good EvidenceCards from raw text?) can only be evaluated against
a live model; that test will live separately once Ollama is up.
"""
from __future__ import annotations

import pytest

from consortium.clients import MockClient
from consortium.pipeline.ingestion import (
    EvidenceExtractionOutput,
    ingest_case_text,
)
from consortium.schemas.evidence import EvidenceCard, EvidenceType, Reliability


def _sample_cards() -> list[EvidenceCard]:
    return [
        EvidenceCard(
            id="E001",
            type=EvidenceType.WITNESS_STATEMENT,
            title="Test witness statement",
            content="A witness reported hearing a disturbance.",
            source="Officer interview, 01/01/2023",
            timestamp_referenced="2023-01-01T22:00:00",
            location_referenced="Test address",
            reliability=Reliability.MEDIUM,
            reliability_note="Adult witness; auditory observation only.",
            chain_of_custody_note="Recorded statement on file.",
        ),
        EvidenceCard(
            id="E002",
            type=EvidenceType.FORENSIC_REPORT,
            title="Test forensic report",
            content="Forensic examination of the scene.",
            source="Forensic services, 02/01/2023",
            timestamp_referenced=None,
            location_referenced="Test scene",
            reliability=Reliability.HIGH,
            reliability_note="Standard forensic methodology by qualified examiner.",
            chain_of_custody_note="Standard chain of custody documented.",
        ),
    ]


def test_ingest_returns_evidence_cards_in_order():
    cards = _sample_cards()
    client = MockClient(
        structured_responses=[EvidenceExtractionOutput(evidence_items=cards)]
    )

    result = ingest_case_text(raw_text="some material", client=client)

    assert len(result) == 2
    assert [c.id for c in result] == ["E001", "E002"]


def test_ingest_calls_client_with_extraction_schema():
    cards = _sample_cards()
    client = MockClient(
        structured_responses=[EvidenceExtractionOutput(evidence_items=cards)]
    )

    ingest_case_text(raw_text="some material", client=client)

    assert len(client.call_log) == 1
    entry = client.call_log[0]
    assert entry["method"] == "chat_structured"
    assert entry["schema"] == "EvidenceExtractionOutput"


def test_ingest_uses_system_and_user_messages():
    cards = _sample_cards()
    client = MockClient(
        structured_responses=[EvidenceExtractionOutput(evidence_items=cards)]
    )

    ingest_case_text(raw_text="some material", client=client)

    roles = [m["role"] for m in client.call_log[0]["messages"]]
    assert roles == ["system", "user"]


def test_ingest_includes_raw_text_in_user_message():
    cards = _sample_cards()
    client = MockClient(
        structured_responses=[EvidenceExtractionOutput(evidence_items=cards)]
    )

    distinctive = "A very distinctive phrase that should appear in the prompt."
    ingest_case_text(raw_text=distinctive, client=client)

    user_content = next(
        m["content"]
        for m in client.call_log[0]["messages"]
        if m["role"] == "user"
    )
    assert distinctive in user_content


def test_ingest_uses_low_temperature_by_default():
    cards = _sample_cards()
    client = MockClient(
        structured_responses=[EvidenceExtractionOutput(evidence_items=cards)]
    )

    ingest_case_text(raw_text="x", client=client)

    assert client.call_log[0]["temperature"] == 0.1


def test_ingest_propagates_validation_errors():
    """If the mock returns the wrong type, ingest_case_text should raise."""

    class _Wrong:
        pass

    client = MockClient(structured_responses=[_Wrong()])  # type: ignore[list-item]
    with pytest.raises(TypeError):
        ingest_case_text(raw_text="x", client=client)