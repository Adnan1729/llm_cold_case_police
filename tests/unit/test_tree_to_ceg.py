"""Tests for EventTree -> ChainEventGraph conversion via cegpy."""
from __future__ import annotations

import pytest

pytest.importorskip("cegpy")

from consortium.ceg.tree_to_ceg import (
    CegpyConversionReport,
    event_tree_to_ceg,
)
from consortium.ceg.validator import validate_ceg_structure
from consortium.schemas.ceg import CEGNodeType
from consortium.schemas.event_tree import (
    EventTree,
    EventTreeEdge,
    EventTreeNode,
)


def _branching_tree() -> EventTree:
    """5-node tree with two situations sharing branching factor 2:
        N0 has 2 outgoing edges (A, B)
        N1 has 2 outgoing edges (C, D)
        => N0 and N1 are in the same hyperstage class for AHC.
    """
    return EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="path A taken"),
            EventTreeNode(id="N2", description="path B taken (leaf)"),
            EventTreeNode(id="N3", description="A then C (leaf)"),
            EventTreeNode(id="N4", description="A then D (leaf)"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="A", conditional_probability=0.6),
            EventTreeEdge(id="T1", from_node="N0", to_node="N2",
                          event_label="B", conditional_probability=0.4),
            EventTreeEdge(
                id="T2", from_node="N1", to_node="N3",
                event_label="C", conditional_probability=0.7,
                associated_evidence=["E001"],
            ),
            EventTreeEdge(id="T3", from_node="N1", to_node="N4",
                          event_label="D", conditional_probability=0.3),
        ],
        root_node_id="N0",
    )


def _asymmetric_tree() -> EventTree:
    """N0 has 3 outgoing edges, N1 has 2. Each situation in its own
    hyperstage class -> triggers the singleton-class AHC fallback.
    Evidence on edges to verify fallback-path preservation.
    """
    return EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="branch a"),
            EventTreeNode(id="N2", description="leaf b"),
            EventTreeNode(id="N3", description="leaf c"),
            EventTreeNode(id="N4", description="leaf a1"),
            EventTreeNode(id="N5", description="leaf a2"),
        ],
        edges=[
            EventTreeEdge(
                id="T0", from_node="N0", to_node="N1",
                event_label="A", conditional_probability=0.4,
                associated_evidence=["E001"],
            ),
            EventTreeEdge(id="T1", from_node="N0", to_node="N2",
                          event_label="B", conditional_probability=0.3),
            EventTreeEdge(id="T2", from_node="N0", to_node="N3",
                          event_label="C", conditional_probability=0.3),
            EventTreeEdge(
                id="T3", from_node="N1", to_node="N4",
                event_label="A1", conditional_probability=0.5,
                associated_evidence=["E002"],
            ),
            EventTreeEdge(id="T4", from_node="N1", to_node="N5",
                          event_label="A2", conditional_probability=0.5),
        ],
        root_node_id="N0",
    )


def _simple_tree() -> EventTree:
    return EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="l"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="X", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )


# --- Structure tests ---

def test_returns_pydantic_ceg_and_report():
    ceg, report = event_tree_to_ceg(_branching_tree(), pseudo_count=1000)
    assert ceg.case_id == "c1"
    assert ceg.hypothesis_id == "H1"
    assert isinstance(report, CegpyConversionReport)


def test_root_node_is_typed_root():
    ceg, _ = event_tree_to_ceg(_branching_tree(), pseudo_count=1000)
    root = next(n for n in ceg.nodes if n.id == ceg.root_node_id)
    assert root.type == CEGNodeType.ROOT.value


def test_leaf_node_ids_match_terminal_nodes():
    ceg, _ = event_tree_to_ceg(_branching_tree(), pseudo_count=1000)
    leaf_ids_in_nodes = {
        n.id for n in ceg.nodes if n.type == CEGNodeType.LEAF.value
    }
    assert set(ceg.leaf_node_ids) == leaf_ids_in_nodes
    assert len(ceg.leaf_node_ids) >= 1


