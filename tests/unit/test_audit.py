"""Tests for the audit logger."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from consortium.utils.audit import (
    RunLogger,
    get_active_logger,
    set_active_logger,
)


def test_run_logger_creates_directories(tmp_path: Path):
    run_dir = tmp_path / "run1"
    RunLogger(run_dir)
    assert run_dir.exists()
    assert (run_dir / "errors").exists()


def test_event_writes_one_jsonl_line_per_call(tmp_path: Path):
    logger = RunLogger(tmp_path / "run")
    logger.event("test_event", foo="bar", n=42)
    logger.event("other_event", x=1.5)

    lines = (tmp_path / "run" / "events.jsonl").read_text().strip().split("\n")
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["event"] == "test_event"
    assert first["foo"] == "bar"
    assert first["n"] == 42
    assert "timestamp" in first

    second = json.loads(lines[1])
    assert second["event"] == "other_event"
    assert second["x"] == 1.5


def test_save_artifact_returns_relative_path_and_writes_content(tmp_path: Path):
    logger = RunLogger(tmp_path / "run")
    rel = logger.save_artifact("test", "some content")
    assert rel.startswith("errors")
    assert "test" in rel
    assert (tmp_path / "run" / rel).read_text() == "some content"


def test_artifacts_numbered_sequentially(tmp_path: Path):
    logger = RunLogger(tmp_path / "run")
    a = logger.save_artifact("a", "x")
    b = logger.save_artifact("b", "y")
    assert "001" in a
    assert "002" in b


def test_stage_context_logs_start_and_end(tmp_path: Path):
    logger = RunLogger(tmp_path / "run")
    with logger.stage("test_stage", foo="bar"):
        pass

    lines = (tmp_path / "run" / "events.jsonl").read_text().strip().split("\n")
    events = [json.loads(line) for line in lines]
    assert [e["event"] for e in events] == ["stage_start", "stage_end"]
    assert events[0]["stage"] == "test_stage"
    assert events[0]["foo"] == "bar"
    assert "duration_seconds" in events[1]


def test_stage_context_logs_error_and_reraises(tmp_path: Path):
    logger = RunLogger(tmp_path / "run")
    with pytest.raises(ValueError, match="boom"):
        with logger.stage("failing_stage"):
            raise ValueError("boom")

    lines = (tmp_path / "run" / "events.jsonl").read_text().strip().split("\n")
    events = [json.loads(line) for line in lines]
    err = next(e for e in events if e["event"] == "stage_error")
    assert err["stage"] == "failing_stage"
    assert err["error_type"] == "ValueError"
    assert "boom" in err["error_message"]
    assert "traceback_artifact" in err


def test_active_logger_contextvar(tmp_path: Path):
    assert get_active_logger() is None

    logger = RunLogger(tmp_path / "run")
    set_active_logger(logger)
    try:
        assert get_active_logger() is logger
    finally:
        set_active_logger(None)

    assert get_active_logger() is None