"""Audit logging for pipeline runs.

Writes structured events to <run_dir>/events.jsonl and saves large
artefacts (full bad LLM outputs, tracebacks) to <run_dir>/errors/.

The active RunLogger is held in a contextvar so downstream code can log
without having a logger explicitly passed to it. The CLI registers the
logger at run start and clears it on exit.
"""
from __future__ import annotations

import contextvars
import json
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional


class RunLogger:
    """Per-run audit logger.

    Each call to `event()` appends one JSON object to events.jsonl. Larger
    error artefacts (full bad model outputs, tracebacks) are saved to the
    errors/ subdirectory and referenced by relative path from event records.
    """

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self.errors_dir = self.run_dir / "errors"
        self.errors_dir.mkdir(exist_ok=True)
        self._artifact_counter = 0

    def event(self, event_type: str, **fields: Any) -> None:
        """Append a structured event to events.jsonl."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            **fields,
        }
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def save_artifact(self, name: str, content: str) -> str:
        """Save a text artifact under errors/ and return its relative path.

        Files are numbered in the order they're saved so the chronology
        of failures is preserved.
        """
        self._artifact_counter += 1
        safe = name.replace("/", "_").replace(" ", "_").replace("\\", "_")
        filename = f"{self._artifact_counter:03d}_{safe}.txt"
        path = self.errors_dir / filename
        path.write_text(content, encoding="utf-8")
        return str(path.relative_to(self.run_dir))

    @contextmanager
    def stage(self, name: str, **fields: Any) -> Generator[None, None, None]:
        """Context manager that logs stage start/end and captures exceptions."""
        started = datetime.now()
        self.event("stage_start", stage=name, **fields)
        try:
            yield
        except Exception as e:
            artefact = self.save_artifact(
                f"exception_{name}",
                traceback.format_exc(),
            )
            self.event(
                "stage_error",
                stage=name,
                duration_seconds=(datetime.now() - started).total_seconds(),
                error_type=type(e).__name__,
                error_message=str(e)[:1000],
                traceback_artifact=artefact,
                **fields,
            )
            raise
        else:
            self.event(
                "stage_end",
                stage=name,
                duration_seconds=(datetime.now() - started).total_seconds(),
                **fields,
            )


# Context-local active logger.
_active_logger: contextvars.ContextVar[Optional[RunLogger]] = contextvars.ContextVar(
    "run_logger", default=None
)


def set_active_logger(logger: Optional[RunLogger]) -> None:
    _active_logger.set(logger)


def get_active_logger() -> Optional[RunLogger]:
    return _active_logger.get()