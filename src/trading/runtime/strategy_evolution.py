"""Compatibility shim for the strategy-evolution phase runtime."""
from __future__ import annotations

import sys

from src.trading.phases import strategy_evolution as _canonical

LiveStrategyEvolutionDependencies = _canonical.LiveStrategyEvolutionDependencies
LiveStrategyEvolutionRequestLoader = _canonical.LiveStrategyEvolutionRequestLoader
LiveStrategyEvolutionRuntime = _canonical.LiveStrategyEvolutionRuntime
StrategyEvolutionLoadResult = _canonical.StrategyEvolutionLoadResult
build_live_strategy_evolution_dependencies = _canonical.build_live_strategy_evolution_dependencies
run_live_strategy_evolution_once = _canonical.run_live_strategy_evolution_once
run_strategy_evolution_once = _canonical.run_strategy_evolution_once

__all__ = [
    "LiveStrategyEvolutionDependencies",
    "LiveStrategyEvolutionRequestLoader",
    "LiveStrategyEvolutionRuntime",
    "StrategyEvolutionLoadResult",
    "build_live_strategy_evolution_dependencies",
    "run_live_strategy_evolution_once",
    "run_strategy_evolution_once",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
