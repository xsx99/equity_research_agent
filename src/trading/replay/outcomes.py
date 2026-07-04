"""Compatibility shim for historical replay outcome records."""
from __future__ import annotations

import sys

from src.trading.phases.replay import outcomes as _canonical

CandidateOutcomeEvaluationRecord = _canonical.CandidateOutcomeEvaluationRecord
OutcomeEvaluator = _canonical.OutcomeEvaluator
PricePoint = _canonical.PricePoint
_catalyst_type = _canonical._catalyst_type
_confidence_bucket = _canonical._confidence_bucket
_points_in_window = _canonical._points_in_window

__all__ = [
    "CandidateOutcomeEvaluationRecord",
    "OutcomeEvaluator",
    "PricePoint",
    "_catalyst_type",
    "_confidence_bucket",
    "_points_in_window",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
