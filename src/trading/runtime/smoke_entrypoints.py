"""Compatibility shim for stable smoke runtime entrypoints."""
from __future__ import annotations

import sys

from src.trading.phases._shell import smoke_entrypoints as _canonical

run_intraday_signal_refresh_once = _canonical.run_intraday_signal_refresh_once
run_manual_ticker_review_once = _canonical.run_manual_ticker_review_once
run_strategy_evolution_once = _canonical.run_strategy_evolution_once
run_trading_preopen_once = _canonical.run_trading_preopen_once
run_trading_reflection_once = _canonical.run_trading_reflection_once

__all__ = [
    "run_intraday_signal_refresh_once",
    "run_manual_ticker_review_once",
    "run_strategy_evolution_once",
    "run_trading_preopen_once",
    "run_trading_reflection_once",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
