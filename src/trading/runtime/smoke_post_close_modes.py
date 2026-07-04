"""Compatibility shim for post-close smoke mode handlers."""
from __future__ import annotations

import sys

from src.trading.phases._shell import smoke_post_close_modes as _canonical

run_strategy_evolution_once = _canonical.run_strategy_evolution_once
run_trading_reflection_once = _canonical.run_trading_reflection_once
_run_reflection_fixture = _canonical._run_reflection_fixture
_run_strategy_evolution_fixture = _canonical._run_strategy_evolution_fixture

__all__ = [
    "run_strategy_evolution_once",
    "run_trading_reflection_once",
    "_run_reflection_fixture",
    "_run_strategy_evolution_fixture",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
