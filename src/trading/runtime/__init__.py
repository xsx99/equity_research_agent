"""Stable compatibility facade for trading runtime entrypoints."""
from __future__ import annotations

from src.trading.phases._shell.facade import TRADING_JOB_PHASES, run_job_phase, run_smoke_mode
from src.trading.phases._shell.smoke import AVAILABLE_SMOKE_MODES

__all__ = [
    "AVAILABLE_SMOKE_MODES",
    "TRADING_JOB_PHASES",
    "run_job_phase",
    "run_smoke_mode",
]
