"""Structural and grounding validation for ChainEventGraph objects.

Schemas enforce shape (types, required fields, value ranges); validators
enforce semantics that span multiple fields:
- Connectivity (referenced nodes exist).
- Acyclicity (no loops; CEGs are DAGs).
- Probability sums (outgoing edges from each non-leaf sum to 1.0).
- Evidence grounding (referenced evidence IDs exist in the case).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

import networkx as nx

from consortium.schemas.case import Case
from consortium.schemas.ceg import CEGNodeType, ChainEventGraph


class CEGValidationError(ValueError):
    """Raised when a CEG fails structural or grounding validation."""


def validate_ceg_structure(
    ceg: ChainEventGraph,
    *,
    probability_tolerance: float = 1e-4,
) -> list[str]:
    """Return a list of human-readable structural problems with the CEG.

    Empty list means structurally valid. Checks:
    1. root_node_id resolves to a node of type 'root'.
    2. leaf_node_ids all resolve to nodes of type 'leaf'.
    3. Every edge's from_node and to_node resolve to nodes.
    4. The graph is acyclic.
    5. For every non-leaf node, outgoing edge probabilities sum to 1.0.
    6. Leaf nodes have no outgoing edges.
    7. Stage member_nodes all resolve to nodes.
    """
    problems: list[str] = []
    node_ids = {n.id for n in ceg.nodes}
    node_by_id = {n.id: n for n in ceg.nodes}

    # 1. Root
    if ceg.root_node_id not in node_ids:
        problems.append(
            f"root_node_id '{ceg.root_node_id}' is not a node in the graph"
        )
    elif node_by_id[ceg.root_node_id].type != CEGNodeType.ROOT.value:
        problems.append(
            f"root_node_id '{ceg.root_node_id}' is not of type 'root' "
            f"(actual type: {node_by_id[ceg.root_node_id].type})"
        )

    # 2. Leaves
    for leaf_id in ceg.leaf_node_ids:
        if leaf_id not in node_ids:
            problems.append(f"leaf node '{leaf_id}' is not in the graph")
        elif node_by_id[leaf_id].type != CEGNodeType.LEAF.value:
            problems.append(
                f"leaf node '{leaf_id}' is not of type 'leaf' "
                f"(actual type: {node_by_id[leaf_id].type})"
            )

    # 3. Edge endpoints
    for edge in ceg.edges:
        if edge.from_node not in node_ids:
            problems.append(
                f"edge '{edge.id}' references unknown from_node '{edge.from_node}'"
            )
        if edge.to_node not in node_ids:
            problems.append(
                f"edge '{edge.id}' references unknown to_node '{edge.to_node}'"
            )

    # 4. Acyclic
    g = nx.DiGraph()
    g.add_nodes_from(node_ids)
    for edge in ceg.edges:
        if edge.from_node in node_ids and edge.to_node in node_ids:
            g.add_edge(edge.from_node, edge.to_node)
    if g.number_of_nodes() > 0 and not nx.is_directed_acyclic_graph(g):
        problems.append("graph contains at least one cycle")

    # 5, 6. Probability sums and leaf-has-no-outgoing
    outgoing_by_node: dict[str, list] = defaultdict(list)
    for edge in ceg.edges:
        outgoing_by_node[edge.from_node].append(edge)

    for node in ceg.nodes:
        if node.type == CEGNodeType.LEAF.value:
            if outgoing_by_node.get(node.id):
                problems.append(
                    f"leaf node '{node.id}' has "
                    f"{len(outgoing_by_node[node.id])} outgoing edge(s); "
                    f"leaves must have none"
                )
            continue

        outgoing = outgoing_by_node.get(node.id, [])
        if not outgoing:
            problems.append(
                f"non-leaf node '{node.id}' has no outgoing edges"
            )
            continue

        total = sum(e.conditional_probability for e in outgoing)
        if abs(total - 1.0) > probability_tolerance:
            problems.append(
                f"outgoing probabilities from node '{node.id}' sum to "
                f"{total:.4f}, expected 1.0 "
                f"(tolerance {probability_tolerance})"
            )

    # 7. Stage members
    for stage in ceg.stages:
        for member in stage.member_nodes:
            if member not in node_ids:
                problems.append(
                    f"stage '{stage.id}' references unknown node '{member}'"
                )

    return problems


def validate_ceg_evidence_grounding(
    ceg: ChainEventGraph,
    case: Case,
) -> list[str]:
    """Return a list of evidence-grounding problems.

    Checks that every evidence ID referenced in any node or edge exists
    in the case's evidence list.
    """
    problems: list[str] = []
    valid_evidence_ids = {e.id for e in case.evidence}

    for node in ceg.nodes:
        for ev_id in node.associated_evidence:
            if ev_id not in valid_evidence_ids:
                problems.append(
                    f"node '{node.id}' references unknown evidence '{ev_id}'"
                )

    for edge in ceg.edges:
        for ev_id in edge.associated_evidence:
            if ev_id not in valid_evidence_ids:
                problems.append(
                    f"edge '{edge.id}' references unknown evidence '{ev_id}'"
                )

    return problems


def assert_ceg_valid(
    ceg: ChainEventGraph,
    case: Optional[Case] = None,
    *,
    probability_tolerance: float = 1e-4,
) -> None:
    """Raise CEGValidationError if the CEG has any structural or grounding issues.

    If `case` is provided, evidence grounding is also checked.
    """
    problems = validate_ceg_structure(
        ceg, probability_tolerance=probability_tolerance
    )
    if case is not None:
        problems.extend(validate_ceg_evidence_grounding(ceg, case))

    if problems:
        raise CEGValidationError(
            f"CEG validation failed with {len(problems)} problem(s):\n"
            + "\n".join(f"  - {p}" for p in problems)
        )