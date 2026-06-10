"""Entry point for the cold-case pipeline CLI.

Thin wrapper around the Typer app defined in consortium.cli. Kept here
because users may invoke the pipeline via `python scripts/run_pipeline.py`
during development; the installed console script `consortium-run` does
the same thing.
"""
from consortium.cli import app

if __name__ == "__main__":
    app()