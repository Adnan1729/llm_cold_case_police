"""CEG rendering: ChainEventGraph → DOT → SVG.

The DOT text output is the primary deliverable; it's pure Python with
no external dependencies. SVG rendering is a convenience that requires
the system Graphviz `dot` binary on PATH.
"""
from __future__ import annotations

from pathlib import Path

from consortium.schemas.ceg import CEGNodeType, ChainEventGraph


def ceg_to_dot(ceg: ChainEventGraph) -> str:
    """Serialise a CEG to Graphviz DOT format.

    Node types are styled differently: root is an ellipse, leaves are
    double circles, situations are plain circles.
    """
    title = f"CEG_{ceg.case_id}_{ceg.hypothesis_id}".replace("-", "_")
    lines = [
        f"digraph {title} {{",
        "  rankdir=LR;",
        '  graph [fontname="Helvetica", fontsize=12];',
        '  node [fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9];',
    ]

    for node in ceg.nodes:
        if node.type == CEGNodeType.ROOT.value:
            shape, fill = "ellipse", "lightblue"
        elif node.type == CEGNodeType.LEAF.value:
            shape, fill = "doublecircle", "lightyellow"
        else:
            shape, fill = "circle", "white"

        desc = node.description[:80]
        if len(node.description) > 80:
            desc += "..."
        label = f"{node.id}\\n{_escape(desc)}"

        lines.append(
            f'  "{node.id}" [shape={shape}, style=filled, '
            f'fillcolor={fill}, label="{label}"];'
        )

    for edge in ceg.edges:
        label = (
            f"{_escape(edge.event_label)}\\n"
            f"(p={edge.conditional_probability:.2f})"
        )
        lines.append(
            f'  "{edge.from_node}" -> "{edge.to_node}" '
            f'[label="{label}"];'
        )

    lines.append("}")
    return "\n".join(lines)


def write_ceg_dot(ceg: ChainEventGraph, output_path: Path) -> Path:
    """Write the CEG as a .dot file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(ceg_to_dot(ceg), encoding="utf-8")
    return output_path


def render_ceg_to_svg(ceg: ChainEventGraph, output_path: Path) -> Path:
    """Render the CEG to SVG.

    Requires the `graphviz` Python package AND the system `dot` binary
    on PATH. Raises ImportError or graphviz.ExecutableNotFound otherwise.
    """
    try:
        from graphviz import Source
    except ImportError as e:
        raise ImportError(
            "SVG rendering requires the 'graphviz' Python package. "
            "Install with: pip install graphviz. You also need the "
            "system Graphviz binary; see https://graphviz.org/download/."
        ) from e

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base = output_path.with_suffix("")
    src = Source(ceg_to_dot(ceg), format="svg")
    rendered = Path(src.render(filename=str(base), cleanup=True))
    return rendered


def _escape(s: str) -> str:
    """Escape characters that have special meaning in DOT labels."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")