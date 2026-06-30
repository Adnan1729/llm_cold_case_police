"""CEG generation stage: LLM event tree -> cegpy AHC -> ChainEventGraph.

This stage replaces the previous direct LLM-generates-CEG approach with
a two-phase neurosymbolic split:

1. The LLM produces an EventTree — a strict tree, no equivalence-class
   staging. This is a simpler structured-output task than producing a
   full CEG, and consequently more reliable on small models.

2. Deterministic code converts the EventTree into a ChainEventGraph by
   submitting it to cegpy for AHC stage identification. When cegpy's
   AHC has nothing to merge (singleton-hyperstage case), the converter
   falls through to a trivial-staging CEG. Either way, probabilities
   are normalised and the result is structurally validated.

Three layers of defence remain in place:

- Layer 1 (inside `client.chat_structured`): JSON-parse and Pydantic
  schema retries on the LLM call.
- Layer 2 (here): structural-validation retries on the event tree.
  When the tree fails tree-shape, reachability, or probability-sum
  checks, the failed tree and the validator's problems are fed back to
  the model for another attempt. This is the same mechanism as before
  but applied to a stricter schema so more failure modes get caught.
- Layer 3 (in the conversion): probability normalisation on the CEG.

Audit events emitted by this stage:
- `event_tree_validation_failed` — when a tree fails structural checks.
- `event_tree_retry_succeeded` — when a retry produces a valid tree.
- `ceg_conversion_completed` — with the CegpyConversionReport contents.
- `ceg_probabilities_normalized` — from the normalisation pass inside
  the conversion (existing event, now sourced from the converter).
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from consortium.ceg.event_tree_validator import (
    EventTreeValidationError,
    validate_event_tree_evidence_grounding,
    validate_event_tree_structure,
)
from consortium.ceg.tree_to_ceg import event_tree_to_ceg
from consortium.clients.base import LLMClient, Message
from consortium.schemas.case import Case
from consortium.schemas.ceg import ChainEventGraph
from consortium.schemas.event_tree import EventTree
from consortium.schemas.hypothesis import Hypothesis
from consortium.utils.audit import get_active_logger
from consortium.utils.prompts import render_template

from consortium.ceg.event_tree_repair import repair_event_tree


def generate_ceg(
    case: Case,
    hypothesis: Hypothesis,
    client: LLMClient,
    *,
    system_prompt_template: str = "system/event_tree_generator.j2",
    user_prompt_template: str = "event_tree/generate_from_hypothesis.j2",
    temperature: float = 0.2,
    max_tokens: Optional[int] = 4096,
    validate: bool = True,
    probability_tolerance: float = 1e-4,
    max_structural_retries: int = 2,
    pseudo_count: int = 1000,
) -> ChainEventGraph:
    """Generate a CEG from a hypothesis via the EventTree pipeline.

    The function name and signature are preserved from the previous
    version so the CLI and other callers continue to work unchanged.

    Args:
        case: The case the hypothesis explains.
        hypothesis: Usually the top-ranked Hypothesis from the consortium.
        client: An LLMClient.
        system_prompt_template: System prompt under prompts/.
        user_prompt_template: User prompt under prompts/.
        temperature: Low default (0.2) — structural consistency over creativity.
        max_tokens: Cap on response length.
        validate: If True, validate the tree and reject invalid ones.
        probability_tolerance: Tolerance for probability-sum checks.
        max_structural_retries: Maximum retries on structural failures.
        pseudo_count: Pseudo-observation budget for cegpy AHC.

    Returns:
        A ChainEventGraph produced via EventTree -> cegpy.

    Raises:
        EventTreeValidationError: if validation exhausts all retries.
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
        tree = client.chat_structured(
            messages,
            response_model=EventTree,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Repair pass: drop orphans, expand DAG to tree, normalise probs.
        # Common 3B-model failure modes are fixable without an LLM round-trip.
        tree, repair_report = repair_event_tree(
            tree, probability_tolerance=probability_tolerance
        )
        if logger and not repair_report.is_empty():
            logger.event(
                "event_tree_repaired",
                attempt=attempt + 1,
                orphans_dropped=repair_report.orphans_dropped,
                edges_dropped=repair_report.edges_dropped_with_orphans,
                duplicated_nodes=repair_report.duplicated_nodes,
                probability_normalizations=repair_report.probability_normalizations,
                expansion_skipped_reason=repair_report.expansion_skipped_reason,
            )

        if not validate:
            return _convert_and_log(
                tree, case, probability_tolerance, pseudo_count, logger
            )

        problems = validate_event_tree_structure(
            tree, probability_tolerance=probability_tolerance
        )
        problems.extend(validate_event_tree_evidence_grounding(tree, case))

        if not problems:
            if logger and attempt > 0:
                logger.event(
                    "event_tree_retry_succeeded",
                    attempts_taken=attempt + 1,
                )
            return _convert_and_log(
                tree, case, probability_tolerance, pseudo_count, logger
            )

        last_problems = problems
        if logger:
            logger.event(
                "event_tree_validation_failed",
                attempt=attempt + 1,
                problem_count=len(problems),
                problems=problems,
            )

        if attempt < max_structural_retries:
            messages = messages + [
                Message(
                    role="assistant",
                    content=tree.model_dump_json(indent=2),
                ),
                Message(
                    role="user",
                    content=(
                        "Your previous event tree had the following "
                        "structural problems:\n"
                        + "\n".join(f"- {p}" for p in problems)
                        + "\n\nPlease regenerate the event tree. "
                        "Common fixes:\n"
                        "- Ensure every non-root node has EXACTLY ONE "
                        "incoming edge (this is a tree).\n"
                        "- Adjust conditional_probability values so the "
                        "outgoing edges from each non-leaf node sum to "
                        "EXACTLY 1.0.\n"
                        "- Every edge's from_node and to_node must "
                        "reference an existing node ID.\n"
                        "- The root_node_id must refer to a node in the "
                        "tree and that node must have no incoming edges.\n"
                        "- Every node must be reachable from the root.\n"
                        "\nOutput ONLY the corrected EventTree JSON."
                    ),
                ),
            ]
            continue

        raise EventTreeValidationError(
            f"Event tree structural validation failed after "
            f"{max_structural_retries + 1} attempt(s). Final problems:\n"
            + "\n".join(f"  - {p}" for p in last_problems)
        )

    raise RuntimeError("generate_ceg loop exited unexpectedly")


def _convert_and_log(
    tree: EventTree,
    case: Case,
    probability_tolerance: float,
    pseudo_count: int,
    logger,
) -> ChainEventGraph:
    """Convert a validated EventTree to a CEG and emit audit events."""
    ceg, report = event_tree_to_ceg(
        tree,
        pseudo_count=pseudo_count,
        case_id=case.metadata.case_id,
        hypothesis_id=tree.hypothesis_id,
        probability_tolerance=probability_tolerance,
    )

    if logger:
        # Serialise normalisations to plain dicts for clean JSON in the log
        report_dict = asdict(report)
        report_dict["normalizations"] = [
            asdict(n) for n in report.normalizations
        ]
        logger.event("ceg_conversion_completed", **report_dict)

        if report.normalizations:
            logger.event(
                "ceg_probabilities_normalized",
                source="event_tree_to_ceg",
                normalizations=[asdict(n) for n in report.normalizations],
            )

        if report.ahc_fallback_triggered:
            logger.event(
                "ceg_ahc_fallback_triggered",
                reason=report.ahc_fallback_reason,
            )

    return ceg