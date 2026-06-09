"""Hypothesis-related schemas.

A Hypothesis is the structured output of the consortium for a single
candidate explanation of a case. Every claim a hypothesis makes about
evidence must be expressed as an EvidenceSupport entry citing the evidence
by id — this is the primary hallucination defence for the POC.

A RankedHypotheses object is the final output of the consortium stage:
the full set of generated hypotheses, ordered by aggregated confidence.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ActorRole(str, Enum):
    PERPETRATOR = "perpetrator"
    VICTIM = "victim"
    ACCOMPLICE = "accomplice"
    WITNESS = "witness"
    OTHER = "other"


class SupportRole(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class Actor(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    name: str
    role: ActorRole
    description: Optional[str] = None


class HypothesisEvent(BaseModel):
    """An event in the hypothesised sequence of what happened."""

    model_config = ConfigDict(extra="forbid")

    sequence_index: int = Field(..., ge=0, description="Ordinal position in the sequence.")
    timestamp: Optional[str] = Field(
        None,
        description="ISO 8601 datetime if estimable; otherwise null.",
    )
    description: str
    supporting_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence IDs that support this specific event being in the sequence.",
    )


class EvidenceSupport(BaseModel):
    """How a specific evidence item bears on this hypothesis."""

    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    evidence_id: str = Field(..., description="ID of the evidence item, e.g. 'E003'.")
    role: SupportRole
    weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Strength of the bearing on the hypothesis, regardless of direction.",
    )
    note: Optional[str] = Field(
        None,
        description="Explanation of how this evidence supports, contradicts, or relates.",
    )


class AgentScore(BaseModel):
    """A single agent's confidence score for a hypothesis, used in weighted aggregation."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    score: float = Field(..., ge=0.0, le=1.0)
    rationale: Optional[str] = None


class Hypothesis(BaseModel):
    """A single candidate explanation of the case."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable identifier, e.g. 'H1'.")
    one_line_summary: str = Field(..., max_length=240)
    narrative: str = Field(
        ...,
        description="A 200–400 word narrative description of what the hypothesis proposes.",
    )

    actors: list[Actor] = Field(default_factory=list)
    timeline: list[HypothesisEvent] = Field(default_factory=list)

    evidence_support: list[EvidenceSupport] = Field(
        default_factory=list,
        description=(
            "Every evidence item the hypothesis touches must appear here. The "
            "validator will reject hypotheses whose narrative references evidence "
            "not declared in this list."
        ),
    )
    unexplained_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence IDs the hypothesis cannot account for.",
    )

    is_exculpatory: bool = Field(
        False,
        description="True if this hypothesis primarily exculpates a named person of interest.",
    )

    agent_scores: list[AgentScore] = Field(
        default_factory=list,
        description="Per-agent confidence scores from the consortium debate.",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Aggregated confidence after weighted aggregation across agents.",
    )
    rank: Optional[int] = Field(
        None,
        ge=1,
        description="Final rank within the ranked set; null until aggregation runs.",
    )


class RankedHypotheses(BaseModel):
    """The complete output of the consortium stage."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    hypotheses: list[Hypothesis]
    aggregation_method: str = "weighted_mean"
    debate_round_count: Optional[int] = None
    notes: Optional[str] = Field(
        None,
        description="Free-text notes from the moderator, e.g. unresolved disagreements.",
    )