"""Compatibility shim for the trading runtime facade."""
from __future__ import annotations

import sys

from src.trading.phases._shell import facade as _canonical

TRADING_JOB_PHASES = _canonical.TRADING_JOB_PHASES
run_job_phase = _canonical.run_job_phase
run_smoke_mode = _canonical.run_smoke_mode

__all__ = [
    "TRADING_JOB_PHASES",
    "run_job_phase",
    "run_smoke_mode",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
