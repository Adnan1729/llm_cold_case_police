"""Tests for PhasedOrchestrator end-to-end with MockClient."""
from __future__ import annotations

import pytest

from consortium.agents.base import Agent
from consortium.clients import MockClient
from consortium.orchestrators.phased import PhasedOrchestrator
from consortium.schemas.case import Case, CaseMetadata
from consortium.schemas.debate import (
    CritiqueBundle,
    HypothesisCritique,
    HypothesisGenerationOutput,
    HypothesisScore,
    ScoreBundle,
)
from consortium.schemas.evidence import EvidenceCard, EvidenceType, Reliability
from consortium.schemas.hypothesis import (
    EvidenceSupport,
    Hypothesis,
    SupportRole,
)


def _minimal_case() -> Case:
    return Case(
        metadata=CaseMetadata(case_id="test", case_name="Test"),
        narrative="Short test narrative.",
        evidence=[
            EvidenceCard(
                id="E001",
                type=EvidenceType.WITNESS_STATEMENT,
                title="W1",
                content="Witness saw X.",
                source="PC Test",
                timestamp_referenced=None,
                location_referenced=None,
                reliability=Reliability.MEDIUM,
                reliability_note="Test.",
                chain_of_custody_note="Test.",
            ),
        ],
    )


def _hyp(id_: str) -> Hypothesis:
    return Hypothesis(
        id=id_,
        one_line_summary=f"Summary {id_}",
        narrative=f"Narrative {id_}",
        evidence_support=[
            EvidenceSupport(
                evidence_id="E001",
                role=SupportRole.SUPPORTS,
                weight=0.5,
            ),
        ],
    )


def test_phased_orchestrator_runs_all_phases_and_populates_scores():
    h1, h2 = _hyp("H1"), _hyp("H2")

    investigator_client = MockClient(
        name="mock-investigator",
        structured_responses=[
            HypothesisGenerationOutput(hypotheses=[h1, h2]),  # generate
            HypothesisGenerationOutput(hypotheses=[h1, h2]),  # revise
            ScoreBundle(scores=[
                HypothesisScore(hypothesis_id="H1", score=0.7, rationale="r"),
                HypothesisScore(hypothesis_id="H2", score=0.3, rationale="r"),
            ]),
        ],
    )
    critic_client = MockClient(
        name="mock-critic",
        structured_responses=[
            CritiqueBundle(critiques=[
                HypothesisCritique(
                    hypothesis_id="H1",
                    strengths=["s"], weaknesses=["w"],
                    overlooked_evidence=[], suggested_revisions=[],
                    overall_assessment="ok",
                ),
                HypothesisCritique(
                    hypothesis_id="H2",
                    strengths=[], weaknesses=["w"],
                    overlooked_evidence=[], suggested_revisions=[],
                    overall_assessment="weak",
                ),
            ]),
            ScoreBundle(scores=[
                HypothesisScore(hypothesis_id="H1", score=0.6, rationale="r"),
                HypothesisScore(hypothesis_id="H2", score=0.2, rationale="r"),
            ]),
        ],
    )

    investigator = Agent(
        name="investigator",
        role="investigator",
        client=investigator_client,
        system_prompt_template="system/investigator.j2",
    )
    critic = Agent(
        name="forensic_analyst",
        role="critic",
        client=critic_client,
        system_prompt_template="system/forensic_analyst.j2",
    )

    result = PhasedOrchestrator().run(_minimal_case(), [investigator, critic])

    assert len(result) == 2
    h1_result = next(h for h in result if h.id == "H1")
    assert {s.agent_name for s in h1_result.agent_scores} == {
        "investigator", "forensic_analyst"
    }
    h1_scores = {s.agent_name: s.score for s in h1_result.agent_scores}
    assert h1_scores["investigator"] == 0.7
    assert h1_scores["forensic_analyst"] == 0.6


def test_phased_orchestrator_requires_investigator():
    critic = Agent(
        name="c",
        role="critic",
        client=MockClient(),
        system_prompt_template="system/forensic_analyst.j2",
    )
    with pytest.raises(ValueError, match="investigator"):
        PhasedOrchestrator().run(_minimal_case(), [critic])


def test_phased_orchestrator_requires_at_least_one_critic():
    investigator = Agent(
        name="i",
        role="investigator",
        client=MockClient(),
        system_prompt_template="system/investigator.j2",
    )
    with pytest.raises(ValueError, match="critic"):
        PhasedOrchestrator().run(_minimal_case(), [investigator])