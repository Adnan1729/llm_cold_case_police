"""Event tree repair operations.

Small LLMs occasionally produce structurally malformed event trees:
- Nodes unreachable from the root (orphaned subgraphs).
- Nodes with multiple parents (a DAG rather than a tree).
- Outgoing probabilities not summing to 1.0 at each non-leaf.

These are recoverable without an LLM round-trip when the model got
"close" to a valid tree. This module applies three deterministic
repair operations, in order:

1. Orphan removal: nodes (and their edges) unreachable from the root
   are dropped.

2. DAG-to-tree expansion: when a node has multiple incoming edges,
   the node and its subtree are duplicated once per incoming edge so
   each copy has a unique parent. Result: a strict tree. cegpy's AHC
   may merge the duplicates back if their conditional distributions
   are equivalent.

3. Probability normalisation: outgoing probabilities at each non-leaf
   are scaled to sum to 1.0 where they don't already.

After repair, the existing event_tree_validator runs as before. Any
remaining issues trigger the retry-with-feedback mechanism.

The repair report records what was modified, so the audit log
preserves a clear distinction between what the LLM produced verbatim
and what deterministic code fixed.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from consortium.schemas.event_tree import (
    EventTree,
    EventTreeEdge,
    EventTreeNode,
)


@dataclass
class EventTreeRepairReport:
    """Summary of what repair_event_tree changed."""

    orphans_dropped: list[str] = field(default_factory=list)
    edges_dropped_with_orphans: list[str] = field(default_factory=list)
    duplicated_nodes: dict[str, list[str]] = field(default_factory=dict)
    probability_normalizations: list[dict] = field(default_factory=list)
    expansion_skipped_reason: str | None = None

    def is_empty(self) -> bool:
        return (
            not self.orphans_dropped
            and not self.edges_dropped_with_orphans
            and not self.duplicated_nodes
            and not self.probability_normalizations
            and self.expansion_skipped_reason is None
        )


def repair_event_tree(
    tree: EventTree,
    *,
    probability_tolerance: float = 1e-4,
    max_expanded_nodes: int = 200,
) -> tuple[EventTree, EventTreeRepairReport]:
    """Best-effort structural repair of an event tree.

    Args:
        tree: The (possibly malformed) event tree.
        probability_tolerance: Tolerance for the normalisation pass.
        max_expanded_nodes: Safety cap on DAG-to-tree expansion. If
            expansion would exceed this, expansion is skipped and the
            validator's normal retry mechanism takes over.

    Returns:
        (repaired_tree, repair_report)
    """
    report = EventTreeRepairReport()
    tree, report = _drop_unreachable(tree, report)
    tree, report = _expand_dag_to_tree(
        tree, report, max_expanded_nodes=max_expanded_nodes
    )
    tree, report = _normalize_probabilities(
        tree, report, tolerance=probability_tolerance
    )
    return tree, report


def _drop_unreachable(
    tree: EventTree,
    report: EventTreeRepairReport,
) -> tuple[EventTree, EventTreeRepairReport]:
    """Remove nodes (and their edges) unreachable from the root."""
    all_node_ids = {n.id for n in tree.nodes}
    if tree.root_node_id not in all_node_ids:
        # Root doesn't exist; let validation handle this.
        return tree, report

    edges_by_source: dict[str, list[EventTreeEdge]] = defaultdict(list)
    for edge in tree.edges:
        edges_by_source[edge.from_node].append(edge)

    reachable: set[str] = set()
    queue = deque([tree.root_node_id])
    while queue:
        nid = queue.popleft()
        if nid in reachable:
            continue
        reachable.add(nid)
        for edge in edges_by_source.get(nid, []):
            if edge.to_node not in reachable:
                queue.append(edge.to_node)

    orphans = all_node_ids - reachable
    if not orphans:
        return tree, report

    new_nodes = [n for n in tree.nodes if n.id in reachable]
    new_edges: list[EventTreeEdge] = []
    dropped_edges: list[str] = []
    for edge in tree.edges:
        if edge.from_node in reachable and edge.to_node in reachable:
            new_edges.append(edge)
        else:
            dropped_edges.append(edge.id)

    report.orphans_dropped.extend(sorted(orphans))
    report.edges_dropped_with_orphans.extend(dropped_edges)

    return (
        tree.model_copy(update={"nodes": new_nodes, "edges": new_edges}),
        report,
    )


def _expand_dag_to_tree(
    tree: EventTree,
    report: EventTreeRepairReport,
    *,
    max_expanded_nodes: int,
) -> tuple[EventTree, EventTreeRepairReport]:
    """Convert DAG to strict tree by duplicating shared descendants.

    Each time a node is reached via a different parent, a fresh copy
    of the node (and its subtree) is generated under the new parent.
    """
    incoming_count: dict[str, int] = defaultdict(int)
    for edge in tree.edges:
        incoming_count[edge.to_node] += 1
    multi_parent = {nid for nid, cnt in incoming_count.items() if cnt > 1}
    if not multi_parent:
        return tree, report

    nodes_by_id = {n.id: n for n in tree.nodes}
    if tree.root_node_id not in nodes_by_id:
        return tree, report

    edges_by_source: dict[str, list[EventTreeEdge]] = defaultdict(list)
    for edge in tree.edges:
        edges_by_source[edge.from_node].append(edge)

    new_nodes: list[EventTreeNode] = []
    new_edges: list[EventTreeEdge] = []
    duplications: dict[str, list[str]] = defaultdict(list)

    node_counter = 0
    edge_counter = 0

    new_root_id = f"N{node_counter}"
    node_counter += 1
    old_root = nodes_by_id[tree.root_node_id]
    new_nodes.append(EventTreeNode(
        id=new_root_id,
        description=old_root.description,
        associated_evidence=list(old_root.associated_evidence),
    ))
    duplications[tree.root_node_id].append(new_root_id)

    # DFS stack: (old_child_id, new_parent_id, source_edge_from_original)
    stack: list[tuple[str, str, EventTreeEdge]] = []
    for edge in edges_by_source.get(tree.root_node_id, []):
        stack.append((edge.to_node, new_root_id, edge))

    while stack:
        old_child_id, new_parent_id, source_edge = stack.pop()

        if old_child_id not in nodes_by_id:
            continue  # dangling edge; validator catches it

        if node_counter > max_expanded_nodes:
            report.expansion_skipped_reason = (
                f"expansion would exceed {max_expanded_nodes} nodes"
            )
            return tree, report  # leave original; validator will retry

        old_child = nodes_by_id[old_child_id]

        new_child_id = f"N{node_counter}"
        node_counter += 1
        new_nodes.append(EventTreeNode(
            id=new_child_id,
            description=old_child.description,
            associated_evidence=list(old_child.associated_evidence),
        ))
        duplications[old_child_id].append(new_child_id)

        new_edges.append(EventTreeEdge(
            id=f"T{edge_counter}",
            from_node=new_parent_id,
            to_node=new_child_id,
            event_label=source_edge.event_label,
            conditional_probability=source_edge.conditional_probability,
            associated_evidence=list(source_edge.associated_evidence),
        ))
        edge_counter += 1

        for child_edge in edges_by_source.get(old_child_id, []):
            stack.append((child_edge.to_node, new_child_id, child_edge))

    for old_id, new_ids in duplications.items():
        if len(new_ids) > 1:
            report.duplicated_nodes[old_id] = list(new_ids)

    new_tree = tree.model_copy(update={
        "nodes": new_nodes,
        "edges": new_edges,
        "root_node_id": new_root_id,
    })
    return new_tree, report


def _normalize_probabilities(
    tree: EventTree,
    report: EventTreeRepairReport,
    *,
    tolerance: float,
) -> tuple[EventTree, EventTreeRepairReport]:
    """Scale outgoing probabilities at each non-leaf to sum to 1.0."""
    edges_by_source: dict[str, list[tuple[int, EventTreeEdge]]] = defaultdict(list)
    for i, edge in enumerate(tree.edges):
        edges_by_source[edge.from_node].append((i, edge))

    new_edges = list(tree.edges)
    changed = False
    for node_id, indexed in edges_by_source.items():
        if not indexed:
            continue
        total = sum(e.conditional_probability for _, e in indexed)
        if total <= 0:
            continue
        if abs(total - 1.0) <= tolerance:
            continue
        for i, edge in indexed:
            new_edges[i] = edge.model_copy(update={
                "conditional_probability": edge.conditional_probability / total
            })
        report.probability_normalizations.append({
            "node_id": node_id,
            "original_sum": total,
            "edge_count": len(indexed),
        })
        changed = True

    if not changed:
        return tree, report
    return tree.model_copy(update={"edges": new_edges}), report