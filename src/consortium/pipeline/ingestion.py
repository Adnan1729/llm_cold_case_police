"""Ingestion stage: raw case text → structured EvidenceCards.

The ingestion stage is the entry point of the pipeline. It takes
unstructured text (witness transcripts, forensic report extracts, digital
record descriptions, all concatenated) and produces a list of validated
EvidenceCard objects ready for the consortium.

For the POC, the input is plain text. In a scaled-up version, an upstream
parser would handle PDFs, DOCX, etc. and produce the plain text that this
stage consumes.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from consortium.clients.base import LLMClient, Message
from consortium.schemas.evidence import EvidenceCard
from consortium.utils.prompts import render_template


class EvidenceExtractionOutput(BaseModel):
    """Wrapper schema for the LLM's response to evidence extraction.

    The LLM is instructed to return JSON in this shape; the stage unwraps
    the `evidence_items` list before returning to the caller. The wrapper
    is needed because Ollama's structured-output enforcement constrains
    the top-level shape; a bare list at the top level is less reliable
    than a named-field object.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_items: list[EvidenceCard]


def ingest_case_text(
    raw_text: str,
    client: LLMClient,
    *,
    temperature: float = 0.1,
    max_tokens: Optional[int] = 4096,
) -> list[EvidenceCard]:
    """Convert unstructured case material into a list of EvidenceCards.

    Args:
        raw_text: The unstructured case material as a single string.
        client: An LLMClient implementation (Ollama, Mock, vLLM later).
        temperature: Sampling temperature. Low default (0.1) for the
            extraction task — we want consistency over creativity.
        max_tokens: Maximum tokens in the response. Default 4096 fits
            roughly 15–20 evidence items; raise for larger cases.

    Returns:
        A list of validated EvidenceCard objects in the order produced
        by the model.

    Raises:
        ValueError: If the model output cannot be parsed or fails schema
            validation. The error message includes a preview of the raw
            content for debugging.
    """
    system_prompt = render_template("system/ingestion.j2")
    user_prompt = render_template(
        "ingestion/evidence_extraction.j2",
        raw_text=raw_text,
    )

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]

    output = client.chat_structured(
        messages,
        response_model=EvidenceExtractionOutput,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return output.evidence_items