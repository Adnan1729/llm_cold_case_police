"""Inspect cegpy's CEG edge representation.

Prints each edge as (u, v, key, data_dict) so we can see exactly where
cegpy stores event labels and probabilities. Use this whenever a cegpy
version bump might have changed the edge-attribute convention.
"""
from __future__ import annotations

import pandas as pd
from cegpy import ChainEventGraph, StagedTree


def main() -> None:
    # Two-level dataframe with two situations sharing branching factor 2,
    # so AHC has something to work on.
    rows = (
        [{"level_0": "outcome_0", "level_1": "outcome_0"}] * 420
        + [{"level_0": "outcome_0", "level_1": "outcome_1"}] * 180
        + [{"level_0": "outcome_1", "level_1": None}] * 400
    )
    df = pd.DataFrame(rows)

    st = StagedTree(df)
    st.calculate_AHC_transitions()
    ceg = ChainEventGraph(st)

    print(f"Nodes: {list(ceg.nodes())}")
    print()
    print("Edges (u, v, key, data_dict):")
    for u, v, key, data in ceg.edges(data=True, keys=True):
        print(f"  {u!r} -> {v!r}, key={key!r}, data={data}")


if __name__ == "__main__":
    main()