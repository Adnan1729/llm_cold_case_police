"""I/O helpers: case loading, config loading, output writing.

Used by the CLI to stay thin. Each function is small and unit-testable.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from consortium.agents import Agent
from consortium.ceg import write_ceg_dot
from consortium.clients import OllamaClient
from consortium.clients.base import LLMClient
from consortium.schemas import (
    Case,
    CaseMetadata,
    ChainEventGraph,
    EvidenceCard,
    RankedHypotheses,
)


# ----------------------------------------------------------------------
# Case loading
# ----------------------------------------------------------------------

def load_case_from_dir(case_dir: Path) -> Case:
    """Load a case from a directory containing case.yaml, narrative.md, evidence.json."""
    case_dir = Path(case_dir)

    case_yaml = case_dir / "case.yaml"
    narrative_md = case_dir / "narrative.md"
    evidence_json = case_dir / "evidence.json"

    for path in (case_yaml, narrative_md, evidence_json):
        if not path.exists():
            raise FileNotFoundError(f"Missing required file: {path}")

    with open(case_yaml) as f:
        meta_data = yaml.safe_load(f)
    meta_data.pop("artefacts", None)
    metadata = CaseMetadata.model_validate(meta_data)

    narrative = narrative_md.read_text(encoding="utf-8")

    with open(evidence_json) as f:
        ev_data = json.load(f)
    evidence = [
        EvidenceCard.model_validate(item) for item in ev_data["evidence_items"]
    ]

    return Case(metadata=metadata, narrative=narrative, evidence=evidence)


# ----------------------------------------------------------------------
# Pipeline config loading
# ----------------------------------------------------------------------

def load_pipeline_config(config_path: Path) -> dict[str, Any]:
    """Load and return a pipeline YAML configuration."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def build_agents_from_config(config: dict[str, Any]) -> list[Agent]:
    """Construct Agent objects (with OllamaClient backends) from a pipeline config."""
    ollama_host = config.get("ollama_host", "http://localhost:11434")

    agents: list[Agent] = [_make_agent(config["investigator"], ollama_host)]
    for critic in config.get("critics", []):
        agents.append(_make_agent(critic, ollama_host))

    return agents


def build_ceg_client_from_config(config: dict[str, Any]) -> LLMClient:
    """Construct the LLMClient for CEG generation from a pipeline config."""
    ollama_host = config.get("ollama_host", "http://localhost:11434")
    ceg_cfg = config["ceg_generator"]
    return OllamaClient(
        model=ceg_cfg["model"],
        host=ollama_host,
        name=f"ollama:{ceg_cfg['model']}:ceg",
    )


def _make_agent(spec: dict[str, Any], ollama_host: str) -> Agent:
    client = OllamaClient(
        model=spec["model"],
        host=ollama_host,
        name=f"ollama:{spec['model']}:{spec['name']}",
    )
    return Agent(
        name=spec["name"],
        role=spec["role"],
        client=client,
        system_prompt_template=spec["system_prompt_template"],
        weight=spec.get("weight", 1.0),
        default_max_tokens=spec.get("default_max_tokens"),
    )


# ----------------------------------------------------------------------
# Output writing
# ----------------------------------------------------------------------

def make_run_directory(
    base_dir: Path,
    case_id: str,
    *,
    timestamp: Optional[str] = None,
) -> Path:
    """Create and return a timestamped run directory under base_dir."""
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(base_dir) / f"{timestamp}_{case_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_ranked_hypotheses(ranked: RankedHypotheses, run_dir: Path) -> Path:
    """Write ranked hypotheses as JSON."""
    path = Path(run_dir) / "ranked_hypotheses.json"
    path.write_text(ranked.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_ceg(
    ceg: ChainEventGraph,
    run_dir: Path,
    *,
    also_dot: bool = True,
) -> dict[str, Path]:
    """Write CEG as JSON (and optionally DOT). Returns paths by extension."""
    run_dir = Path(run_dir)
    paths: dict[str, Path] = {}

    json_path = run_dir / "ceg.json"
    json_path.write_text(ceg.model_dump_json(indent=2), encoding="utf-8")
    paths["json"] = json_path

    if also_dot:
        paths["dot"] = write_ceg_dot(ceg, run_dir / "ceg.dot")

    return paths


def try_render_ceg_svg(ceg: ChainEventGraph, run_dir: Path) -> Optional[Path]:
    """Try to render the CEG to SVG. Returns None if Graphviz is unavailable."""
    from consortium.ceg import render_ceg_to_svg

    try:
        from graphviz import ExecutableNotFound
    except ImportError:
        return None

    try:
        return render_ceg_to_svg(ceg, run_dir / "ceg")
    except (ExecutableNotFound, ImportError):
        return None