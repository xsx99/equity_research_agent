"""Compatibility shim for fixture-backed trading smoke runtimes."""
from __future__ import annotations

import sys

from src.trading.phases._shell import smoke as _canonical

AVAILABLE_SMOKE_MODES = _canonical.AVAILABLE_SMOKE_MODES
_run_historical_replay_fixture = _canonical._run_historical_replay_fixture
_run_intraday_refresh_fixture = _canonical._run_intraday_refresh_fixture
_run_manual_review_execution_fixture = _canonical._run_manual_review_execution_fixture
_run_manual_review_fixture = _canonical._run_manual_review_fixture
_run_paper_option_lifecycle_fixture = _canonical._run_paper_option_lifecycle_fixture
_run_paper_option_fixture = _canonical._run_paper_option_fixture
_run_paper_trade_dry_run = _canonical._run_paper_trade_dry_run
_run_provider_guardrail_fixture = _canonical._run_provider_guardrail_fixture
_run_reflection_fixture = _canonical._run_reflection_fixture
_run_strategy_evolution_fixture = _canonical._run_strategy_evolution_fixture
_run_universe_signal_db_write = _canonical._run_universe_signal_db_write
run_intraday_signal_refresh_once = _canonical.run_intraday_signal_refresh_once
run_manual_ticker_review_once = _canonical.run_manual_ticker_review_once
run_strategy_evolution_once = _canonical.run_strategy_evolution_once
run_trading_preopen_once = _canonical.run_trading_preopen_once
run_trading_reflection_once = _canonical.run_trading_reflection_once

__all__ = [
    "AVAILABLE_SMOKE_MODES",
    "_run_historical_replay_fixture",
    "_run_intraday_refresh_fixture",
    "_run_manual_review_execution_fixture",
    "_run_manual_review_fixture",
    "_run_paper_option_lifecycle_fixture",
    "_run_paper_option_fixture",
    "_run_paper_trade_dry_run",
    "_run_provider_guardrail_fixture",
    "_run_reflection_fixture",
    "_run_strategy_evolution_fixture",
    "_run_universe_signal_db_write",
    "run_intraday_signal_refresh_once",
    "run_manual_ticker_review_once",
    "run_strategy_evolution_once",
    "run_trading_preopen_once",
    "run_trading_reflection_once",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
