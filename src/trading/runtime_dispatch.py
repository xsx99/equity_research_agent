"""Shared dispatch helpers for scheduler phases and smoke modes."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.trading.runtime_live import run_live_preopen_once
from src.trading.runtime_smoke import (
    _run_historical_replay_fixture,
    _run_intraday_refresh_fixture,
    _run_manual_review_fixture,
    _run_paper_option_fixture,
    _run_paper_trade_dry_run,
    _run_provider_guardrail_fixture,
    _run_reflection_fixture,
    _run_strategy_evolution_fixture,
    _run_universe_signal_db_write,
)

RuntimeHandler = Callable[[], dict[str, Any]]

JOB_PHASE_HANDLERS: dict[str, RuntimeHandler] = {
    "preopen": run_live_preopen_once,
    "manual_review": _run_manual_review_fixture,
    "intraday_refresh": _run_intraday_refresh_fixture,
    "reflection": _run_reflection_fixture,
    "strategy_evolution": _run_strategy_evolution_fixture,
}

SMOKE_MODE_HANDLERS: dict[str, RuntimeHandler] = {
    "provider_guardrail_fixture": _run_provider_guardrail_fixture,
    "universe_signal_db_write": _run_universe_signal_db_write,
    "historical_replay_fixture": _run_historical_replay_fixture,
    "paper_trade_dry_run": _run_paper_trade_dry_run,
    "manual_review_fixture": _run_manual_review_fixture,
    "paper_option_fixture": _run_paper_option_fixture,
    "intraday_refresh_fixture": _run_intraday_refresh_fixture,
    "reflection_fixture": _run_reflection_fixture,
    "strategy_evolution_fixture": _run_strategy_evolution_fixture,
}


def get_job_phase_handler(phase: str) -> RuntimeHandler:
    """Return the scheduler runtime handler for a supported phase."""
    try:
        return JOB_PHASE_HANDLERS[phase]
    except KeyError as exc:
        raise ValueError(f"unsupported_trading_job_phase:{phase}") from exc


def get_smoke_mode_handler(mode: str) -> RuntimeHandler:
    """Return the smoke runtime handler for a supported smoke mode."""
    try:
        return SMOKE_MODE_HANDLERS[mode]
    except KeyError as exc:
        raise ValueError(f"unsupported_trading_smoke_mode:{mode}") from exc
