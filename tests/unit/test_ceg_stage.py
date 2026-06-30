"""Tests for the CEG generation stage (event-tree pipeline)."""
from __future__ import annotations

import pytest

pytest.importorskip("cegpy")

from consortium.ceg.event_tree_validator import EventTreeValidationError
from consortium.ceg.validator import validate_ceg_structure
from consortium.clients import MockClient
from consortium.pipeline.ceg_stage import generate_ceg
from consortium.schemas.case import Case, CaseMetadata
from consortium.schemas.event_tree import (
    EventTree,
    EventTreeEdge,
    EventTreeNode,
)
from consortium.schemas.evidence import EvidenceCard, EvidenceType, Reliability
from consortium.schemas.hypothesis import EvidenceSupport, Hypothesis, SupportRole


# --- Fixtures ---

def _case() -> Case:
    return Case(
        metadata=CaseMetadata(case_id="c1", case_name="Test"),
        narrative="A short narrative.",
        evidence=[
            EvidenceCard(
                id="E001",
                type=EvidenceType.WITNESS_STATEMENT,
                title="W", content="content", source="src",
                reliability=Reliability.MEDIUM,
                reliability_note="n", chain_of_custody_note="n",
            ),
        ],
    )


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        id="H1",
        one_line_summary="Summary H1",
        narrative="Narrative H1",
        evidence_support=[
            EvidenceSupport(
                evidence_id="E001",
                role=SupportRole.SUPPORTS,
                weight=0.7,
            ),
        ],
        confidence_score=0.65,
    )


def _valid_tree() -> EventTree:
    """Minimal valid 2-node tree."""
    return EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="start"),
            EventTreeNode(id="N1", description="end"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="event", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )


def _invalid_tree_dangling_edge() -> EventTree:
    """Dangling edge — cannot be auto-repaired."""
    return EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="start"),
            EventTreeNode(id="N1", description="end"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N99",
                          event_label="dangling", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )


# --- Tests ---

def test_generate_ceg_returns_validated_ceg():
    client = MockClient(structured_responses=[_valid_tree()])
    ceg = generate_ceg(_case(), _hypothesis(), client)
    assert ceg.case_id == "c1"
    assert ceg.hypothesis_id == "H1"
    assert validate_ceg_structure(ceg) == []


def test_generate_ceg_calls_llm_with_event_tree_schema():
    client = MockClient(structured_responses=[_valid_tree()])
    generate_ceg(_case(), _hypothesis(), client)
    assert client.call_log[0]["schema"] == "EventTree"


def test_generate_ceg_includes_system_and_user_messages():
    client = MockClient(structured_responses=[_valid_tree()])
    generate_ceg(_case(), _hypothesis(), client)
    roles = [m["role"] for m in client.call_log[0]["messages"]]
    assert roles == ["system", "user"]


def test_generate_ceg_raises_when_invalid_and_no_retries():
    client = MockClient(structured_responses=[_invalid_tree_dangling_edge()])
    with pytest.raises(EventTreeValidationError):
        generate_ceg(
            _case(), _hypothesis(), client, max_structural_retries=0
        )


def test_generate_ceg_skips_validation_when_validate_false():
    """validate=False accepts an otherwise-rejected event tree."""
    # A tree with sums-to-1.0 violation but no dangling edges so the
    # converter doesn't blow up downstream.
    bad_sum_tree = EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="start"),
            EventTreeNode(id="N1", description="end"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="x", conditional_probability=0.5),
        ],
        root_node_id="N0",
    )
    client = MockClient(structured_responses=[bad_sum_tree])
    ceg = generate_ceg(_case(), _hypothesis(), client, validate=False)
    # The conversion's normalization pass should still have produced
    # a structurally valid CEG.
    assert validate_ceg_structure(ceg) == []


def test_generate_ceg_retries_invalid_and_succeeds_on_valid_tree():
    """First call returns invalid tree, retry returns valid; succeeds."""
    client = MockClient(
        structured_responses=[
            _invalid_tree_dangling_edge(),
            _valid_tree(),
        ]
    )
    ceg = generate_ceg(_case(), _hypothesis(), client)
    assert ceg.case_id == "c1"


def test_generate_ceg_raises_after_exhausting_retries():
    client = MockClient(
        structured_responses=[
            _invalid_tree_dangling_edge(),
            _invalid_tree_dangling_edge(),
            _invalid_tree_dangling_edge(),
        ]
    )
    with pytest.raises(EventTreeValidationError, match="3 attempt"):
        generate_ceg(_case(), _hypothesis(), client)


def test_generate_ceg_propagates_evidence_grounding_errors():
    """Tree referencing a non-existent evidence ID is rejected."""
    bad_evidence_tree = EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="start",
                          associated_evidence=["E999"]),
            EventTreeNode(id="N1", description="end"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="x", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )
    client = MockClient(structured_responses=[bad_evidence_tree])
    with pytest.raises(EventTreeValidationError, match="E999"):
        generate_ceg(_case(), _hypothesis(), client, max_structural_retries=0)