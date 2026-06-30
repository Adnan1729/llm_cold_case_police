"""Tests for EventTree -> pandas DataFrame conversion."""
from __future__ import annotations

import pytest

from consortium.ceg.tree_to_dataframe import (
    enumerate_root_to_leaf_paths,
    event_tree_to_dataframe,
)
from consortium.schemas.event_tree import (
    EventTree,
    EventTreeEdge,
    EventTreeNode,
)


# --- Fixtures ---

def _branching_tree() -> EventTree:
    """5-node tree:
        N0 -> N1 (A, 0.7)   N0 -> N2 (B, 0.3)
        N1 -> N3 (C, 0.4)   N1 -> N4 (D, 0.6)
        Paths:
          N0 -> N2          [B],       p=0.30
          N0 -> N1 -> N3    [A, C],    p=0.28
          N0 -> N1 -> N4    [A, D],    p=0.42
    """
    return EventTree(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="l1"),
            EventTreeNode(id="N2", description="l2"),
            EventTreeNode(id="N3", description="l3"),
            EventTreeNode(id="N4", description="l4"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="A", conditional_probability=0.7),
            EventTreeEdge(id="T1", from_node="N0", to_node="N2",
                          event_label="B", conditional_probability=0.3),
            EventTreeEdge(id="T2", from_node="N1", to_node="N3",
                          event_label="C", conditional_probability=0.4),
            EventTreeEdge(id="T3", from_node="N1", to_node="N4",
                          event_label="D", conditional_probability=0.6),
        ],
        root_node_id="N0",
    )


def _single_path_tree() -> EventTree:
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


# --- Path enumeration tests ---

def test_enumerate_paths_branching_tree_finds_all_leaves():
    paths = enumerate_root_to_leaf_paths(_branching_tree())
    assert len(paths) == 3
    assert {p.node_ids[-1] for p in paths} == {"N2", "N3", "N4"}


def test_enumerate_paths_joint_probability_correct():
    paths = enumerate_root_to_leaf_paths(_branching_tree())
    by_leaf = {p.node_ids[-1]: p.joint_probability for p in paths}
    assert by_leaf["N2"] == pytest.approx(0.3)
    assert by_leaf["N3"] == pytest.approx(0.7 * 0.4)
    assert by_leaf["N4"] == pytest.approx(0.7 * 0.6)


def test_enumerate_paths_total_probability_sums_to_one():
    paths = enumerate_root_to_leaf_paths(_branching_tree())
    assert sum(p.joint_probability for p in paths) == pytest.approx(1.0)


def test_enumerate_paths_single_path_tree():
    paths = enumerate_root_to_leaf_paths(_single_path_tree())
    assert len(paths) == 1
    assert paths[0].event_labels == ["X"]
    assert paths[0].joint_probability == 1.0


# --- DataFrame tests ---

def test_dataframe_columns_one_per_depth_level():
    df, _ = event_tree_to_dataframe(_branching_tree(), pseudo_count=100)
    assert list(df.columns) == ["level_0", "level_1"]


def test_dataframe_single_path_has_one_column():
    df, _ = event_tree_to_dataframe(_single_path_tree(), pseudo_count=10)
    assert list(df.columns) == ["level_0"]


def test_dataframe_row_count_approximately_pseudo_count():
    df, _ = event_tree_to_dataframe(_branching_tree(), pseudo_count=1000)
    assert abs(len(df) - 1000) <= 3  # rounding may cause ±1 per path


def test_dataframe_row_distribution_proportional_to_probability():
    df, _ = event_tree_to_dataframe(_branching_tree(), pseudo_count=1000)
    n_b = (df["level_0"] == "B").sum()
    n_a = (df["level_0"] == "A").sum()
    assert abs(n_b - 300) <= 1
    assert abs(n_a - 700) <= 1

    a_then_c = ((df["level_0"] == "A") & (df["level_1"] == "C")).sum()
    a_then_d = ((df["level_0"] == "A") & (df["level_1"] == "D")).sum()
    assert abs(a_then_c - 280) <= 1
    assert abs(a_then_d - 420) <= 1


def test_dataframe_shorter_paths_padded_with_none():
    df, _ = event_tree_to_dataframe(_branching_tree(), pseudo_count=100)
    b_rows = df[df["level_0"] == "B"]
    assert b_rows["level_1"].isna().all()


def test_dataframe_low_probability_path_gets_at_least_one_row():
    tree = EventTree(
        case_id="c", hypothesis_id="H",
        nodes=[
            EventTreeNode(id="N0", description="r"),
            EventTreeNode(id="N1", description="common"),
            EventTreeNode(id="N2", description="rare"),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="A", conditional_probability=0.999),
            EventTreeEdge(id="T1", from_node="N0", to_node="N2",
                          event_label="B", conditional_probability=0.001),
        ],
        root_node_id="N0",
    )
    df, _ = event_tree_to_dataframe(tree, pseudo_count=100)
    # B would round to 0; we guarantee >=1 row
    assert (df["level_0"] == "B").sum() >= 1


def test_invalid_pseudo_count_rejected():
    with pytest.raises(ValueError, match="pseudo_count must be positive"):
        event_tree_to_dataframe(_branching_tree(), pseudo_count=0)
    with pytest.raises(ValueError, match="pseudo_count must be positive"):
        event_tree_to_dataframe(_branching_tree(), pseudo_count=-5)


def test_root_only_tree_raises():
    tree = EventTree(
        case_id="c", hypothesis_id="H",
        nodes=[EventTreeNode(id="N0", description="r")],
        edges=[],
        root_node_id="N0",
    )
    with pytest.raises(ValueError, match="no edges"):
        event_tree_to_dataframe(tree, pseudo_count=100)

def test_generic_labels_mode_produces_outcome_placeholders():
    tree = _branching_tree()
    df, mapping = event_tree_to_dataframe(
        tree, pseudo_count=100, use_generic_labels=True
    )
    assert mapping is not None
    # Level 0 emits outcome_0 and outcome_1 (the two outgoing edges from N0)
    level_0_values = set(df["level_0"].dropna().unique())
    assert level_0_values == {"outcome_0", "outcome_1"}
    # The mapping can recover the original labels
    assert mapping.generic_to_specific[("N0", "outcome_0")] in {"A", "B"}
    assert mapping.generic_to_specific[("N0", "outcome_1")] in {"A", "B"}