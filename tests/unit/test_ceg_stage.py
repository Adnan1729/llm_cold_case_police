"""Tests for the CEG generation stage."""
from __future__ import annotations

import pytest

from consortium.ceg.validator import CEGValidationError
from consortium.clients import MockClient
from consortium.pipeline.ceg_stage import generate_ceg
from consortium.schemas.case import Case, CaseMetadata
from consortium.schemas.ceg import (
    CEGEdge,
    CEGNode,
    CEGNodeType,
    ChainEventGraph,
)
from consortium.schemas.evidence import EvidenceCard, EvidenceType, Reliability
from consortium.schemas.hypothesis import EvidenceSupport, Hypothesis, SupportRole


def _case() -> Case:
    return Case(
        metadata=CaseMetadata(case_id="c1", case_name="Test"),
        narrative="A short narrative.",
        evidence=[
            EvidenceCard(
                id="E001",
                type=EvidenceType.WITNESS_STATEMENT,
                title="W",
                content="content",
                source="src",
                reliability=Reliability.MEDIUM,
                reliability_note="n",
                chain_of_custody_note="n",
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


def _valid_ceg() -> ChainEventGraph:
    return ChainEventGraph(
        case_id="c1",
        hypothesis_id="H1",
        nodes=[
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="start"),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="end"),
        ],
        edges=[
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="event", conditional_probability=1.0),
        ],
        stages=[],
        root_node_id="N0",
        leaf_node_ids=["N1"],
    )


def _invalid_ceg() -> ChainEventGraph:
    """Probability sum violation."""
    return ChainEventGraph(
        case_id="c1",
        hypothesis_id="H1",
        nodes=[
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="start"),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="end"),
        ],
        edges=[
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="event", conditional_probability=0.5),
        ],
        stages=[],
        root_node_id="N0",
        leaf_node_ids=["N1"],
    )


def test_generate_ceg_returns_validated_ceg():
    client = MockClient(structured_responses=[_valid_ceg()])
    result = generate_ceg(_case(), _hypothesis(), client)
    assert result.case_id == "c1"
    assert result.hypothesis_id == "H1"


def test_generate_ceg_calls_llm_with_chain_event_graph_schema():
    client = MockClient(structured_responses=[_valid_ceg()])
    generate_ceg(_case(), _hypothesis(), client)
    assert client.call_log[0]["schema"] == "ChainEventGraph"


def test_generate_ceg_includes_system_and_user_messages():
    client = MockClient(structured_responses=[_valid_ceg()])
    generate_ceg(_case(), _hypothesis(), client)
    roles = [m["role"] for m in client.call_log[0]["messages"]]
    assert roles == ["system", "user"]


def test_generate_ceg_raises_when_invalid_and_validate_true():
    """With retries disabled, an invalid CEG raises immediately."""
    client = MockClient(structured_responses=[_invalid_ceg()])
    with pytest.raises(CEGValidationError):
        generate_ceg(
            _case(), _hypothesis(), client, max_structural_retries=0
        )


def test_generate_ceg_skips_validation_when_validate_false():
    """Skipping validation accepts any CEG, including structurally invalid ones."""
    client = MockClient(structured_responses=[_invalid_ceg()])
    result = generate_ceg(
        _case(), _hypothesis(), client, validate=False
    )
    assert result.case_id == "c1"


def test_generate_ceg_retries_structural_failure_and_succeeds_on_valid():
    """First call returns invalid CEG, retry returns valid; generate_ceg succeeds."""
    client = MockClient(
        structured_responses=[_invalid_ceg(), _valid_ceg()]
    )
    result = generate_ceg(_case(), _hypothesis(), client)
    assert result.case_id == "c1"


def test_generate_ceg_raises_after_exhausting_structural_retries():
    """If all retries return invalid CEGs, the final CEGValidationError is raised."""
    client = MockClient(
        structured_responses=[_invalid_ceg(), _invalid_ceg(), _invalid_ceg()]
    )
    with pytest.raises(CEGValidationError, match="3 attempt"):
        generate_ceg(_case(), _hypothesis(), client)