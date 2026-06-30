"""CEG validation, repair, and rendering."""
from consortium.ceg.renderer import ceg_to_dot, render_ceg_to_svg, write_ceg_dot
from consortium.ceg.repair import (
    NormalizationRecord,
    RepairReport,
    normalize_outgoing_probabilities,
)
from consortium.ceg.validator import (
    CEGValidationError,
    assert_ceg_valid,
    validate_ceg_evidence_grounding,
    validate_ceg_structure,
)

# Add to the imports block:
from consortium.ceg.event_tree_validator import (
    EventTreeValidationError,
    assert_event_tree_valid,
    validate_event_tree_evidence_grounding,
    validate_event_tree_structure,
)

from consortium.ceg.tree_to_dataframe import (
    TreePath,
    enumerate_root_to_leaf_paths,
    event_tree_to_dataframe,
)
from consortium.ceg.tree_to_ceg import (
    CegpyConversionReport,
    event_tree_to_ceg,
)

from consortium.ceg.event_tree_repair import (
    EventTreeRepairReport,
    repair_event_tree,
)

__all__ = [
    "CEGValidationError",
    "NormalizationRecord",
    "RepairReport",
    "assert_ceg_valid",
    "ceg_to_dot",
    "normalize_outgoing_probabilities",
    "render_ceg_to_svg",
    "validate_ceg_evidence_grounding",
    "validate_ceg_structure",
    "write_ceg_dot",
    # event tree
    "EventTreeValidationError",
    "assert_event_tree_valid",
    "validate_event_tree_evidence_grounding",
    "validate_event_tree_structure",
    "CegpyConversionReport",
    "TreePath",
    "enumerate_root_to_leaf_paths",
    "event_tree_to_ceg",
    "event_tree_to_dataframe",
    "EventTreeRepairReport",
    "repair_event_tree",
]