"""Convert an EventTree to a Pydantic ChainEventGraph via cegpy AHC.

This is the second half of the neurosymbolic split for CEG generation:
- The LLM produces an EventTree (handled in step 5).
- This module converts the EventTree into a ChainEventGraph by handing
  the stage-identification (equivalence-class clustering) problem to
  cegpy's deterministic AHC algorithm.

Pipeline:

    EventTree                                  (from LLM)
        |
        v
    event_tree_to_dataframe(use_generic_labels=True)
        |                                       (pseudo-counts + outcome_K
        v                                        placeholders so cegpy can
    cegpy.StagedTree(df)                         partition situations)
        |
        v
    .calculate_AHC_transitions()               (Bayesian agglomerative
        |                                       hierarchical clustering)
        v
    cegpy.ChainEventGraph(staged_tree)         (positions merged)
        |
        v
    Pydantic ChainEventGraph                   (final output, with
                                                specific labels and
                                                evidence reattached)

Generic labels:
- cegpy partitions situations into a "hyperstage" — groups of situations
  whose outgoing-event signatures match. AHC searches within each group
  for pairs to merge.
- With the LLM's distinct event labels ("Alice arrives", "Bob leaves",
  ...), every situation has a unique signature, so every situation sits
  in a singleton group, and AHC has nothing to do (and crashes in some
  cegpy versions when it tries).
- We sidestep this by submitting generic positional labels (outcome_0,
  outcome_1, ...) to cegpy. Situations with the same branching factor
  share signatures, AHC has pairs to consider, and the LLM's specific
  labels are reattached afterwards using LabelMapping.

Singleton-class fallback:
- If every situation has a different branching factor, cegpy still
  produces a singleton-only hyperstage and crashes. We catch that
  specific failure mode (ValueError from max() of empty sequence inside
  cegpy.trees._staged) and emit a trivial CEG — every position its own
  stage — which is what cegpy would have produced had its bug been
  fixed. This is logged via the conversion report so the audit trail
  records when it happens.

Probability normalisation:
- cegpy's AHC may produce conditional probabilities that don't sum to
  exactly 1.0 due to pseudo-count rounding. The conversion runs
  normalize_outgoing_probabilities on the result so the CEG passes
  structural validation. Normalisations are surfaced via the report.

Evidence preservation:
- Edge evidence is preserved by (from_node, event_label) matching after
  reattaching specific labels. Node evidence is left empty in this
  version; preservation across stage merging is non-trivial and deferred.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from consortium.ceg.repair import (
    NormalizationRecord,
    normalize_outgoing_probabilities,
)
from consortium.ceg.tree_to_dataframe import (
    LabelMapping,
    enumerate_root_to_leaf_paths,
    event_tree_to_dataframe,
)
from consortium.schemas.ceg import (
    CEGEdge,
    CEGNode,
    CEGNodeType,
    ChainEventGraph,
)
from consortium.schemas.event_tree import EventTree


@dataclass
class CegpyConversionReport:
    """Summary of an event_tree_to_ceg conversion, for audit logging."""

    event_tree_node_count: int
    event_tree_edge_count: int
    event_tree_path_count: int
    pseudo_observation_count: int
    pseudo_count_budget: int
    cegpy_position_count: int
    cegpy_edge_count: int
    nodes_merged: int
    ahc_fallback_triggered: bool = False
    ahc_fallback_reason: Optional[str] = None
    normalizations: list[NormalizationRecord] = field(default_factory=list)


def event_tree_to_ceg(
    tree: EventTree,
    *,
    pseudo_count: int = 1000,
    case_id: Optional[str] = None,
    hypothesis_id: Optional[str] = None,
    notes: Optional[str] = None,
    probability_tolerance: float = 1e-4,
) -> tuple[ChainEventGraph, CegpyConversionReport]:
    """Convert an EventTree to a Pydantic ChainEventGraph via cegpy AHC.

    Args:
        tree: A validated EventTree.
        pseudo_count: Number of pseudo-observations for cegpy. Higher
            values make AHC more confident in the LLM's probabilities
            (less aggressive merging). Default 1000.
        case_id: Override the case ID in the output. Defaults to tree's.
        hypothesis_id: Override the hypothesis ID. Defaults to tree's.
        notes: Optional notes attached to the output CEG.
        probability_tolerance: Tolerance for the normalisation pass.

    Returns:
        (ChainEventGraph, CegpyConversionReport).

    Raises:
        ImportError: if cegpy is not installed.
        ValueError: if the tree has no edges.
    """
    case_id = case_id or tree.case_id
    hypothesis_id = hypothesis_id or tree.hypothesis_id

    try:
        from cegpy import ChainEventGraph as CegpyCEG
        from cegpy import StagedTree
    except ImportError as e:
        raise ImportError(
            "event_tree_to_ceg requires cegpy. Install with: pip install cegpy"
        ) from e

    # 1. Build the dataframe with generic outcome labels so cegpy's
    #    hyperstage partitioning groups situations by branching factor.
    df, label_mapping = event_tree_to_dataframe(
        tree,
        pseudo_count=pseudo_count,
        use_generic_labels=True,
    )
    assert label_mapping is not None  # guaranteed when use_generic_labels=True

    # 2. Run cegpy. AHC may fail with the singleton-class bug when all
    #    situations have distinct branching factors; fall through if so.
    staged_tree = StagedTree(df)
    ahc_fallback = False
    ahc_fallback_reason: Optional[str] = None
    try:
        staged_tree.calculate_AHC_transitions()
        cegpy_ceg = CegpyCEG(staged_tree)
        cegpy_root_id = _find_cegpy_root(cegpy_ceg)
        cegpy_sink_ids = _find_cegpy_sinks(cegpy_ceg)
    except ValueError as e:
        # The cegpy singleton-class bug: max() of empty newscores_list.
        # Any other ValueError is real and should propagate.
        if "max() iterable argument is empty" not in str(e):
            raise
        ahc_fallback = True
        ahc_fallback_reason = (
            "cegpy singleton-class AHC bug: every situation had a "
            "unique branching factor, so the hyperstage contained no "
            "pairs to evaluate. Falling back to a direct trivial-staging "
            "CEG (every position its own stage)."
        )

    if ahc_fallback:
        final_ceg, repair_report = _direct_conversion(
            tree, case_id, hypothesis_id, notes, probability_tolerance
        )
        report = CegpyConversionReport(
            event_tree_node_count=len(tree.nodes),
            event_tree_edge_count=len(tree.edges),
            event_tree_path_count=len(enumerate_root_to_leaf_paths(tree)),
            pseudo_observation_count=len(df),
            pseudo_count_budget=pseudo_count,
            cegpy_position_count=len(final_ceg.nodes),
            cegpy_edge_count=len(final_ceg.edges),
            nodes_merged=0,
            ahc_fallback_triggered=True,
            ahc_fallback_reason=ahc_fallback_reason,
            normalizations=repair_report.normalizations,
        )
        return final_ceg, report

    # 3. Normal path: map cegpy IDs to ours.
    id_map = _build_id_map(cegpy_ceg, cegpy_root_id, cegpy_sink_ids)

    # 4. Build (from_node, specific_label) -> evidence index using the
    #    LLM's specific labels on the original tree.
    edge_evidence = _build_edge_evidence_index(tree)

    # 5. Build CEG nodes.
    our_nodes: list[CEGNode] = []
    leaf_node_ids: list[str] = []
    for cegpy_id in cegpy_ceg.nodes():
        our_id = id_map[cegpy_id]
        in_deg = cegpy_ceg.in_degree(cegpy_id)
        out_deg = cegpy_ceg.out_degree(cegpy_id)

        if in_deg == 0:
            node_type = CEGNodeType.ROOT
            desc = "Root (initial state)"
        elif out_deg == 0:
            node_type = CEGNodeType.LEAF
            desc = f"Terminal outcome ({our_id})"
            leaf_node_ids.append(our_id)
        else:
            node_type = CEGNodeType.SITUATION
            desc = f"Intermediate position ({our_id})"

        our_nodes.append(
            CEGNode(
                id=our_id,
                type=node_type,
                description=desc,
                associated_evidence=[],
            )
        )

    # 6. Build CEG edges. cegpy returns generic labels (outcome_K); we
    #    look up the specific label using the cegpy from-node's position
    #    in the original tree where possible. Note: after stage merging,
    #    a single cegpy node may correspond to multiple original-tree
    #    nodes, in which case we attempt all candidate (from_node, generic)
    #    keys and use the first match.
    our_edges: list[CEGEdge] = []
    cegpy_to_tree_nodes = _build_cegpy_to_tree_nodes(
        cegpy_ceg, cegpy_root_id, tree, df
    )

    for i, (u, v, key, edge_data) in enumerate(cegpy_ceg.edges(data=True, keys=True)):
        generic_label = _get_edge_label(edge_data, key)
        prob = _get_edge_probability(edge_data) or 0.0

        candidate_tree_nodes = cegpy_to_tree_nodes.get(u, [])
        specific_label = generic_label  # fallback if lookup fails
        evidence: list[str] = []
        for tree_node_id in candidate_tree_nodes:
            key = (tree_node_id, generic_label)
            if key in label_mapping.generic_to_specific:
                specific_label = label_mapping.generic_to_specific[key]
                evidence = list(edge_evidence.get(
                    (tree_node_id, specific_label), []
                ))
                break

        our_edges.append(
            CEGEdge(
                id=f"T{i}",
                from_node=id_map[u],
                to_node=id_map[v],
                event_label=specific_label,
                conditional_probability=prob,
                associated_evidence=sorted(set(evidence)),
            )
        )

    root_id = id_map[cegpy_root_id]
    preliminary_ceg = ChainEventGraph(
        case_id=case_id,
        hypothesis_id=hypothesis_id,
        nodes=our_nodes,
        edges=our_edges,
        stages=[],
        root_node_id=root_id,
        leaf_node_ids=leaf_node_ids,
        notes=notes,
    )

    final_ceg, repair_report = normalize_outgoing_probabilities(
        preliminary_ceg, tolerance=probability_tolerance
    )

    report = CegpyConversionReport(
        event_tree_node_count=len(tree.nodes),
        event_tree_edge_count=len(tree.edges),
        event_tree_path_count=len(enumerate_root_to_leaf_paths(tree)),
        pseudo_observation_count=len(df),
        pseudo_count_budget=pseudo_count,
        cegpy_position_count=len(list(cegpy_ceg.nodes())),
        cegpy_edge_count=len(list(cegpy_ceg.edges())),
        nodes_merged=len(tree.nodes) - len(list(cegpy_ceg.nodes())),
        ahc_fallback_triggered=False,
        ahc_fallback_reason=None,
        normalizations=repair_report.normalizations,
    )

    return final_ceg, report


# --- Helpers ---


def _direct_conversion(
    tree: EventTree,
    case_id: str,
    hypothesis_id: str,
    notes: Optional[str],
    probability_tolerance: float,
) -> tuple[ChainEventGraph, Any]:
    """Direct 1:1 tree -> CEG conversion used when AHC falls through.

    Produces the trivial-staging CEG cegpy would have returned if it
    handled the singleton-hyperstage case correctly.
    """
    incoming_count: dict[str, int] = defaultdict(int)
    outgoing_count: dict[str, int] = defaultdict(int)
    for edge in tree.edges:
        incoming_count[edge.to_node] += 1
        outgoing_count[edge.from_node] += 1

    our_nodes: list[CEGNode] = []
    leaf_node_ids: list[str] = []
    for node in tree.nodes:
        if node.id == tree.root_node_id:
            node_type = CEGNodeType.ROOT
        elif outgoing_count[node.id] == 0:
            node_type = CEGNodeType.LEAF
            leaf_node_ids.append(node.id)
        else:
            node_type = CEGNodeType.SITUATION
        our_nodes.append(
            CEGNode(
                id=node.id,
                type=node_type,
                description=node.description,
                associated_evidence=list(node.associated_evidence),
            )
        )

    our_edges = [
        CEGEdge(
            id=edge.id,
            from_node=edge.from_node,
            to_node=edge.to_node,
            event_label=edge.event_label,
            conditional_probability=edge.conditional_probability,
            associated_evidence=list(edge.associated_evidence),
        )
        for edge in tree.edges
    ]

    preliminary = ChainEventGraph(
        case_id=case_id,
        hypothesis_id=hypothesis_id,
        nodes=our_nodes,
        edges=our_edges,
        stages=[],
        root_node_id=tree.root_node_id,
        leaf_node_ids=leaf_node_ids,
        notes=notes,
    )
    return normalize_outgoing_probabilities(
        preliminary, tolerance=probability_tolerance
    )


def _find_cegpy_root(cegpy_ceg: Any) -> Any:
    roots = [n for n in cegpy_ceg.nodes() if cegpy_ceg.in_degree(n) == 0]
    if len(roots) != 1:
        raise RuntimeError(
            f"Expected exactly one root in cegpy's CEG, found {len(roots)}: "
            f"{roots}"
        )
    return roots[0]


def _find_cegpy_sinks(cegpy_ceg: Any) -> list[Any]:
    return [n for n in cegpy_ceg.nodes() if cegpy_ceg.out_degree(n) == 0]


def _build_id_map(
    cegpy_ceg: Any,
    cegpy_root: Any,
    cegpy_sinks: list[Any],
) -> dict[Any, str]:
    """Map cegpy node IDs to N0, N1, ... root first, then sinks, then rest."""
    id_map: dict[Any, str] = {cegpy_root: "N0"}
    counter = 1
    for sink_id in cegpy_sinks:
        if sink_id not in id_map:
            id_map[sink_id] = f"N{counter}"
            counter += 1
    for cegpy_id in cegpy_ceg.nodes():
        if cegpy_id not in id_map:
            id_map[cegpy_id] = f"N{counter}"
            counter += 1
    return id_map


def _build_cegpy_to_tree_nodes(
    cegpy_ceg: Any,
    cegpy_root_id: Any,
    tree: EventTree,
    df: Any,
) -> dict[Any, list[str]]:
    """Best-effort mapping from cegpy nodes to candidate original-tree
    node IDs by replaying paths.

    cegpy nodes after AHC may correspond to multiple original tree nodes
    (positions that got merged). We replay each root-to-leaf path
    through cegpy's graph using the generic labels in df, recording
    which tree node ID was at each step, and accumulate candidates per
    cegpy node.
    """
    edges_by_source_generic: dict[Any, dict[str, Any]] = defaultdict(dict)
    for u, v, key, data in cegpy_ceg.edges(data=True, keys=True):
        label = _get_edge_label(data, key)
        edges_by_source_generic[u][label] = v

    # Re-enumerate original tree paths with the generic labels
    from consortium.ceg.tree_to_dataframe import _build_generic_label_mapping
    label_mapping = _build_generic_label_mapping(tree)

    paths = enumerate_root_to_leaf_paths(tree)
    candidates: dict[Any, set[str]] = defaultdict(set)
    candidates[cegpy_root_id].add(tree.root_node_id)

    for path in paths:
        cegpy_cursor: Any = cegpy_root_id
        for depth, specific_label in enumerate(path.event_labels):
            parent_tree_id = path.node_ids[depth]
            child_tree_id = path.node_ids[depth + 1]
            generic = label_mapping.specific_to_generic.get(
                (parent_tree_id, specific_label)
            )
            if generic is None:
                break
            next_cegpy = edges_by_source_generic.get(cegpy_cursor, {}).get(
                generic
            )
            if next_cegpy is None:
                break
            candidates[next_cegpy].add(child_tree_id)
            cegpy_cursor = next_cegpy

    return {k: sorted(v) for k, v in candidates.items()}


def _build_edge_evidence_index(
    tree: EventTree,
) -> dict[tuple[str, str], list[str]]:
    """Index evidence by (from_node, event_label) so we can look up
    evidence after specific labels have been re-attached."""
    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for edge in tree.edges:
        by_key[(edge.from_node, edge.event_label)].extend(
            edge.associated_evidence
        )
    return dict(by_key)


def _get_edge_label(data: dict, key: Any = None) -> str:
    """Extract an event label from cegpy's edge.

    cegpy uses NetworkX MultiDiGraph, which stores the event label as
    the parallel-edge KEY, not as an attribute in the data dict. We try
    the key first (when iterating with keys=True), then fall back to
    common attribute names just in case the version we're running on
    chooses to put a copy in the data dict.
    """
    if key is not None and isinstance(key, str) and key:
        return key
    for k in ("label", "event_label", "event", "name"):
        if k in data and data[k] is not None:
            return str(data[k])
    return ""


def _get_edge_probability(data: dict) -> Optional[float]:
    for key in ("probability", "conditional_probability", "prob", "weight", "p"):
        if key in data and data[key] is not None:
            try:
                return float(data[key])
            except (TypeError, ValueError):
                pass
    return None