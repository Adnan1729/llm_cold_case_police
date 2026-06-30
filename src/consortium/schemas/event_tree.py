"""Event Tree schemas.

An event tree is a directed tree where:
- Exactly one node has no incoming edges (the root).
- Every other node has exactly one incoming edge (its parent).
- Outgoing edge probabilities from any non-leaf node sum to 1.0.
- Leaves are simply nodes with no outgoing edges (no explicit type field).

Event trees are the precursor representation to Chain Event Graphs (CEGs).
cegpy's AHC algorithm identifies stages (equivalence classes of nodes
with identical outgoing probability distributions) and collapses them
into a CEG.

In this pipeline, the LLM generates an EventTree; cegpy converts it to
a CEG. The simpler tree structure is significantly easier for small
models to produce reliably than a full CEG with equivalence classes:
- No `type` field on nodes (root/leaf is determined by position).
- No `stages` field (every node is its own stage at this point).
- No `leaf_node_ids` field (leaves are inferred).

Schema validation here is field-level only (types, ranges, required
fields). Structural validation (tree shape, probability sums) lives in
`consortium.ceg.event_tree_validator`.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EventTreeNode(BaseModel):
    """A node in the event tree, representing a state of the world."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable identifier, e.g. 'N0'.")
    description: str = Field(
        ..., description="What state of the world this node represents."
    )
    associated_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence IDs that anchor this state.",
    )


class EventTreeEdge(BaseModel):
    """A directed edge in the event tree, representing a transition (event)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable identifier, e.g. 'T0'.")
    from_node: str = Field(..., description="ID of source node.")
    to_node: str = Field(..., description="ID of destination node.")
    event_label: str = Field(
        ..., description="A short label for the transition event."
    )
    conditional_probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "P(to_node | from_node). Outgoing edges from any single node "
            "should sum to 1.0; enforced by validator, not at schema level."
        ),
    )
    associated_evidence: list[str] = Field(default_factory=list)


class EventTree(BaseModel):
    """An event tree representing a hypothesis as a branching event sequence.

    Unlike a CEG, an event tree has no equivalence-class staging — every
    node is in its own stage. cegpy's AHC algorithm identifies stages
    downstream and produces a CEG by merging equivalent positions.

    `root_node_id` is declared explicitly to make the LLM commit to it;
    leaves are implicit (nodes with no outgoing edges).
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str
    hypothesis_id: str = Field(
        ..., description="The Hypothesis this event tree materialises."
    )

    nodes: list[EventTreeNode]
    edges: list[EventTreeEdge]

    root_node_id: str = Field(
        ...,
        description="ID of the root node. Must appear in `nodes` and have no incoming edges.",
    )

    notes: Optional[str] = None