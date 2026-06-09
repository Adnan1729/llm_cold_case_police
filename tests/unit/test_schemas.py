"""Smoke test: ensure the toy case loads cleanly into the schemas."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from consortium.schemas import Case, CaseMetadata, EvidenceCard


CASE_DIR = Path(__file__).resolve().parents[2] / "cases" / "toy" / "cold_case_001"


def test_case_yaml_loads_into_metadata():
    with open(CASE_DIR / "case.yaml") as f:
        data = yaml.safe_load(f)
    # Strip the artefacts pointer block before validating
    data.pop("artefacts", None)
    metadata = CaseMetadata.model_validate(data)
    assert metadata.case_id == "cold_case_001"
    assert metadata.designated_for_evaluation is True


def test_evidence_json_loads_into_cards():
    with open(CASE_DIR / "evidence.json") as f:
        data = json.load(f)
    cards = [EvidenceCard.model_validate(item) for item in data["evidence_items"]]
    assert len(cards) == 13
    assert {c.id for c in cards} == {f"E{i:03d}" for i in range(1, 14)}


def test_full_case_loads():
    with open(CASE_DIR / "case.yaml") as f:
        meta_data = yaml.safe_load(f)
    meta_data.pop("artefacts", None)
    metadata = CaseMetadata.model_validate(meta_data)

    with open(CASE_DIR / "narrative.md") as f:
        narrative = f.read()

    with open(CASE_DIR / "evidence.json") as f:
        ev_data = json.load(f)
    evidence = [EvidenceCard.model_validate(item) for item in ev_data["evidence_items"]]

    case = Case(metadata=metadata, narrative=narrative, evidence=evidence)
    assert case.metadata.case_name == "Carnaden Antiques Shop Killing"
    assert len(case.evidence) == 13