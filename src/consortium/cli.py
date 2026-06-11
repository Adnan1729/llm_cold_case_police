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
    import traceback as tb

    from consortium.utils.audit import RunLogger, set_active_logger

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

    audit = RunLogger(run_dir)
    set_active_logger(audit)
    audit.event(
        "run_start",
        case_id=case_obj.metadata.case_id,
        case_name=case_obj.metadata.case_name,
        config_path=str(config),
        agents=[
            {"name": a.name, "role": a.role, "model": a.client.name}
            for a in agents
        ],
    )

    try:
        with audit.stage("consortium"):
            console.print("\n[bold green]Stage 1: Consortium[/bold green]")
            max_hypotheses = cfg.get("pipeline", {}).get("max_hypotheses", 6)
            ranked = run_consortium(
                case_obj, agents, PhasedOrchestrator(),
                max_hypotheses=max_hypotheses,
            )
            hypotheses_path = write_ranked_hypotheses(ranked, run_dir)
            console.print(f"  -> wrote {hypotheses_path.name}")
            _print_ranked_table(ranked)

        run_ceg_stage_flag = cfg.get("pipeline", {}).get("run_ceg_stage", True)
        if skip_ceg or not run_ceg_stage_flag:
            console.print("\n[yellow]CEG stage skipped[/yellow]")
        else:
            with audit.stage("ceg_generation"):
                console.print("\n[bold green]Stage 2: CEG generation[/bold green]")
                ceg_client = build_ceg_client_from_config(cfg)
                console.print(f"  -> using {ceg_client.name}")
                top_hypothesis = ranked.hypotheses[0]
                ceg = generate_ceg(case_obj, top_hypothesis, ceg_client)
                paths = write_ceg(ceg, run_dir, also_dot=True)
                console.print(
                    f"  -> wrote {paths['json'].name}, {paths['dot'].name}"
                )
                svg_path = try_render_ceg_svg(ceg, run_dir)
                if svg_path is not None:
                    console.print(f"  -> wrote {svg_path.name}")
                else:
                    console.print(
                        "  -> [dim]SVG render skipped (Graphviz not on PATH).[/dim]"
                    )

        audit.event("run_end", success=True)
        console.print(f"\n[bold green]Done.[/bold green] Outputs in {run_dir}")
    except Exception as e:
        artefact = audit.save_artifact("run_exception", tb.format_exc())
        audit.event(
            "run_end",
            success=False,
            error_type=type(e).__name__,
            error_message=str(e)[:1000],
            traceback_artifact=artefact,
        )
        console.print(f"\n[bold red]Run failed:[/bold red] {e}")
        console.print(f"  Traceback saved to: {run_dir / artefact}")
        console.print(f"  Full event log: {run_dir / 'events.jsonl'}")
        raise
    finally:
        set_active_logger(None)

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