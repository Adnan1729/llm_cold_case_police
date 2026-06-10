"""CEG generation stage.

Takes the top-ranked hypothesis and the case, calls an LLM to produce a
ChainEventGraph, validates it, and returns the result.

A reasoning model (DeepSeek-R1-Distill, QwQ) is recommended here because
CEG construction requires structural reasoning about branches and
probabilities — exactly what reasoning models are tuned for.
"""
from __future__ import annotations

from typing import Optional

from consortium.ceg.validator import assert_ceg_valid
from consortium.clients.base import LLMClient, Message
from consortium.schemas.case import Case
from consortium.schemas.ceg import ChainEventGraph
from consortium.schemas.hypothesis import Hypothesis
from consortium.utils.prompts import render_template


def generate_ceg(
    case: Case,
    hypothesis: Hypothesis,
    client: LLMClient,
    *,
    system_prompt_template: str = "system/ceg_generator.j2",
    user_prompt_template: str = "ceg/generate_from_hypothesis.j2",
    temperature: float = 0.2,
    max_tokens: Optional[int] = 4096,
    validate: bool = True,
    probability_tolerance: float = 1e-4,
) -> ChainEventGraph:
    """Generate a CEG from a hypothesis.

    Args:
        case: The case the hypothesis explains.
        hypothesis: Usually the top-ranked Hypothesis from the consortium.
        client: An LLMClient. Reasoning models are recommended.
        system_prompt_template: Path to the system prompt under prompts/.
        user_prompt_template: Path to the user prompt under prompts/.
        temperature: Low default (0.2) — structural consistency over creativity.
        max_tokens: Cap on response length.
        validate: If True, validate the CEG before returning.
        probability_tolerance: Tolerance for outgoing-probability sums.
            Slightly loose (1e-4) because LLMs round probabilities.

    Returns:
        A ChainEventGraph object, validated if `validate=True`.

    Raises:
        ValueError: if the LLM produces malformed output.
        CEGValidationError: if `validate=True` and the CEG fails checks.
    """
    system = render_template(system_prompt_template)
    user = render_template(
        user_prompt_template,
        case=case,
        evidence=case.evidence,
        hypothesis=hypothesis,
    )

    ceg = client.chat_structured(
        [
            Message(role="system", content=system),
            Message(role="user", content=user),
        ],
        response_model=ChainEventGraph,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if validate:
        assert_ceg_valid(
            ceg, case, probability_tolerance=probability_tolerance
        )

    return ceg