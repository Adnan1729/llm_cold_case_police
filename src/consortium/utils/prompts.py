"""Prompt template loading and rendering.

Templates live in the repo's top-level `prompts/` directory, organised by
stage. They're Jinja2 templates with strict undefined-variable checking
(missing context variables raise rather than rendering as empty strings).

Keeping prompts as files rather than Python string literals means they
are independently version-controllable, reviewable without reading code,
and editable by domain experts who don't want to touch Python.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined


def _default_prompts_dir() -> Path:
    """Resolve the default prompts directory.

    Order of resolution:
    1. CONSORTIUM_PROMPTS_DIR environment variable, if set.
    2. The repo's top-level prompts/ directory, located relative to this file
       (src/consortium/utils/prompts.py -> ../../../prompts).
    """
    env_override = os.environ.get("CONSORTIUM_PROMPTS_DIR")
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parents[3] / "prompts"


def render_template(
    template_name: str,
    *,
    prompts_dir: Optional[Path] = None,
    **context: Any,
) -> str:
    """Render a Jinja2 template by name and return the resulting string.

    Args:
        template_name: Path to the template relative to the prompts
            directory, e.g. 'ingestion/evidence_extraction.j2'.
        prompts_dir: Optional explicit prompts directory. If omitted,
            uses CONSORTIUM_PROMPTS_DIR or the repo default.
        **context: Variables passed to the template for rendering.

    Returns:
        The rendered template as a string.

    Raises:
        jinja2.UndefinedError: If the template references a variable not
            supplied in context.
    """
    resolved_dir = prompts_dir if prompts_dir is not None else _default_prompts_dir()
    env = Environment(
        loader=FileSystemLoader(str(resolved_dir)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )
    template = env.get_template(template_name)
    return template.render(**context)