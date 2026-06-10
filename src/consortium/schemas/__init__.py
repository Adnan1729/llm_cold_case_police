"""Public schema exports.

All Pydantic models that cross module boundaries are re-exported here so
that callers can `from consortium.schemas import Hypothesis` without
needing to know which file the model lives in.
"""
from consortium.schemas.case import Case, CaseMetadata, Incident, Victim
from consortium.schemas.ceg import (
    CEGEdge,
    CEGNode,
    CEGNodeType,
    CEGStage,
    ChainEventGraph,
)
from consortium.schemas.evidence import EvidenceCard, EvidenceType, Reliability
from consortium.schemas.hypothesis import (
    Actor,
    ActorRole,
    AgentScore,
    EvidenceSupport,
    Hypothesis,
    HypothesisEvent,
    RankedHypotheses,
    SupportRole,
)

from consortium.schemas.debate import (
    CritiqueBundle,
    HypothesisCritique,
    HypothesisGenerationOutput,
    HypothesisScore,
    ScoreBundle,
)

# # Change these absolute imports to relative imports:
# from .case import Case, CaseMetadata, Incident, Victim
# from .ceg import (
#     CEGEdge,
#     CEGNode,
#     CEGNodeType,
#     CEGStage,
#     ChainEventGraph,
# )
# from .evidence import EvidenceCard, EvidenceType, Reliability
# from .hypothesis import (
#     Actor,
#     ActorRole,
#     AgentScore,
#     EvidenceSupport,
#     Hypothesis,
#     HypothesisEvent,
#     RankedHypotheses,
#     SupportRole,
# )

__all__ = [
    # case
    "Case",
    "CaseMetadata",
    "Incident",
    "Victim",
    # ceg
    "CEGEdge",
    "CEGNode",
    "CEGNodeType",
    "CEGStage",
    "ChainEventGraph",
    # evidence
    "EvidenceCard",
    "EvidenceType",
    "Reliability",
    # hypothesis
    "Actor",
    "ActorRole",
    "AgentScore",
    "EvidenceSupport",
    "Hypothesis",
    "HypothesisEvent",
    "RankedHypotheses",
    "SupportRole",
    # debate
    "CritiqueBundle",
    "HypothesisCritique",
    "HypothesisGenerationOutput",
    "HypothesisScore",
    "ScoreBundle",
]