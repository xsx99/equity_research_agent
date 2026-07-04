"""Compatibility shim for trading runtime dispatch helpers."""
from __future__ import annotations

import sys

from src.trading.phases._shell import dispatch as _canonical

JOB_PHASE_HANDLERS = _canonical.JOB_PHASE_HANDLERS
RuntimeHandler = _canonical.RuntimeHandler
SMOKE_MODE_HANDLERS = _canonical.SMOKE_MODE_HANDLERS
get_job_phase_handler = _canonical.get_job_phase_handler
get_smoke_mode_handler = _canonical.get_smoke_mode_handler
invoke_job_phase_handler = _canonical.invoke_job_phase_handler

__all__ = [
    "JOB_PHASE_HANDLERS",
    "RuntimeHandler",
    "SMOKE_MODE_HANDLERS",
    "get_job_phase_handler",
    "get_smoke_mode_handler",
    "invoke_job_phase_handler",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
