"""Trading runtime facade for scheduler phases and standalone smoke modes."""
from __future__ import annotations

from typing import Any

from src.core.logging import get_logger
from src.trading import runtime_dispatch
from src.trading.runtime_smoke import AVAILABLE_SMOKE_MODES

logger = get_logger(__name__)

TRADING_JOB_PHASES = (
    "preopen",
    "manual_review",
    "intraday_refresh",
    "reflection",
    "strategy_evolution",
)


def run_job_phase(phase: str) -> dict[str, Any]:
    """Run one scheduler-facing trading phase."""
    return runtime_dispatch.get_job_phase_handler(phase)()


def run_smoke_mode(mode: str) -> dict[str, Any]:
    """Run one standalone fixture-first smoke mode."""
    report = runtime_dispatch.get_smoke_mode_handler(mode)()
    logger.info("trading_smoke_completed", mode=mode, status=report["status"])
    return report
