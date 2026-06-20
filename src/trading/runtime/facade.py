"""Trading runtime facade for scheduler phases and standalone smoke modes."""
from __future__ import annotations

from typing import Any

from src.core.logging import get_logger

from . import dispatch
from .smoke import AVAILABLE_SMOKE_MODES

logger = get_logger(__name__)

TRADING_JOB_PHASES = (
    "preopen",
    "manual_review",
    "intraday_refresh",
    "reflection",
    "strategy_evolution",
)


def run_job_phase(
    phase: str,
    *,
    execute_paper_orders: bool | None = None,
    execute_paper_option_orders: bool | None = None,
) -> dict[str, Any]:
    """Run one scheduler-facing trading phase."""
    return dispatch.invoke_job_phase_handler(
        phase,
        execute_paper_orders=execute_paper_orders,
        execute_paper_option_orders=execute_paper_option_orders,
    )


def run_smoke_mode(mode: str) -> dict[str, Any]:
    """Run one standalone fixture-first smoke mode."""
    report = dispatch.get_smoke_mode_handler(mode)()
    logger.info("trading_smoke_completed", mode=mode, status=report["status"])
    return report
