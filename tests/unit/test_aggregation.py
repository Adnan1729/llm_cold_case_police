"""Tests for weighted-mean aggregation."""
from __future__ import annotations

from consortium.agents.base import Agent
from consortium.clients import MockClient
from consortium.pipeline.aggregation import aggregate_weighted_mean
from consortium.schemas.hypothesis import AgentScore, Hypothesis


def _hyp(id_: str, scores: list[tuple[str, float]]) -> Hypothesis:
    return Hypothesis(
        id=id_,
        one_line_summary=f"summary {id_}",
        narrative=f"narrative {id_}",
        agent_scores=[
            AgentScore(agent_name=n, score=s, rationale="r") for n, s in scores
        ],
    )


def _agent(name: str, weight: float = 1.0) -> Agent:
    return Agent(
        name=name,
        role="critic",
        client=MockClient(name=f"m-{name}"),
        system_prompt_template="system/forensic_analyst.j2",
        weight=weight,
    )


def test_equal_weights_simple_mean():
    h1 = _hyp("H1", [("a", 0.8), ("b", 0.6)])
    h2 = _hyp("H2", [("a", 0.3), ("b", 0.4)])
    result = aggregate_weighted_mean(
        [h1, h2], [_agent("a"), _agent("b")], case_id="c"
    )
    assert result.hypotheses[0].id == "H1"
    assert result.hypotheses[0].confidence_score == 0.7
    assert result.hypotheses[0].rank == 1
    assert result.hypotheses[1].confidence_score == 0.35
    assert result.hypotheses[1].rank == 2


def test_uneven_weights():
    h = _hyp("H1", [("a", 1.0), ("b", 0.0)])
    result = aggregate_weighted_mean(
        [h], [_agent("a", weight=3.0), _agent("b", weight=1.0)], case_id="c"
    )
    # (3*1.0 + 1*0.0) / 4 = 0.75
    assert result.hypotheses[0].confidence_score == 0.75


def test_sort_descending_with_ranks():
    hs = [_hyp("H1", [("a", 0.2)]), _hyp("H2", [("a", 0.9)]), _hyp("H3", [("a", 0.5)])]
    result = aggregate_weighted_mean(hs, [_agent("a")], case_id="c")
    assert [h.id for h in result.hypotheses] == ["H2", "H3", "H1"]
    assert [h.rank for h in result.hypotheses] == [1, 2, 3]


def test_unknown_agent_defaults_to_weight_one():
    h = _hyp("H1", [("known", 0.8), ("unknown", 0.4)])
    result = aggregate_weighted_mean([h], [_agent("known", weight=2.0)], case_id="c")
    # (2*0.8 + 1*0.4) / 3 = 0.6666...
    assert abs(result.hypotheses[0].confidence_score - (2/3)) < 1e-6