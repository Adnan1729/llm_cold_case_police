"""Tests for EventTree structural and grounding validators."""
from __future__ import annotations

import pytest

from consortium.ceg.event_tree_validator import (
    EventTreeValidationError,
    assert_event_tree_valid,
    validate_event_tree_evidence_grounding,
    validate_event_tree_structure,
)
from consortium.schemas.case import Case, CaseMetadata
from consortium.schemas.event_tree import (
    EventTree,
    EventTreeEdge,
    EventTreeNode,
)
from consortium.schemas.evidence import EvidenceCard, EvidenceType, Reliability


# --- Fixtures ---

def _minimal_valid_tree() -> EventTree:
    """Two-node tree: root -> leaf, edge prob 1.0."""
    return EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="start"),
            EventTreeNode(id="N1", description="end"),
        ],
        edges=[
            EventTreeEdge(
                id="T0", from_node="N0", to_node="N1",
                event_label="event", conditional_probability=1.0,
            ),
        ],
        root_node_id="N0",
    )


def _branching_tree() -> EventTree:
    """Five-node tree:
        N0 -> N1 (0.6), N0 -> N2 (0.4)
        N1 -> N3 (0.7), N1 -> N4 (0.3)
        (N2, N3, N4 are leaves)
    """
    return EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="root"),
            EventTreeNode(id="N1", description="left branch"),
            EventTreeNode(id="N2", description="right leaf"),
            EventTreeNode(id="N3", description="left-left leaf"),
            EventTreeNode(id="N4", description="left-right leaf"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="a", conditional_probability=0.6),
            EventTreeEdge(id="T1", from_node="N0", to_node="N2",
                          event_label="b", conditional_probability=0.4),
            EventTreeEdge(id="T2", from_node="N1", to_node="N3",
                          event_label="c", conditional_probability=0.7),
            EventTreeEdge(id="T3", from_node="N1", to_node="N4",
                          event_label="d", conditional_probability=0.3),
        ],
        root_node_id="N0",
    )


def _case_with_evidence() -> Case:
    return Case(
        metadata=CaseMetadata(case_id="c1", case_name="Test"),
        narrative="N",
        evidence=[
            EvidenceCard(
                id="E001",
                type=EvidenceType.WITNESS_STATEMENT,
                title="W", content="c", source="s",
                reliability=Reliability.MEDIUM,
                reliability_note="n", chain_of_custody_note="n",
            ),
        ],
    )


# --- Structural validation tests ---

def test_minimal_valid_tree_passes():
    assert validate_event_tree_structure(_minimal_valid_tree()) == []


def test_branching_tree_passes():
    assert validate_event_tree_structure(_branching_tree()) == []


def test_missing_root_node_detected():
    tree = _minimal_valid_tree()
    tree.root_node_id = "N99"
    problems = validate_event_tree_structure(tree)
    assert any("root_node_id" in p for p in problems)


def test_root_with_incoming_edge_detected():
    tree = EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="l"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="x", conditional_probability=0.5),
            EventTreeEdge(id="T1", from_node="N1", to_node="N0",
                          event_label="back", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )
    problems = validate_event_tree_structure(tree)
    assert any("root node 'N0' has" in p for p in problems)


def test_node_with_multiple_parents_detected():
    """A DAG-but-not-tree: N3 has two parents (N1 and N2)."""
    tree = EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="m1"),
            EventTreeNode(id="N2", description="m2"),
            EventTreeNode(id="N3", description="merged"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="a", conditional_probability=0.5),
            EventTreeEdge(id="T1", from_node="N0", to_node="N2",
                          event_label="b", conditional_probability=0.5),
            EventTreeEdge(id="T2", from_node="N1", to_node="N3",
                          event_label="c", conditional_probability=1.0),
            EventTreeEdge(id="T3", from_node="N2", to_node="N3",
                          event_label="d", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )
    problems = validate_event_tree_structure(tree)
    assert any("N3" in p and "2 incoming" in p for p in problems)


def test_orphaned_node_detected():
    """N2 has no incoming edge and is not the root."""
    tree = EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="l"),
            EventTreeNode(id="N2", description="orphan"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="x", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )
    problems = validate_event_tree_structure(tree)
    assert any("N2" in p and "no incoming" in p for p in problems)


def test_dangling_edge_detected():
    tree = _minimal_valid_tree()
    tree.edges.append(
        EventTreeEdge(id="T1", from_node="N0", to_node="N99",
                      event_label="dangling", conditional_probability=0.0)
    )
    problems = validate_event_tree_structure(tree)
    assert any("N99" in p for p in problems)


def test_cycle_detected():
    """N0 -> N1 -> N2 -> N1 forms a cycle on N1<->N2."""
    tree = EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="m"),
            EventTreeNode(id="N2", description="l"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="a", conditional_probability=1.0),
            EventTreeEdge(id="T1", from_node="N1", to_node="N2",
                          event_label="b", conditional_probability=1.0),
            EventTreeEdge(id="T2", from_node="N2", to_node="N1",
                          event_label="back", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )
    problems = validate_event_tree_structure(tree)
    assert any("cycle" in p for p in problems)


def test_probability_sum_violation_detected():
    tree = EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="l1"),
            EventTreeNode(id="N2", description="l2"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="x", conditional_probability=0.6),
            EventTreeEdge(id="T1", from_node="N0", to_node="N2",
                          event_label="y", conditional_probability=0.3),
        ],
        root_node_id="N0",
    )
    problems = validate_event_tree_structure(tree)
    assert any("sum to" in p for p in problems)


def test_probability_tolerance_respected():
    tree = EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="l1"),
            EventTreeNode(id="N2", description="l2"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="x", conditional_probability=0.5001),
            EventTreeEdge(id="T1", from_node="N0", to_node="N2",
                          event_label="y", conditional_probability=0.4999),
        ],
        root_node_id="N0",
    )
    assert validate_event_tree_structure(tree, probability_tolerance=1e-3) == []


# --- Grounding validation tests ---

def test_evidence_grounding_passes_for_known_ids():
    case = _case_with_evidence()
    tree = _minimal_valid_tree()
    tree.nodes[0].associated_evidence = ["E001"]
    assert validate_event_tree_evidence_grounding(tree, case) == []


def test_evidence_grounding_detects_unknown_id():
    case = _case_with_evidence()
    tree = _minimal_valid_tree()
    tree.nodes[0].associated_evidence = ["E999"]
    problems = validate_event_tree_evidence_grounding(tree, case)
    assert any("E999" in p for p in problems)


# --- assert_event_tree_valid wrapper tests ---

def test_assert_event_tree_valid_raises_with_summary():
    tree = _minimal_valid_tree()
    tree.root_node_id = "N99"
    with pytest.raises(EventTreeValidationError, match="N99"):
        assert_event_tree_valid(tree)


def test_assert_event_tree_valid_passes_for_clean_tree():
    assert_event_tree_valid(_minimal_valid_tree())


def test_assert_event_tree_valid_includes_grounding_when_case_provided():
    case = _case_with_evidence()
    tree = _minimal_valid_tree()
    tree.nodes[0].associated_evidence = ["E999"]
    with pytest.raises(EventTreeValidationError, match="E999"):
        assert_event_tree_valid(tree, case)