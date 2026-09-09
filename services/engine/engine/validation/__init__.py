"""Validation pipeline and acceptance gates."""

from engine.validation.gates import DEFAULT_MIN_TRADES, AcceptanceGates
from engine.validation.pipeline import (
    HARD_STAGES,
    STAGE_NAMES,
    StageResult,
    ValidationReport,
    run_pipeline,
    weakest_sentence,
)

__all__ = [
    "DEFAULT_MIN_TRADES",
    "HARD_STAGES",
    "STAGE_NAMES",
    "AcceptanceGates",
    "StageResult",
    "ValidationReport",
    "run_pipeline",
    "weakest_sentence",
]
