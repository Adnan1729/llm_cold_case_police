"""CEG repair operations.

Repair is distinct from validation. Validators identify what's wrong;
repair functions attempt to fix specific classes of problem. The pipeline
runs repair before final validation so the model's "close but not quite"
output becomes usable.

Each repair function is small, focused, and idempotent: running it twice
produces the same result as running it once.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from consortium.schemas.ceg import CEGEdge, CEGNodeType, ChainEventGraph


@dataclass
class NormalizationRecord:
    """Record of one node's outgoing probabilities being normalised."""

    node_id: str
    original_sum: float
    edge_count: int
    edge_ids: list[str]


@dataclass
class RepairReport:
    """Summary of all repairs applied to a CEG."""

    normalizations: list[NormalizationRecord] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.normalizations


def normalize_outgoing_probabilities(
    ceg: ChainEventGraph,
    *,
    tolerance: float = 1e-4,
) -> tuple[ChainEventGraph, RepairReport]:
    """Scale outgoing edge probabilities at each non-leaf node to sum to 1.0.

    For each non-leaf node:
    - If the sum is already within `tolerance` of 1.0, leave it.
    - If the sum is positive but ≠ 1.0, scale all outgoing edges
      proportionally so they sum to 1.0.
    - If the sum is 0.0 (or there are no outgoing edges), leave it —
      the structural validator will report it as a real problem.

    Returns the (possibly modified) CEG and a RepairReport describing
    every change. The original CEG is not mutated.
    """
    leaf_ids = {n.id for n in ceg.nodes if n.type == CEGNodeType.LEAF.value}

    outgoing_by_node: dict[str, list[tuple[int, CEGEdge]]] = defaultdict(list)
    for i, edge in enumerate(ceg.edges):
        outgoing_by_node[edge.from_node].append((i, edge))

    new_edges = list(ceg.edges)
    report = RepairReport()

    for node_id, indexed_edges in outgoing_by_node.items():
        if node_id in leaf_ids:
            continue

        total = sum(e.conditional_probability for _, e in indexed_edges)
        if total <= 0:
            continue
        if abs(total - 1.0) <= tolerance:
            continue

        for i, edge in indexed_edges:
            new_edges[i] = edge.model_copy(
                update={
                    "conditional_probability": edge.conditional_probability / total
                }
            )

        report.normalizations.append(
            NormalizationRecord(
                node_id=node_id,
                original_sum=total,
                edge_count=len(indexed_edges),
                edge_ids=[e.id for _, e in indexed_edges],
            )
        )

    if report.is_empty():
        return ceg, report

    return ceg.model_copy(update={"edges": new_edges}), report