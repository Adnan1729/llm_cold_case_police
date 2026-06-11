"""Tests for CEG probability normalization."""
from __future__ import annotations

import pytest

from consortium.ceg.repair import normalize_outgoing_probabilities
from consortium.schemas.ceg import (
    CEGEdge,
    CEGNode,
    CEGNodeType,
    ChainEventGraph,
)


def _ceg(nodes, edges):
    leaves = [n.id for n in nodes if n.type == CEGNodeType.LEAF.value]
    return ChainEventGraph(
        case_id="c", hypothesis_id="H",
        nodes=nodes, edges=edges, stages=[],
        root_node_id=nodes[0].id,
        leaf_node_ids=leaves or [nodes[-1].id],
    )


def test_already_normalized_unchanged():
    ceg = _ceg(
        [
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="r"),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="l1"),
            CEGNode(id="N2", type=CEGNodeType.LEAF, description="l2"),
        ],
        [
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="e", conditional_probability=0.6),
            CEGEdge(id="T1", from_node="N0", to_node="N2",
                    event_label="e", conditional_probability=0.4),
        ],
    )
    new_ceg, report = normalize_outgoing_probabilities(ceg)
    assert report.is_empty()
    assert new_ceg.edges[0].conditional_probability == 0.6


def test_under_one_normalized_up():
    ceg = _ceg(
        [
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="r"),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="l"),
        ],
        [
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="e", conditional_probability=0.4),
        ],
    )
    new_ceg, report = normalize_outgoing_probabilities(ceg)
    assert len(report.normalizations) == 1
    assert report.normalizations[0].node_id == "N0"
    assert report.normalizations[0].original_sum == 0.4
    assert new_ceg.edges[0].conditional_probability == pytest.approx(1.0)


def test_over_one_normalized_down():
    ceg = _ceg(
        [
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="r"),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="l1"),
            CEGNode(id="N2", type=CEGNodeType.LEAF, description="l2"),
        ],
        [
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="e", conditional_probability=1.0),
            CEGEdge(id="T1", from_node="N0", to_node="N2",
                    event_label="e", conditional_probability=1.0),
        ],
    )
    new_ceg, report = normalize_outgoing_probabilities(ceg)
    assert report.normalizations[0].original_sum == 2.0
    assert new_ceg.edges[0].conditional_probability == pytest.approx(0.5)
    assert new_ceg.edges[1].conditional_probability == pytest.approx(0.5)


def test_zero_sum_unchanged():
    ceg = _ceg(
        [
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="r"),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="l"),
        ],
        [
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="e", conditional_probability=0.0),
        ],
    )
    new_ceg, report = normalize_outgoing_probabilities(ceg)
    assert report.is_empty()
    assert new_ceg.edges[0].conditional_probability == 0.0

def test_multiple_nodes_normalized_independently():
    ceg = _ceg(
        [
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="r"),
            CEGNode(id="N1", type=CEGNodeType.SITUATION, description="s"),
            CEGNode(id="N2", type=CEGNodeType.LEAF, description="l1"),
            CEGNode(id="N3", type=CEGNodeType.LEAF, description="l2"),
        ],
        [
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="e", conditional_probability=0.5),
            CEGEdge(id="T1", from_node="N1", to_node="N2",
                    event_label="e", conditional_probability=0.8),
            CEGEdge(id="T2", from_node="N1", to_node="N3",
                    event_label="e", conditional_probability=0.4),
        ],
    )
    new_ceg, report = normalize_outgoing_probabilities(ceg)
    assert len(report.normalizations) == 2

    # N0: outgoing sums to 0.5 -> scaled to 1.0
    t0 = next(e for e in new_ceg.edges if e.id == "T0")
    assert t0.conditional_probability == pytest.approx(1.0)

    # N1: outgoing sums to 1.2 -> scaled to 1.0
    t1 = next(e for e in new_ceg.edges if e.id == "T1")
    t2 = next(e for e in new_ceg.edges if e.id == "T2")
    assert t1.conditional_probability == pytest.approx(0.8 / 1.2)
    assert t2.conditional_probability == pytest.approx(0.4 / 1.2)


def test_returns_same_ceg_object_when_nothing_to_repair():
    ceg = _ceg(
        [
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="r"),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="l"),
        ],
        [
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="e", conditional_probability=1.0),
        ],
    )
    new_ceg, report = normalize_outgoing_probabilities(ceg)
    assert report.is_empty()
    assert new_ceg is ceg