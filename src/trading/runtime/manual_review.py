"""Compatibility shim for the manual-review phase runtime."""
from __future__ import annotations

import sys

from src.trading.phases import manual_review as _canonical

LiveManualReviewDependencies = _canonical.LiveManualReviewDependencies
LiveManualReviewRuntime = _canonical.LiveManualReviewRuntime
ManualReviewExecutionResult = _canonical.ManualReviewExecutionResult
build_live_manual_review_dependencies = _canonical.build_live_manual_review_dependencies
run_live_manual_review_once = _canonical.run_live_manual_review_once
run_manual_review_once = _canonical.run_manual_review_once

__all__ = [
    "LiveManualReviewDependencies",
    "LiveManualReviewRuntime",
    "ManualReviewExecutionResult",
    "build_live_manual_review_dependencies",
    "run_live_manual_review_once",
    "run_manual_review_once",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
