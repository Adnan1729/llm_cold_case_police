"""Tests for EventTree schema-level (field) validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from consortium.schemas.event_tree import (
    EventTree,
    EventTreeEdge,
    EventTreeNode,
)


def test_minimal_event_tree_loads():
    tree = EventTree(
        case_id="c1",
        hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="root"),
            EventTreeNode(id="N1", description="leaf"),
        ],
        edges=[
            EventTreeEdge(
                id="T0", from_node="N0", to_node="N1",
                event_label="event", conditional_probability=1.0,
            ),
        ],
        root_node_id="N0",
    )
    assert tree.case_id == "c1"
    assert tree.hypothesis_id == "H1"
    assert len(tree.nodes) == 2
    assert len(tree.edges) == 1


def test_event_tree_rejects_extra_fields():
    with pytest.raises(ValidationError):
        EventTree(
            case_id="c1",
            hypothesis_id="H1",
            nodes=[],
            edges=[],
            root_node_id="N0",
            unknown_field="foo",
        )


def test_edge_probability_out_of_range_rejected():
    with pytest.raises(ValidationError):
        EventTreeEdge(
            id="T0", from_node="N0", to_node="N1",
            event_label="x", conditional_probability=1.5,
        )
    with pytest.raises(ValidationError):
        EventTreeEdge(
            id="T0", from_node="N0", to_node="N1",
            event_label="x", conditional_probability=-0.1,
        )


def test_edge_probability_boundary_values_allowed():
    e_zero = EventTreeEdge(
        id="T0", from_node="N0", to_node="N1",
        event_label="x", conditional_probability=0.0,
    )
    e_one = EventTreeEdge(
        id="T1", from_node="N0", to_node="N1",
        event_label="y", conditional_probability=1.0,
    )
    assert e_zero.conditional_probability == 0.0
    assert e_one.conditional_probability == 1.0


def test_node_associated_evidence_defaults_empty():
    node = EventTreeNode(id="N0", description="x")
    assert node.associated_evidence == []


def test_node_rejects_extra_fields():
    with pytest.raises(ValidationError):
        EventTreeNode(id="N0", description="x", extra_field="bad")