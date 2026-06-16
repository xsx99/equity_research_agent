"""Stable facade for fixture-backed trading smoke runtimes."""
from __future__ import annotations

from .smoke_entrypoints import (
    run_intraday_signal_refresh_once,
    run_manual_ticker_review_once,
    run_strategy_evolution_once,
    run_trading_preopen_once,
    run_trading_reflection_once,
)
from .smoke_fixture_modes import (
    _run_historical_replay_fixture,
    _run_intraday_refresh_fixture,
    _run_manual_review_execution_fixture,
    _run_manual_review_fixture,
    _run_paper_option_lifecycle_fixture,
    _run_paper_option_fixture,
    _run_paper_trade_dry_run,
    _run_provider_guardrail_fixture,
    _run_universe_signal_db_write,
)
from .smoke_post_close_modes import (
    _run_reflection_fixture,
    _run_strategy_evolution_fixture,
)

AVAILABLE_SMOKE_MODES = (
    "provider_guardrail_fixture",
    "universe_signal_db_write",
    "historical_replay_fixture",
    "paper_trade_dry_run",
    "manual_review_fixture",
    "manual_review_execution_fixture",
    "paper_option_fixture",
    "paper_option_lifecycle_fixture",
    "intraday_refresh_fixture",
    "reflection_fixture",
    "strategy_evolution_fixture",
)

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
