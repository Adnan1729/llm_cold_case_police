"""Intermediate schemas used during the consortium debate.

These are the shapes the orchestrator exchanges with agents between the
initial Hypothesis generation and the final aggregation. They are not
part of the pipeline's external contract — only Case, RankedHypotheses,
and ChainEventGraph cross stage boundaries.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from consortium.schemas.hypothesis import Hypothesis


class HypothesisGenerationOutput(BaseModel):
    """Wrapper for the Investigator's structured generation output."""

    model_config = ConfigDict(extra="forbid")

    hypotheses: list[Hypothesis]


class HypothesisCritique(BaseModel):
    """A critic agent's structured critique of one Hypothesis."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    overlooked_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence IDs the hypothesis fails to address.",
    )
    suggested_revisions: list[str] = Field(default_factory=list)
    overall_assessment: str


class CritiqueBundle(BaseModel):
    """One critic agent's critiques covering the full Hypothesis set."""

    model_config = ConfigDict(extra="forbid")

    critiques: list[HypothesisCritique]


class HypothesisScore(BaseModel):
    """A single agent's score for a single Hypothesis."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(..., description="One sentence explaining the score.")


class ScoreBundle(BaseModel):
    """One agent's scores covering the full Hypothesis set."""

    model_config = ConfigDict(extra="forbid")

    scores: list[HypothesisScore]