"""Shared dispatch helpers for scheduler phases and smoke modes."""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from .intraday_refresh import run_live_intraday_refresh_once
from .manual_review import run_live_manual_review_once
from .preopen import run_live_preopen_once
from .reflection import run_live_reflection_once
from .smoke import (
    _run_historical_replay_fixture,
    _run_intraday_refresh_fixture,
    _run_manual_review_execution_fixture,
    _run_manual_review_fixture,
    _run_paper_option_lifecycle_fixture,
    _run_paper_option_fixture,
    _run_paper_trade_dry_run,
    _run_provider_guardrail_fixture,
    _run_reflection_fixture,
    _run_strategy_evolution_fixture,
    _run_universe_signal_db_write,
)
from .strategy_evolution import run_live_strategy_evolution_once

RuntimeHandler = Callable[..., dict[str, Any]]

JOB_PHASE_HANDLERS: dict[str, RuntimeHandler] = {
    "preopen": run_live_preopen_once,
    "manual_review": run_live_manual_review_once,
    "intraday_refresh": run_live_intraday_refresh_once,
    "reflection": run_live_reflection_once,
    "strategy_evolution": run_live_strategy_evolution_once,
}

SMOKE_MODE_HANDLERS: dict[str, RuntimeHandler] = {
    "provider_guardrail_fixture": _run_provider_guardrail_fixture,
    "universe_signal_db_write": _run_universe_signal_db_write,
    "historical_replay_fixture": _run_historical_replay_fixture,
    "paper_trade_dry_run": _run_paper_trade_dry_run,
    "manual_review_fixture": _run_manual_review_fixture,
    "manual_review_execution_fixture": _run_manual_review_execution_fixture,
    "paper_option_fixture": _run_paper_option_fixture,
    "paper_option_lifecycle_fixture": _run_paper_option_lifecycle_fixture,
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


def invoke_job_phase_handler(phase: str, **policy: Any) -> dict[str, Any]:
    """Call the requested phase handler while dropping unsupported policy kwargs."""
    handler = get_job_phase_handler(phase)
    params = inspect.signature(handler).parameters

    kwargs = {k: v for k, v in policy.items() if k in params and v is not None}
    return handler(**kwargs)


def get_smoke_mode_handler(mode: str) -> RuntimeHandler:
    """Return the smoke runtime handler for a supported smoke mode."""
    try:
        return SMOKE_MODE_HANDLERS[mode]
    except KeyError as exc:
        raise ValueError(f"unsupported_trading_smoke_mode:{mode}") from exc
