"""Structural and grounding validation for EventTree objects.

A valid event tree must satisfy:
- The root_node_id refers to an existing node.
- The root has no incoming edges.
- Every non-root node has exactly one incoming edge (its parent).
- No node references in edges are dangling.
- The graph is acyclic.
- All nodes are reachable from the root.
- Outgoing probabilities at each non-leaf node sum to 1.0.

Plus, optionally, evidence grounding (all referenced evidence IDs exist).

This mirrors `consortium.ceg.validator` but for the tree precursor.
Constraints checked here are deliberately stricter than the CEG validator's:
single-parent enforcement and reachability eliminate at schema-validation
time the kinds of failure modes (orphaned situation nodes, non-tree DAGs)
we observed in the LLM-generated CEGs from earlier runs.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

import networkx as nx

from consortium.schemas.case import Case
from consortium.schemas.event_tree import EventTree


class EventTreeValidationError(ValueError):
    """Raised when an EventTree fails structural or grounding validation."""


def validate_event_tree_structure(
    tree: EventTree,
    *,
    probability_tolerance: float = 1e-4,
) -> list[str]:
    """Return a list of human-readable structural problems.

    Empty list means the tree is structurally valid. Checks:
    1. root_node_id resolves to a node.
    2. Edge endpoints (from_node, to_node) resolve to nodes.
    3. The root has no incoming edges.
    4. Every non-root node has exactly one incoming edge.
    5. The graph is acyclic.
    6. Every node is reachable from the root.
    7. For every non-leaf node, outgoing edge probabilities sum to 1.0
       within `probability_tolerance`.
    """
    problems: list[str] = []
    node_ids = {n.id for n in tree.nodes}

    # 1. Root exists
    if tree.root_node_id not in node_ids:
        problems.append(
            f"root_node_id '{tree.root_node_id}' is not a node in the tree"
        )

    # 2. Edge endpoints + accumulate incoming/outgoing
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing_by_node: dict[str, list] = defaultdict(list)
    for edge in tree.edges:
        if edge.from_node not in node_ids:
            problems.append(
                f"edge '{edge.id}' references unknown from_node "
                f"'{edge.from_node}'"
            )
        if edge.to_node not in node_ids:
            problems.append(
                f"edge '{edge.id}' references unknown to_node "
                f"'{edge.to_node}'"
            )
        if edge.from_node in node_ids and edge.to_node in node_ids:
            incoming[edge.to_node].append(edge.id)
            outgoing_by_node[edge.from_node].append(edge)

    # 3. Root has no incoming
    if tree.root_node_id in node_ids and incoming.get(tree.root_node_id):
        problems.append(
            f"root node '{tree.root_node_id}' has "
            f"{len(incoming[tree.root_node_id])} incoming edge(s); "
            f"the root must have none"
        )

    # 4. Every non-root node has exactly one parent
    for node in tree.nodes:
        if node.id == tree.root_node_id:
            continue
        n_in = len(incoming.get(node.id, []))
        if n_in == 0:
            problems.append(
                f"node '{node.id}' has no incoming edge "
                f"(only the root may have no parent)"
            )
        elif n_in > 1:
            problems.append(
                f"node '{node.id}' has {n_in} incoming edges "
                f"(via {incoming[node.id]}); tree nodes must have "
                f"exactly one parent"
            )

    # 5. Acyclic (built from valid edges only)
    g = nx.DiGraph()
    g.add_nodes_from(node_ids)
    for edge in tree.edges:
        if edge.from_node in node_ids and edge.to_node in node_ids:
            g.add_edge(edge.from_node, edge.to_node)
    is_dag = nx.is_directed_acyclic_graph(g) if g.number_of_nodes() > 0 else True
    if not is_dag:
        problems.append("graph contains at least one cycle")

    # 6. Reachability (only meaningful if DAG and root exists)
    if tree.root_node_id in node_ids and is_dag:
        reachable = nx.descendants(g, tree.root_node_id) | {tree.root_node_id}
        unreachable = node_ids - reachable
        if unreachable:
            problems.append(
                f"node(s) not reachable from root: {sorted(unreachable)}"
            )

    # 7. Probability sums
    for node in tree.nodes:
        outgoing = outgoing_by_node.get(node.id, [])
        if not outgoing:
            # Leaf node — nothing to sum
            continue
        total = sum(e.conditional_probability for e in outgoing)
        if abs(total - 1.0) > probability_tolerance:
            problems.append(
                f"outgoing probabilities from node '{node.id}' sum to "
                f"{total:.4f}, expected 1.0 "
                f"(tolerance {probability_tolerance})"
            )

    return problems


def validate_event_tree_evidence_grounding(
    tree: EventTree,
    case: Case,
) -> list[str]:
    """Return a list of evidence-grounding problems.

    Checks that every evidence ID referenced on any node or edge exists
    in the case's evidence list.
    """
    problems: list[str] = []
    valid_ids = {e.id for e in case.evidence}

    for node in tree.nodes:
        for ev_id in node.associated_evidence:
            if ev_id not in valid_ids:
                problems.append(
                    f"node '{node.id}' references unknown evidence '{ev_id}'"
                )

    for edge in tree.edges:
        for ev_id in edge.associated_evidence:
            if ev_id not in valid_ids:
                problems.append(
                    f"edge '{edge.id}' references unknown evidence '{ev_id}'"
                )

    return problems


def assert_event_tree_valid(
    tree: EventTree,
    case: Optional[Case] = None,
    *,
    probability_tolerance: float = 1e-4,
) -> None:
    """Raise EventTreeValidationError if the tree has any problems.

    If `case` is provided, evidence grounding is also checked.
    """
    problems = validate_event_tree_structure(
        tree, probability_tolerance=probability_tolerance
    )
    if case is not None:
        problems.extend(validate_event_tree_evidence_grounding(tree, case))

    if problems:
        raise EventTreeValidationError(
            f"EventTree validation failed with {len(problems)} problem(s):\n"
            + "\n".join(f"  - {p}" for p in problems)
        )