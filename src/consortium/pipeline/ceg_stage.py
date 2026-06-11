"""CEG generation stage with repair and structural-validation retry."""
from __future__ import annotations

from typing import Optional

from consortium.ceg.repair import normalize_outgoing_probabilities
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
    """Generate a CEG from a hypothesis with repair + retry.

    Each attempt:
    1. Calls the LLM (which has its own JSON/schema retry inside).
    2. Repair pass: normalises outgoing probabilities to sum to 1.0
       where the model's arithmetic was close but not exact.
    3. Structural validation: catches issues repair can't fix
       (orphaned nodes, leaves with outgoing edges, dangling edge
       references, cycles).
    4. If still invalid and retries remain, the failed CEG and
       structural problems are fed back to the model for another attempt.
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

        # Repair pass: normalise probabilities.
        ceg, repair_report = normalize_outgoing_probabilities(
            ceg, tolerance=probability_tolerance
        )
        if logger and not repair_report.is_empty():
            logger.event(
                "ceg_probabilities_normalized",
                attempt=attempt + 1,
                normalizations=[
                    {
                        "node_id": r.node_id,
                        "original_sum": r.original_sum,
                        "edge_count": r.edge_count,
                        "edge_ids": r.edge_ids,
                    }
                    for r in repair_report.normalizations
                ],
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
                        + "\n\nPlease regenerate the CEG. Probability sums "
                        "will be auto-normalised, but other structural "
                        "constraints must be satisfied:\n"
                        "- Every non-leaf node must have outgoing edges.\n"
                        "- Leaf nodes must have NO outgoing edges.\n"
                        "- Every edge must reference existing node IDs.\n"
                        "- The graph must be acyclic.\n"
                        "- root_node_id must refer to the node typed 'root'.\n"
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