"""Orchestrator interface.

An Orchestrator runs a multi-agent process over a Case and produces a
list of Hypothesis objects with their `agent_scores` populated. It does
NOT compute final aggregated `confidence_score` or `rank` — those are
the Aggregator's job, called downstream in `consortium_stage.run_consortium`.

Implementations:
    PhasedOrchestrator     — deterministic phase-based, no framework.
    AutoGenOrchestrator    — (planned) AutoGen GroupChat-based debate.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from consortium.agents.base import Agent
from consortium.schemas.case import Case
from consortium.schemas.hypothesis import Hypothesis


class ConsortiumOrchestrator(ABC):
    """Abstract base for consortium orchestrators."""

    @abstractmethod
    def run(
        self,
        case: Case,
        agents: list[Agent],
        *,
        max_hypotheses: int = 6,
    ) -> list[Hypothesis]:
        """Run the consortium and return scored hypotheses.

        Returned Hypothesis objects have `agent_scores` populated but
        `confidence_score` and `rank` are still None — the aggregator
        sets those.
        """
        raise NotImplementedError