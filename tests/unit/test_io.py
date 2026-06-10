"""Tests for IO helpers (case loading, config building, output writing)."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from consortium.clients import OllamaClient
from consortium.io import (
    build_agents_from_config,
    build_ceg_client_from_config,
    load_case_from_dir,
    load_pipeline_config,
    make_run_directory,
    write_ceg,
    write_ranked_hypotheses,
)
from consortium.schemas import (
    CEGEdge,
    CEGNode,
    CEGNodeType,
    ChainEventGraph,
    Hypothesis,
    RankedHypotheses,
)


CASE_DIR = Path(__file__).resolve().parents[2] / "cases" / "toy" / "cold_case_001"
DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[2]
    / "configs" / "pipelines" / "poc_default.yaml"
)


def test_load_case_from_dir_loads_toy_case():
    case = load_case_from_dir(CASE_DIR)
    assert case.metadata.case_id == "cold_case_001"
    assert len(case.evidence) == 13


def test_build_agents_from_config_produces_three_agents():
    config = load_pipeline_config(DEFAULT_CONFIG)
    agents = build_agents_from_config(config)
    assert len(agents) == 3
    assert agents[0].role == "investigator"
    assert all(a.role == "critic" for a in agents[1:])
    assert all(isinstance(a.client, OllamaClient) for a in agents)


def test_build_ceg_client_from_config_returns_ollama_client():
    config = load_pipeline_config(DEFAULT_CONFIG)
    client = build_ceg_client_from_config(config)
    assert isinstance(client, OllamaClient)


def test_make_run_directory_creates_timestamped_dir(tmp_path: Path):
    run_dir = make_run_directory(tmp_path, "case_x", timestamp="20260610_120000")
    assert run_dir == tmp_path / "20260610_120000_case_x"
    assert run_dir.exists()
    assert run_dir.is_dir()


def test_write_ranked_hypotheses_produces_readable_json(tmp_path: Path):
    ranked = RankedHypotheses(
        case_id="c1",
        hypotheses=[
            Hypothesis(
                id="H1",
                one_line_summary="Summary",
                narrative="N",
                confidence_score=0.7,
                rank=1,
            )
        ],
    )
    path = write_ranked_hypotheses(ranked, tmp_path)
    data = json.loads(path.read_text())
    assert data["case_id"] == "c1"
    assert data["hypotheses"][0]["id"] == "H1"


def test_write_ceg_produces_json_and_dot(tmp_path: Path):
    ceg = ChainEventGraph(
        case_id="c1", hypothesis_id="H1",
        nodes=[
            CEGNode(id="N0", type=CEGNodeType.ROOT, description="r"),
            CEGNode(id="N1", type=CEGNodeType.LEAF, description="l"),
        ],
        edges=[
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="e", conditional_probability=1.0),
        ],
        stages=[],
        root_node_id="N0",
        leaf_node_ids=["N1"],
    )
    paths = write_ceg(ceg, tmp_path)
    assert paths["json"].exists()
    assert paths["dot"].exists()
    assert "digraph" in paths["dot"].read_text()