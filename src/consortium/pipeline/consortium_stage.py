"""Consortium stage entry point.

Wires an Orchestrator with the aggregator. This is the single function
the pipeline's CLI and UI call to run the consortium stage.
"""
from __future__ import annotations

from consortium.agents.base import Agent
from consortium.orchestrators.base import ConsortiumOrchestrator
from consortium.pipeline.aggregation import aggregate_weighted_mean
from consortium.schemas.case import Case
from consortium.schemas.hypothesis import RankedHypotheses


def run_consortium(
    case: Case,
    agents: list[Agent],
    orchestrator: ConsortiumOrchestrator,
    *,
    max_hypotheses: int = 6,
) -> RankedHypotheses:
    """Run the consortium stage end-to-end and return RankedHypotheses."""
    hypotheses = orchestrator.run(case, agents, max_hypotheses=max_hypotheses)
    return aggregate_weighted_mean(
        hypotheses, agents, case_id=case.metadata.case_id
    )