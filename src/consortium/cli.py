"""Cold-case pipeline CLI.

The Typer app defined here is registered as the `consortium-run` console
script via pyproject.toml. The thin wrapper at scripts/run_pipeline.py
invokes it for local development.
"""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from consortium.io import (
    build_agents_from_config,
    build_ceg_client_from_config,
    load_case_from_dir,
    load_pipeline_config,
    make_run_directory,
    try_render_ceg_svg,
    write_ceg,
    write_ranked_hypotheses,
)
from consortium.orchestrators import PhasedOrchestrator
from consortium.pipeline import generate_ceg, run_consortium
from consortium.schemas import RankedHypotheses

app = typer.Typer(
    help="Cold-case LLM consortium pipeline.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def run(
    case: Path = typer.Option(
        ..., "--case", "-c",
        help="Path to the case directory (case.yaml + narrative.md + evidence.json).",
        exists=True, file_okay=False, dir_okay=True, resolve_path=True,
    ),
    config: Path = typer.Option(
        Path("configs/pipelines/poc_default.yaml"), "--config", "-f",
        help="Path to the pipeline configuration YAML.",
        exists=True, file_okay=True, dir_okay=False, resolve_path=True,
    ),
    out: Path = typer.Option(
        Path("outputs/runs"), "--out", "-o",
        help="Base directory for run outputs.",
    ),
    skip_ceg: bool = typer.Option(
        False, "--skip-ceg",
        help="Skip the CEG stage. Useful for iterating on the consortium.",
    ),
) -> None:
    """Run the pipeline end-to-end on a single case."""
    console.print(f"[bold cyan]Loading case[/bold cyan] {case}")
    case_obj = load_case_from_dir(case)
    console.print(
        f"  -> {case_obj.metadata.case_name} "
        f"({len(case_obj.evidence)} evidence items)"
    )

    console.print(f"[bold cyan]Loading config[/bold cyan] {config}")
    cfg = load_pipeline_config(config)
    agents = build_agents_from_config(cfg)
    console.print(f"  -> {len(agents)} agents:")
    for a in agents:
        console.print(f"     - {a.name} ({a.role}) on {a.client.name}")

    run_dir = make_run_directory(out, case_obj.metadata.case_id)
    console.print(f"[bold cyan]Run directory[/bold cyan] {run_dir}")

    console.print("\n[bold green]Stage 1: Consortium[/bold green]")
    max_hypotheses = cfg.get("pipeline", {}).get("max_hypotheses", 6)
    ranked = run_consortium(
        case_obj,
        agents,
        PhasedOrchestrator(),
        max_hypotheses=max_hypotheses,
    )
    hypotheses_path = write_ranked_hypotheses(ranked, run_dir)
    console.print(f"  -> wrote {hypotheses_path.name}")
    _print_ranked_table(ranked)

    if skip_ceg or not cfg.get("pipeline", {}).get("run_ceg_stage", True):
        console.print("\n[yellow]CEG stage skipped[/yellow]")
        console.print(f"\n[bold green]Done.[/bold green] Outputs in {run_dir}")
        return

    console.print("\n[bold green]Stage 2: CEG generation[/bold green]")
    ceg_client = build_ceg_client_from_config(cfg)
    console.print(f"  -> using {ceg_client.name}")

    top_hypothesis = ranked.hypotheses[0]
    ceg = generate_ceg(case_obj, top_hypothesis, ceg_client)

    paths = write_ceg(ceg, run_dir, also_dot=True)
    console.print(f"  -> wrote {paths['json'].name}, {paths['dot'].name}")

    svg_path = try_render_ceg_svg(ceg, run_dir)
    if svg_path is not None:
        console.print(f"  -> wrote {svg_path.name}")
    else:
        console.print("  -> [dim]SVG render skipped (Graphviz not on PATH).[/dim]")

    console.print(f"\n[bold green]Done.[/bold green] Outputs in {run_dir}")


@app.command()
def info(
    case: Path = typer.Option(
        ..., "--case", "-c",
        help="Path to the case directory.",
        exists=True, file_okay=False, dir_okay=True,
    ),
) -> None:
    """Print a summary of a case without running the pipeline."""
    case_obj = load_case_from_dir(case)
    console.print(
        f"[bold]{case_obj.metadata.case_name}[/bold] "
        f"({case_obj.metadata.case_id})"
    )
    console.print(f"Status: {case_obj.metadata.status or 'n/a'}")
    if case_obj.metadata.victim:
        v = case_obj.metadata.victim
        console.print(f"Victim: {v.name} ({v.age_at_death or '?'})")
    console.print(f"Evidence items: {len(case_obj.evidence)}\n")

    table = Table(title="Evidence")
    table.add_column("ID", style="cyan")
    table.add_column("Type")
    table.add_column("Reliability")
    table.add_column("Title")
    for e in case_obj.evidence:
        table.add_row(e.id, e.type, e.reliability, e.title)
    console.print(table)


def _print_ranked_table(ranked: RankedHypotheses) -> None:
    table = Table(
        title=f"Ranked hypotheses for {ranked.case_id}",
        show_lines=False,
    )
    table.add_column("Rank", justify="right", style="cyan", no_wrap=True)
    table.add_column("ID", style="bold")
    table.add_column("Confidence", justify="right")
    table.add_column("Summary")

    for h in ranked.hypotheses:
        summary = h.one_line_summary
        if len(summary) > 80:
            summary = summary[:77] + "..."
        table.add_row(
            str(h.rank),
            h.id,
            f"{h.confidence_score:.3f}" if h.confidence_score is not None else "—",
            summary,
        )
    console.print(table)