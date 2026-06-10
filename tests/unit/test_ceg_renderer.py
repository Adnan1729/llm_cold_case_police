"""Tests for the CEG → DOT renderer."""
from __future__ import annotations

from pathlib import Path

from consortium.ceg.renderer import ceg_to_dot, write_ceg_dot
from consortium.schemas.ceg import (
    CEGEdge,
    CEGNode,
    CEGNodeType,
    ChainEventGraph,
)


def _ceg() -> ChainEventGraph:
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
        stages=[],
        root_node_id="N0",
        leaf_node_ids=["N1"],
    )


def test_dot_output_is_well_formed():
    dot = ceg_to_dot(_ceg())
    assert dot.startswith("digraph")
    assert dot.rstrip().endswith("}")


def test_dot_output_includes_all_nodes_and_edge():
    dot = ceg_to_dot(_ceg())
    assert '"N0"' in dot
    assert '"N1"' in dot
    assert '"N0" -> "N1"' in dot


def test_dot_output_includes_probability():
    dot = ceg_to_dot(_ceg())
    assert "p=1.00" in dot


def test_dot_escapes_quotes_in_labels():
    ceg = ChainEventGraph(
        case_id="c", hypothesis_id="H",
        nodes=[
            CEGNode(id="N0", type=CEGNodeType.ROOT, description='says "hi"'),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="end"),
        ],
        edges=[
            CEGEdge(
                id="T0", from_node="N0", to_node="N1",
                event_label='has "quotes"', conditional_probability=1.0,
            ),
        ],
        stages=[],
        root_node_id="N0",
        leaf_node_ids=["N1"],
    )
    dot = ceg_to_dot(ceg)
    assert '\\"hi\\"' in dot
    assert '\\"quotes\\"' in dot


def test_write_dot_creates_file(tmp_path: Path):
    out = tmp_path / "ceg.dot"
    result = write_ceg_dot(_ceg(), out)
    assert result == out
    assert out.exists()
    content = out.read_text()
    assert "digraph" in content