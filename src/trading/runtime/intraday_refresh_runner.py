"""Compatibility shim for the intraday refresh runtime runner."""
from __future__ import annotations

import sys

from src.trading.phases.intraday import runner as _canonical

LiveIntradayRefreshRuntime = _canonical.LiveIntradayRefreshRuntime
_build_intraday_intent_with_optional_context = _canonical._build_intraday_intent_with_optional_context
_intraday_instrument_type = _canonical._intraday_instrument_type
_intraday_macro_risk_state = _canonical._intraday_macro_risk_state
_intraday_positions = _canonical._intraday_positions
_load_intraday_macro_snapshot = _canonical._load_intraday_macro_snapshot
_portfolio_context_with_positions = _canonical._portfolio_context_with_positions
_should_refresh_intraday_macro_snapshot = _canonical._should_refresh_intraday_macro_snapshot

__all__ = [
    "LiveIntradayRefreshRuntime",
    "_build_intraday_intent_with_optional_context",
    "_intraday_instrument_type",
    "_intraday_macro_risk_state",
    "_intraday_positions",
    "_load_intraday_macro_snapshot",
    "_portfolio_context_with_positions",
    "_should_refresh_intraday_macro_snapshot",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