def test_ceg_passes_structural_validation():
    ceg, _ = event_tree_to_ceg(_branching_tree(), pseudo_count=1000)
    problems = validate_ceg_structure(ceg)
    assert problems == [], f"Validation failed: {problems}"


def test_simple_tree_uses_fallback_path():
    """A single-situation tree has only one situation, so AHC has nothing
    to merge — fallback path should engage and still produce a valid CEG.
    """
    ceg, report = event_tree_to_ceg(_simple_tree(), pseudo_count=100)
    problems = validate_ceg_structure(ceg)
    assert problems == [], f"Validation failed: {problems}"
    assert report.ahc_fallback_triggered is True


def test_asymmetric_tree_uses_fallback_path():
    """Asymmetric branching factors -> singleton hyperstage -> fallback."""
    ceg, report = event_tree_to_ceg(_asymmetric_tree(), pseudo_count=1000)
    problems = validate_ceg_structure(ceg)
    assert problems == [], f"Validation failed: {problems}"
    assert report.ahc_fallback_triggered is True
    assert report.ahc_fallback_reason is not None


# --- Evidence preservation ---

def test_fallback_path_preserves_edge_evidence_one_to_one():
    """Fallback path uses direct conversion; evidence preserved 1:1."""
    ceg, report = event_tree_to_ceg(_asymmetric_tree(), pseudo_count=1000)
    assert report.ahc_fallback_triggered

    edges_by_label = {e.event_label: e for e in ceg.edges}
    assert "A" in edges_by_label
    assert "A1" in edges_by_label
    assert edges_by_label["A"].associated_evidence == ["E001"]
    assert edges_by_label["A1"].associated_evidence == ["E002"]


def test_fallback_path_preserves_edge_labels():
    """Fallback path retains the LLM's specific event labels exactly."""
    ceg, report = event_tree_to_ceg(_asymmetric_tree(), pseudo_count=1000)
    assert report.ahc_fallback_triggered
    labels = {e.event_label for e in ceg.edges}
    assert labels == {"A", "B", "C", "A1", "A2"}


def test_ahc_path_reattaches_specific_labels():
    """AHC path: cegpy sees generic labels (outcome_0, outcome_1) but
    the output CEG should carry the LLM's specific labels reattached
    via the LabelMapping. No outgoing-position edge should retain a
    generic placeholder."""
    ceg, report = event_tree_to_ceg(_branching_tree(), pseudo_count=1000)
    assert report.ahc_fallback_triggered is False
    labels = {e.event_label for e in ceg.edges}

    # No generic placeholders left in the output
    assert not any(lab.startswith("outcome_") for lab in labels)
    # At least one of the original labels survived re-attachment
    assert labels & {"A", "B", "C", "D"}


def test_ahc_path_preserves_edge_evidence():
    """Edge T2 in the branching tree has evidence ['E001'] attached.
    After AHC + re-attachment, the C-labelled edge should carry it."""
    ceg, _ = event_tree_to_ceg(_branching_tree(), pseudo_count=1000)
    c_edges = [e for e in ceg.edges if e.event_label == "C"]
    assert len(c_edges) >= 1
    assert any("E001" in e.associated_evidence for e in c_edges)

# --- Report contents ---

def test_conversion_report_counts_branching_tree():
    tree = _branching_tree()
    _, report = event_tree_to_ceg(tree, pseudo_count=1000)
    assert report.event_tree_node_count == 5
    assert report.event_tree_edge_count == 4
    assert report.event_tree_path_count == 3
    assert report.pseudo_count_budget == 1000
    assert report.pseudo_observation_count > 0
    assert report.cegpy_position_count >= 2


def test_report_normalizations_field_is_list():
    _, report = event_tree_to_ceg(_branching_tree(), pseudo_count=1000)
    assert isinstance(report.normalizations, list)


def test_report_ahc_fallback_fields_present():
    _, report = event_tree_to_ceg(_branching_tree(), pseudo_count=1000)
    assert hasattr(report, "ahc_fallback_triggered")
    assert hasattr(report, "ahc_fallback_reason")