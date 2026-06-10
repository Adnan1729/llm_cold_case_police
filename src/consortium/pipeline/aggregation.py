"""Score aggregation: combine per-agent scores into final confidence and rank.

For the POC the only aggregation method is weighted mean. The
AggregatorFn alias documents the plug-in shape if alternative methods
(weighted median, trimmed mean, Bayesian) are added later.
"""
from __future__ import annotations

from typing import Callable

from consortium.agents.base import Agent
from consortium.schemas.hypothesis import Hypothesis, RankedHypotheses


def aggregate_weighted_mean(
    hypotheses: list[Hypothesis],
    agents: list[Agent],
    *,
    case_id: str,
) -> RankedHypotheses:
    """Aggregate per-agent scores via weighted mean.

    For each Hypothesis:
        confidence_score = sum(weight_i * score_i) / sum(weight_i)
    where i ranges over agents that scored this hypothesis. Unknown agent
    names default to weight 1.0.

    Hypotheses are then sorted by confidence_score descending and assigned
    ranks 1, 2, 3, ...
    """
    weights_by_name = {a.name: a.weight for a in agents}

    scored: list[Hypothesis] = []
    for h in hypotheses:
        total_weight = 0.0
        weighted_sum = 0.0
        for s in h.agent_scores:
            w = weights_by_name.get(s.agent_name, 1.0)
            total_weight += w
            weighted_sum += w * s.score
        confidence = weighted_sum / total_weight if total_weight > 0 else 0.0
        scored.append(h.model_copy(update={"confidence_score": confidence}))

    scored.sort(key=lambda h: h.confidence_score or 0.0, reverse=True)
    ranked = [h.model_copy(update={"rank": i + 1}) for i, h in enumerate(scored)]

    return RankedHypotheses(
        case_id=case_id,
        hypotheses=ranked,
        aggregation_method="weighted_mean",
    )


AggregatorFn = Callable[..., RankedHypotheses]