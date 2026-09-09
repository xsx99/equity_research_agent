"""Compatibility shim for the persisted-candidate outcome runtime."""
from __future__ import annotations

import sys

from src.trading.phases import outcomes as _canonical

LiveOutcomeDependencies = _canonical.LiveOutcomeDependencies
LiveOutcomeRuntime = _canonical.LiveOutcomeRuntime
build_live_outcome_dependencies = _canonical.build_live_outcome_dependencies
run_live_outcomes_once = _canonical.run_live_outcomes_once

__all__ = [
    "LiveOutcomeDependencies",
    "LiveOutcomeRuntime",
    "build_live_outcome_dependencies",
    "run_live_outcomes_once",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
