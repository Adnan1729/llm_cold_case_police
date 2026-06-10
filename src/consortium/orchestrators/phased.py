"""Phase-based orchestrator: generate → critique → revise → score.

Runs the consortium as a deterministic sequence of structured LLM calls,
one phase per call per agent. Does not use any agent-framework library.
This is the baseline implementation against which framework-based
alternatives (AutoGen, LangGraph) will be compared.
"""
from __future__ import annotations

from consortium.agents.base import Agent
from consortium.clients.base import Message
from consortium.orchestrators.base import ConsortiumOrchestrator
from consortium.schemas.case import Case
from consortium.schemas.debate import (
    CritiqueBundle,
    HypothesisCritique,
    HypothesisGenerationOutput,
    HypothesisScore,
    ScoreBundle,
)
from consortium.schemas.hypothesis import AgentScore, Hypothesis
from consortium.utils.prompts import render_template


# Phase-specific temperatures. Generation needs some creativity;
# critique, revision, and especially scoring need consistency.
_GENERATE_TEMPERATURE = 0.6
_CRITIQUE_TEMPERATURE = 0.2
_REVISE_TEMPERATURE = 0.3
_SCORE_TEMPERATURE = 0.1


class PhasedOrchestrator(ConsortiumOrchestrator):
    """Deterministic phase-based orchestrator.

    Requires exactly one Agent with role='investigator' and at least one
    Agent with role='critic'. Other roles are ignored.
    """

    def run(
        self,
        case: Case,
        agents: list[Agent],
        *,
        max_hypotheses: int = 6,
    ) -> list[Hypothesis]:
        investigator, critics = self._split_agents(agents)

        hypotheses = self._phase_generate(case, investigator, max_hypotheses)

        critiques_by_critic: dict[str, list[HypothesisCritique]] = {}
        for critic in critics:
            bundle = self._phase_critique(case, critic, hypotheses)
            critiques_by_critic[critic.name] = bundle.critiques

        hypotheses = self._phase_revise(
            case, investigator, hypotheses, critiques_by_critic
        )

        scores_by_agent: dict[str, list[HypothesisScore]] = {}
        for agent in [investigator] + critics:
            bundle = self._phase_score(case, agent, hypotheses)
            scores_by_agent[agent.name] = bundle.scores

        return self._attach_scores(hypotheses, scores_by_agent)

    @staticmethod
    def _split_agents(agents: list[Agent]) -> tuple[Agent, list[Agent]]:
        investigators = [a for a in agents if a.role == "investigator"]
        critics = [a for a in agents if a.role == "critic"]
        if len(investigators) != 1:
            raise ValueError(
                f"PhasedOrchestrator requires exactly one investigator agent; "
                f"got {len(investigators)}."
            )
        if not critics:
            raise ValueError(
                "PhasedOrchestrator requires at least one critic agent."
            )
        return investigators[0], critics

    @staticmethod
    def _messages(system: str, user: str) -> list[Message]:
        return [
            Message(role="system", content=system),
            Message(role="user", content=user),
        ]

    def _phase_generate(
        self,
        case: Case,
        investigator: Agent,
        max_hypotheses: int,
    ) -> list[Hypothesis]:
        system = render_template(investigator.system_prompt_template)
        user = render_template(
            "consortium/initial_generation.j2",
            case=case,
            evidence=case.evidence,
            max_hypotheses=max_hypotheses,
        )
        output = investigator.client.chat_structured(
            self._messages(system, user),
            response_model=HypothesisGenerationOutput,
            temperature=_GENERATE_TEMPERATURE,
            max_tokens=investigator.default_max_tokens,
        )
        return list(output.hypotheses)[:max_hypotheses]

    def _phase_critique(
        self,
        case: Case,
        critic: Agent,
        hypotheses: list[Hypothesis],
    ) -> CritiqueBundle:
        system = render_template(critic.system_prompt_template)
        user = render_template(
            "consortium/critique.j2",
            case=case,
            evidence=case.evidence,
            hypotheses=hypotheses,
        )
        return critic.client.chat_structured(
            self._messages(system, user),
            response_model=CritiqueBundle,
            temperature=_CRITIQUE_TEMPERATURE,
            max_tokens=critic.default_max_tokens,
        )

    def _phase_revise(
        self,
        case: Case,
        investigator: Agent,
        hypotheses: list[Hypothesis],
        critiques_by_critic: dict[str, list[HypothesisCritique]],
    ) -> list[Hypothesis]:
        system = render_template(investigator.system_prompt_template)
        user = render_template(
            "consortium/revise.j2",
            case=case,
            evidence=case.evidence,
            hypotheses=hypotheses,
            critiques_by_critic=critiques_by_critic,
        )
        output = investigator.client.chat_structured(
            self._messages(system, user),
            response_model=HypothesisGenerationOutput,
            temperature=_REVISE_TEMPERATURE,
            max_tokens=investigator.default_max_tokens,
        )
        return list(output.hypotheses)

    def _phase_score(
        self,
        case: Case,
        agent: Agent,
        hypotheses: list[Hypothesis],
    ) -> ScoreBundle:
        system = render_template(agent.system_prompt_template)
        user = render_template(
            "consortium/score.j2",
            case=case,
            evidence=case.evidence,
            hypotheses=hypotheses,
        )
        return agent.client.chat_structured(
            self._messages(system, user),
            response_model=ScoreBundle,
            temperature=_SCORE_TEMPERATURE,
            max_tokens=agent.default_max_tokens,
        )

    @staticmethod
    def _attach_scores(
        hypotheses: list[Hypothesis],
        scores_by_agent: dict[str, list[HypothesisScore]],
    ) -> list[Hypothesis]:
        result: list[Hypothesis] = []
        for h in hypotheses:
            agent_scores: list[AgentScore] = []
            for agent_name, score_list in scores_by_agent.items():
                for s in score_list:
                    if s.hypothesis_id == h.id:
                        agent_scores.append(
                            AgentScore(
                                agent_name=agent_name,
                                score=s.score,
                                rationale=s.rationale,
                            )
                        )
            result.append(h.model_copy(update={"agent_scores": agent_scores}))
        return result