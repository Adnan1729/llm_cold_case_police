"""Tests for CEG structural and grounding validators."""
from __future__ import annotations

import pytest

from consortium.ceg.validator import (
    CEGValidationError,
    assert_ceg_valid,
    validate_ceg_evidence_grounding,
    validate_ceg_structure,
)
from consortium.schemas.case import Case, CaseMetadata
from consortium.schemas.ceg import (
    CEGEdge,
    CEGNode,
    CEGNodeType,
    CEGStage,
    ChainEventGraph,
)
from consortium.schemas.evidence import EvidenceCard, EvidenceType, Reliability


def _minimal_valid_ceg() -> ChainEventGraph:
    return ChainEventGraph(
        case_id="c1",
        hypothesis_id="H1",
        nodes=[
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="start"),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="end"),
        ],
        edges=[
            CEGEdge(
                id="T0", from_node="N0", to_node="N1",
                event_label="event", conditional_probability=1.0,
            ),
        ],
        stages=[
            CEGStage(id="S0", member_nodes=["N0"]),
            CEGStage(id="S1", member_nodes=["N1"]),
        ],
        root_node_id="N0",
        leaf_node_ids=["N1"],
    )


def _case_with_one_piece_of_evidence() -> Case:
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


def test_minimal_ceg_is_valid():
    assert validate_ceg_structure(_minimal_valid_ceg()) == []


def test_missing_root_node_detected():
    ceg = _minimal_valid_ceg()
    ceg.root_node_id = "N99"
    problems = validate_ceg_structure(ceg)
    assert any("root_node_id" in p for p in problems)


def test_leaf_with_wrong_type_detected():
    ceg = _minimal_valid_ceg()
    ceg.nodes[1].type = CEGNodeType.SITUATION.value
    # Need outgoing edge sums to fix at the same time — N1 now non-leaf with
    # no outgoing. Two problems expected.
    problems = validate_ceg_structure(ceg)
    assert any("not of type 'leaf'" in p for p in problems)


def test_dangling_edge_detected():
    ceg = _minimal_valid_ceg()
    ceg.edges.append(
        CEGEdge(
            id="T1", from_node="N0", to_node="N99",
            event_label="dangling", conditional_probability=0.0,
        )
    )
    problems = validate_ceg_structure(ceg)
    assert any("N99" in p for p in problems)


def test_cycle_detected():
    ceg = ChainEventGraph(
        case_id="c", hypothesis_id="H",
        nodes=[
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="r"),
            CEGNode(id="N1", type=CEGNodeType.SITUATION, description="mid"),
            CEGNode(id="N2", type=CEGNodeType.LEAF, description="l"),
        ],
        edges=[
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="a", conditional_probability=1.0),
            CEGEdge(id="T1", from_node="N1", to_node="N0",
                    event_label="back", conditional_probability=0.5),
            CEGEdge(id="T2", from_node="N1", to_node="N2",
                    event_label="forward", conditional_probability=0.5),
        ],
        stages=[],
        root_node_id="N0",
        leaf_node_ids=["N2"],
    )
    assert any("cycle" in p for p in validate_ceg_structure(ceg))


def test_probability_sum_violation_detected():
    ceg = ChainEventGraph(
        case_id="c", hypothesis_id="H",
        nodes=[
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="r"),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="a"),
            CEGNode(id="N2", type=CEGNodeType.LEAF, description="b"),
        ],
        edges=[
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="x", conditional_probability=0.6),
            CEGEdge(id="T1", from_node="N0", to_node="N2",
                    event_label="y", conditional_probability=0.5),
        ],
        stages=[],
        root_node_id="N0",
        leaf_node_ids=["N1", "N2"],
    )
    problems = validate_ceg_structure(ceg)
    assert any("sum to" in p for p in problems)


def test_probability_tolerance_respected():
    ceg = ChainEventGraph(
        case_id="c", hypothesis_id="H",
        nodes=[
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="r"),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="a"),
            CEGNode(id="N2", type=CEGNodeType.LEAF, description="b"),
        ],
        edges=[
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="x", conditional_probability=0.5001),
            CEGEdge(id="T1", from_node="N0", to_node="N2",
                    event_label="y", conditional_probability=0.4999),
        ],
        stages=[],
        root_node_id="N0",
        leaf_node_ids=["N1", "N2"],
    )
    assert validate_ceg_structure(ceg, probability_tolerance=1e-3) == []


def test_leaf_with_outgoing_edge_detected():
    ceg = _minimal_valid_ceg()
    # Add a phantom outgoing edge from the leaf
    ceg.edges.append(
        CEGEdge(
            id="T1", from_node="N1", to_node="N0",
            event_label="bad", conditional_probability=1.0,
        )
    )
    problems = validate_ceg_structure(ceg)
    assert any("leaf node 'N1' has" in p for p in problems)


def test_evidence_grounding_passes_for_known_ids():
    case = _case_with_one_piece_of_evidence()
    ceg = _minimal_valid_ceg()
    ceg.nodes[0].associated_evidence = ["E001"]
    assert validate_ceg_evidence_grounding(ceg, case) == []


def test_evidence_grounding_detects_unknown_id():
    case = _case_with_one_piece_of_evidence()
    ceg = _minimal_valid_ceg()
    ceg.nodes[0].associated_evidence = ["E999"]
    problems = validate_ceg_evidence_grounding(ceg, case)
    assert any("E999" in p for p in problems)


def test_assert_ceg_valid_raises_with_summary():
    ceg = _minimal_valid_ceg()
    ceg.root_node_id = "N99"
    with pytest.raises(CEGValidationError, match="N99"):
        assert_ceg_valid(ceg)


def test_assert_ceg_valid_passes_for_clean_ceg():
    assert_ceg_valid(_minimal_valid_ceg())