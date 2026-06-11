"""CEG generation stage with structural-validation retry."""
from __future__ import annotations

from typing import Optional

from consortium.ceg.validator import (
    CEGValidationError,
    validate_ceg_evidence_grounding,
    validate_ceg_structure,
)
from consortium.clients.base import LLMClient, Message
from consortium.schemas.case import Case
from consortium.schemas.ceg import ChainEventGraph
from consortium.schemas.hypothesis import Hypothesis
from consortium.utils.audit import get_active_logger
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
    max_structural_retries: int = 2,
) -> ChainEventGraph:
    """Generate a CEG from a hypothesis with two layers of retry.

    Layer 1 (inside `client.chat_structured`): retries on JSON parse
    errors or Pydantic schema validation failures.

    Layer 2 (here): retries on structural validation failures — graph
    constraints that Pydantic can't enforce (probabilities summing to 1,
    orphaned nodes, leaves with outgoing edges, etc.).

    When a structural failure occurs and retries remain, the failed CEG
    is fed back to the model along with the list of structural problems,
    so the model can correct itself.
    """
    system = render_template(system_prompt_template)
    user = render_template(
        user_prompt_template,
        case=case,
        evidence=case.evidence,
        hypothesis=hypothesis,
    )

    messages: list[Message] = [
        Message(role="system", content=system),
        Message(role="user", content=user),
    ]

    logger = get_active_logger()
    last_problems: list[str] = []

    for attempt in range(max_structural_retries + 1):
        ceg = client.chat_structured(
            messages,
            response_model=ChainEventGraph,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if not validate:
            return ceg

        problems = validate_ceg_structure(
            ceg, probability_tolerance=probability_tolerance
        )
        problems.extend(validate_ceg_evidence_grounding(ceg, case))

        if not problems:
            if logger and attempt > 0:
                logger.event(
                    "ceg_structural_retry_succeeded",
                    attempts_taken=attempt + 1,
                )
            return ceg

        last_problems = problems
        if logger:
            logger.event(
                "ceg_structural_validation_failed",
                attempt=attempt + 1,
                problem_count=len(problems),
                problems=problems,
            )

        if attempt < max_structural_retries:
            messages = messages + [
                Message(
                    role="assistant",
                    content=ceg.model_dump_json(indent=2),
                ),
                Message(
                    role="user",
                    content=(
                        "Your previous CEG had the following structural "
                        "problems:\n"
                        + "\n".join(f"- {p}" for p in problems)
                        + "\n\nPlease regenerate the CEG. The most common "
                        "fixes are:\n"
                        "- Add the missing outgoing edges from any non-leaf "
                        "  node (every non-leaf needs at least one).\n"
                        "- Adjust conditional_probability values so the "
                        "  outgoing edges from each non-leaf node sum to "
                        "  EXACTLY 1.0.\n"
                        "- Change the type of any leaf that has outgoing "
                        "  edges to 'situation', OR remove its outgoing "
                        "  edges if it really is terminal.\n"
                        "- Ensure root_node_id refers to the node typed 'root'.\n"
                        "\nOutput ONLY the corrected ChainEventGraph JSON."
                    ),
                ),
            ]
            continue

        raise CEGValidationError(
            f"CEG structural validation failed after "
            f"{max_structural_retries + 1} attempt(s). Final problems:\n"
            + "\n".join(f"  - {p}" for p in last_problems)
        )

    raise RuntimeError("generate_ceg loop exited unexpectedly")