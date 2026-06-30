"""Tests for event tree repair operations."""
from __future__ import annotations

import pytest

from consortium.ceg.event_tree_repair import (
    EventTreeRepairReport,
    repair_event_tree,
)
from consortium.ceg.event_tree_validator import validate_event_tree_structure
from consortium.schemas.event_tree import (
    EventTree,
    EventTreeEdge,
    EventTreeNode,
)


def test_valid_tree_unchanged():
    tree = EventTree(
        case_id="c", hypothesis_id="H",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="l"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="x", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )
    repaired, report = repair_event_tree(tree)
    assert report.is_empty()
    assert validate_event_tree_structure(repaired) == []


def test_orphan_node_dropped():
    tree = EventTree(
        case_id="c", hypothesis_id="H",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="reachable"),
            EventTreeNode(id="N2", description="orphan"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="a", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )
    repaired, report = repair_event_tree(tree)
    assert "N2" in report.orphans_dropped
    assert {n.id for n in repaired.nodes} == {"N0", "N1"}


def test_orphan_with_outgoing_edges_dropped_completely():
    tree = EventTree(
        case_id="c", hypothesis_id="H",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="reachable"),
            EventTreeNode(id="N2", description="orphan"),
            EventTreeNode(id="N3", description="orphan child"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="a", conditional_probability=1.0),
            EventTreeEdge(id="T1", from_node="N2", to_node="N3",
                          event_label="b", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )
    repaired, report = repair_event_tree(tree)
    assert set(report.orphans_dropped) == {"N2", "N3"}
    assert "T1" in report.edges_dropped_with_orphans


def test_dag_node_with_two_parents_expanded():
    """N3 has parents N1 and N2. After repair it's duplicated."""
    tree = EventTree(
        case_id="c", hypothesis_id="H",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="a"),
            EventTreeNode(id="N2", description="b"),
            EventTreeNode(id="N3", description="shared", associated_evidence=["E001"]),
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
    repaired, report = repair_event_tree(tree)
    # N3 should appear in duplicated_nodes with 2 new copies
    assert "N3" in report.duplicated_nodes
    assert len(report.duplicated_nodes["N3"]) == 2
    # The repaired tree should pass validation
    assert validate_event_tree_structure(repaired) == []
    # Evidence preserved in both copies
    n3_copies = [
        n for n in repaired.nodes if n.description == "shared"
    ]
    assert len(n3_copies) == 2
    for copy in n3_copies:
        assert copy.associated_evidence == ["E001"]


def test_probability_sums_normalized():
    tree = EventTree(
        case_id="c", hypothesis_id="H",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="a"),
            EventTreeNode(id="N2", description="b"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="a", conditional_probability=0.6),
            EventTreeEdge(id="T1", from_node="N0", to_node="N2",
                          event_label="b", conditional_probability=0.2),
        ],
        root_node_id="N0",
    )
    repaired, report = repair_event_tree(tree)
    assert len(report.probability_normalizations) == 1
    assert report.probability_normalizations[0]["node_id"] == "N0"
    new_total = sum(
        e.conditional_probability for e in repaired.edges
        if e.from_node == repaired.root_node_id
    )
    assert abs(new_total - 1.0) < 1e-4


def test_all_three_repairs_applied_together():
    """A pathological output combining orphans + DAG + bad probs."""
    tree = EventTree(
        case_id="c", hypothesis_id="H",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="reachable a"),
            EventTreeNode(id="N2", description="reachable b"),
            EventTreeNode(id="N3", description="shared"),
            EventTreeNode(id="N4", description="orphan"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="a", conditional_probability=0.4),
            EventTreeEdge(id="T1", from_node="N0", to_node="N2",
                          event_label="b", conditional_probability=0.3),
            EventTreeEdge(id="T2", from_node="N1", to_node="N3",
                          event_label="c", conditional_probability=1.0),
            EventTreeEdge(id="T3", from_node="N2", to_node="N3",
                          event_label="d", conditional_probability=1.0),
        ],
        root_node_id="N0",
    )
    repaired, report = repair_event_tree(tree)
    # orphan dropped
    assert "N4" in report.orphans_dropped
    # N3 duplicated
    assert "N3" in report.duplicated_nodes
    # N0 outgoing probabilities normalised (was 0.7)
    assert any(
        n["node_id"] in (report.duplicated_nodes.get("N0", ["N0"])[0], "N0")
        for n in report.probability_normalizations
    )
    # Final tree valid
    assert validate_event_tree_structure(repaired) == []


def test_expansion_safety_cap_skips_when_too_large():
    """If expansion would blow up, repair skips it and notes why."""
    # Construct a tree where each node has 2 children and N3 has 2 parents
    # — small enough not to actually trigger, just confirm the flag exists.
    tree = EventTree(
        case_id="c", hypothesis_id="H",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="a"),
            EventTreeNode(id="N2", description="b"),
            EventTreeNode(id="N3", description="shared"),
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
    # Cap at 3 (less than what expansion needs); should skip.
    repaired, report = repair_event_tree(tree, max_expanded_nodes=3)
    assert report.expansion_skipped_reason is not None
    assert "N3" not in report.duplicated_nodes