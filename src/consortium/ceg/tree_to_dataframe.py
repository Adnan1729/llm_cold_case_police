"""Convert an EventTree into a pandas DataFrame for cegpy consumption.

cegpy is built to learn CEG structure from observed data: its input is
a DataFrame where each row is one observation and each column is one
variable (or, for our purposes, one level of the event tree). The
DataFrame is the input to cegpy's EventTree / StagedTree classes.

Our LLM produces probabilities, not observations. We bridge by expanding
those probabilities into pseudo-counts: for each root-to-leaf path in
the event tree, we compute the joint probability of the path and
generate roughly `pseudo_count * joint_probability` rows containing the
event labels along that path. Shorter paths leave the trailing columns
as None (non-stratified event tree, which cegpy supports).

Two label modes are supported:

- **Specific labels** (default): the dataframe contains the LLM's
  actual event labels (e.g. "Calum leaves the location"). Useful for
  inspection and audit logging.

- **Generic labels** (`use_generic_labels=True`): the dataframe contains
  positional placeholders (e.g. "outcome_0", "outcome_1") indicating
  which branch was taken at each tree depth. Required for cegpy's AHC:
  cegpy partitions situations by their outgoing-event label set, and
  with all-distinct LLM labels every situation lands in its own
  singleton class with nothing to merge. Generic labels group
  situations by branching factor, giving AHC something to work on.

When using generic labels, also returns the bidirectional mapping
between generic and specific labels so the LLM's narrative content can
be re-attached after AHC runs.

The pseudo_count budget controls how confident cegpy's AHC will be in
the LLM's probabilities: higher -> less aggressive merging, lower ->
more aggressive merging. Every root-to-leaf path gets at least one row
so the full tree structure is preserved when probabilities are extreme.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from consortium.schemas.event_tree import EventTree, EventTreeEdge


@dataclass
class TreePath:
    """One root-to-leaf path through the event tree."""

    node_ids: list[str]
    event_labels: list[str]
    joint_probability: float

    @property
    def depth(self) -> int:
        return len(self.event_labels)


@dataclass
class LabelMapping:
    """Bidirectional mapping between generic outcome placeholders and the
    LLM's specific event labels, anchored on each (parent_node, depth)
    position.

    Cegpy edges in the resulting CEG can be looked up by their generic
    label; the specific label and any associated evidence can then be
    re-attached to the corresponding edge in our Pydantic CEG.
    """

    # (from_node_id, generic_label) -> specific_label
    generic_to_specific: dict[tuple[str, str], str] = field(default_factory=dict)
    # (from_node_id, specific_label) -> generic_label
    specific_to_generic: dict[tuple[str, str], str] = field(default_factory=dict)


def enumerate_root_to_leaf_paths(tree: EventTree) -> list[TreePath]:
    """Enumerate every root-to-leaf path in the tree, DFS order."""
    edges_by_source: dict[str, list[EventTreeEdge]] = defaultdict(list)
    for edge in tree.edges:
        edges_by_source[edge.from_node].append(edge)

    paths: list[TreePath] = []

    def dfs(
        node_id: str,
        node_path: list[str],
        event_path: list[str],
        joint_prob: float,
    ) -> None:
        outgoing = edges_by_source.get(node_id, [])
        if not outgoing:
            paths.append(
                TreePath(
                    node_ids=node_path.copy(),
                    event_labels=event_path.copy(),
                    joint_probability=joint_prob,
                )
            )
            return
        for edge in outgoing:
            node_path.append(edge.to_node)
            event_path.append(edge.event_label)
            dfs(
                edge.to_node,
                node_path,
                event_path,
                joint_prob * edge.conditional_probability,
            )
            node_path.pop()
            event_path.pop()

    dfs(tree.root_node_id, [tree.root_node_id], [], 1.0)
    return paths


def _build_generic_label_mapping(tree: EventTree) -> LabelMapping:
    """For each non-leaf node, assign generic outcome_K labels to its
    outgoing edges in deterministic (edge.id-sorted) order."""
    mapping = LabelMapping()
    edges_by_source: dict[str, list[EventTreeEdge]] = defaultdict(list)
    for edge in tree.edges:
        edges_by_source[edge.from_node].append(edge)

    for source_id, outgoing in edges_by_source.items():
        outgoing_sorted = sorted(outgoing, key=lambda e: e.id)
        for k, edge in enumerate(outgoing_sorted):
            generic = f"outcome_{k}"
            mapping.generic_to_specific[(source_id, generic)] = edge.event_label
            mapping.specific_to_generic[(source_id, edge.event_label)] = generic

    return mapping


def event_tree_to_dataframe(
    tree: EventTree,
    *,
    pseudo_count: int = 1000,
    level_column_prefix: str = "level",
    use_generic_labels: bool = False,
) -> tuple[pd.DataFrame, Optional[LabelMapping]]:
    """Expand an EventTree into a pandas DataFrame of pseudo-observations.

    Args:
        tree: The validated EventTree.
        pseudo_count: Total number of pseudo-observations to generate,
            distributed across root-to-leaf paths in proportion to each
            path's joint probability. Every path gets at least one row.
        level_column_prefix: Column-name prefix; columns will be
            "level_0", "level_1", ... up to the maximum tree depth.
        use_generic_labels: If True, event labels in the dataframe are
            replaced with positional placeholders ("outcome_0", "outcome_1",
            ...) per parent node. Required for cegpy AHC to find pairs
            of situations to merge.

    Returns:
        (DataFrame, LabelMapping or None). The mapping is None when
        use_generic_labels=False; otherwise it carries the bidirectional
        translation needed to re-attach specific labels to cegpy's output.

    Raises:
        ValueError: if pseudo_count <= 0, the tree has no paths, or the
            tree has no edges.
    """
    if pseudo_count <= 0:
        raise ValueError(f"pseudo_count must be positive, got {pseudo_count}")

    paths = enumerate_root_to_leaf_paths(tree)
    if not paths:
        raise ValueError(
            "Event tree has no root-to-leaf paths; cannot build dataframe"
        )

    max_depth = max(p.depth for p in paths)
    if max_depth == 0:
        raise ValueError(
            "Event tree has no edges (root is the only node); "
            "cannot build dataframe"
        )

    label_mapping: Optional[LabelMapping] = None
    if use_generic_labels:
        label_mapping = _build_generic_label_mapping(tree)

    columns = [f"{level_column_prefix}_{i}" for i in range(max_depth)]

    # When using generic labels, we need to walk path-by-path with parent
    # information, since the generic label depends on the parent.
    rows: list[list[Optional[str]]] = []
    for path in paths:
        n = round(pseudo_count * path.joint_probability)
        if n < 1:
            n = 1

        if use_generic_labels:
            generic_labels: list[str] = []
            assert label_mapping is not None
            for depth, specific in enumerate(path.event_labels):
                parent_id = path.node_ids[depth]
                generic = label_mapping.specific_to_generic[(parent_id, specific)]
                generic_labels.append(generic)
            row_labels = generic_labels
        else:
            row_labels = list(path.event_labels)

        padded = row_labels + [None] * (max_depth - len(row_labels))
        rows.extend([padded[:] for _ in range(n)])

    return pd.DataFrame(rows, columns=columns), label_mapping