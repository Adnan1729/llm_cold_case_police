"""Pipeline stages."""
from consortium.pipeline.aggregation import (
    AggregatorFn,
    aggregate_weighted_mean,
)
from consortium.pipeline.ceg_stage import generate_ceg
from consortium.pipeline.consortium_stage import run_consortium
from consortium.pipeline.ingestion import (
    EvidenceExtractionOutput,
    ingest_case_text,
)

__all__ = [
    "AggregatorFn",
    "EvidenceExtractionOutput",
    "aggregate_weighted_mean",
    "generate_ceg",
    "ingest_case_text",
    "run_consortium",
]