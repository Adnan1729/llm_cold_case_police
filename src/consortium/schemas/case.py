"""Case-level schemas.

Mirrors `case.yaml` plus carries the loaded narrative and structured
evidence list. A Case object is the input to the pipeline.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from consortium.schemas.evidence import EvidenceCard


def _coerce_temporal_to_string(value):
    """Convert date/datetime objects to ISO 8601 strings.

    YAML auto-parses date literals (e.g. 2022-11-07) into datetime.date
    objects. This coercion lets the schema continue accepting strings as
    the canonical type while tolerating that quirk.
    """
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class Victim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    age_at_death: Optional[int] = None
    occupation: Optional[str] = None


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str
    date_discovered: Optional[str] = None
    estimated_window_of_death: Optional[str] = None
    cause_of_death: Optional[str] = None

    @field_validator(
        "date_discovered", "estimated_window_of_death", mode="before"
    )
    @classmethod
    def _coerce_dates(cls, v):
        return _coerce_temporal_to_string(v)


class CaseMetadata(BaseModel):
    """Top-level metadata for a case, mirroring case.yaml."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    case_name: str
    jurisdiction: Optional[str] = None
    status: Optional[str] = None
    designated_for_evaluation: bool = False

    victim: Optional[Victim] = None
    incident: Optional[Incident] = None

    case_age_years: Optional[float] = None
    case_dormant_since: Optional[str] = None

    @field_validator("case_dormant_since", mode="before")
    @classmethod
    def _coerce_dates(cls, v):
        return _coerce_temporal_to_string(v)


class Case(BaseModel):
    """A fully loaded case: metadata + narrative + evidence."""

    model_config = ConfigDict(extra="forbid")

    metadata: CaseMetadata
    narrative: str
    evidence: list[EvidenceCard]