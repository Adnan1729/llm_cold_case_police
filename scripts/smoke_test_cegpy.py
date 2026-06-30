"""Smoke test: verify cegpy installation and basic API.

Runs the canonical cegpy pipeline (DataFrame -> StagedTree -> ChainEventGraph)
on a tiny synthetic dataset and prints structural counts. If this prints
without exceptions, the install is good.
"""
from __future__ import annotations

import pandas as pd
from cegpy import ChainEventGraph, StagedTree


def main() -> None:
    # Tiny synthetic dataset: two binary variables.
    # 30 rows, varied joint distribution so AHC has something to chew on.
    rows = (
        [{"A": "yes", "B": "yes"}] * 10
        + [{"A": "yes", "B": "no"}] * 5
        + [{"A": "no", "B": "yes"}] * 5
        + [{"A": "no", "B": "no"}] * 10
    )
    df = pd.DataFrame(rows)
    print(f"Input DataFrame: {len(df)} rows, columns={list(df.columns)}")

    st = StagedTree(df)
    print(f"StagedTree constructed. nodes={st.number_of_nodes()}")

    st.calculate_AHC_transitions()
    print("AHC transitions calculated.")

    ceg = ChainEventGraph(st)
    print(
        f"ChainEventGraph constructed. "
        f"nodes={ceg.number_of_nodes()}, edges={ceg.number_of_edges()}"
    )

    print("\nOK - cegpy is working.")


if __name__ == "__main__":
    main()