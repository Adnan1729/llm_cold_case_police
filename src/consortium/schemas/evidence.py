"""Evidence-related schemas.

The EvidenceCard is the structural contract for a single piece of evidence in
a case. Every component downstream — agents, validators, aggregators, UI —
receives evidence in this shape.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EvidenceType(str, Enum):
    WITNESS_STATEMENT = "witness_statement"
    FORENSIC_REPORT = "forensic_report"
    DIGITAL_RECORD = "digital_record"
    PHYSICAL_EVIDENCE = "physical_evidence"
    FINANCIAL_RECORD = "financial_record"
    OTHER = "other"


class Reliability(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceCard(BaseModel):
    """A single piece of evidence in a case.

    The `id` is the canonical reference used by hypotheses and CEGs to cite
    this item. Once assigned it must not change.

    Reliability is a deliberately coarse three-level scale; reliability_note
    carries the human-readable justification.
    """

    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    id: str = Field(..., description="Stable identifier, e.g. 'E001'.")
    type: EvidenceType
    title: str
    content: str = Field(..., description="The substantive content of the item.")

    source: str = Field(
        ...,
        description="Who or what produced the evidence, including reference numbers.",
    )
    timestamp_referenced: Optional[str] = Field(
        None,
        description=(
            "ISO 8601 datetime, or a range expressed as 'YYYY-MM-DDTHH:MM:SS to "
            "YYYY-MM-DDTHH:MM:SS'. Null if the item is not time-anchored."
        ),
    )
    location_referenced: Optional[str] = None

    reliability: Reliability
    reliability_note: str = Field(
        ..., description="Justification for the reliability rating."
    )
    chain_of_custody_note: str = Field(
        ..., description="Provenance and handling trail for the evidence."
    )