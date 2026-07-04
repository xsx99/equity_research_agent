"""Canonical trading runtime package and stable public facade."""
from __future__ import annotations

__all__ = [
    "AVAILABLE_SMOKE_MODES",
    "TRADING_JOB_PHASES",
    "run_job_phase",
    "run_smoke_mode",
]


# PR 42 moves only the morning phases. Keep the runtime facade lazy until PR 43
# moves the cross-phase shell; eager dispatch imports still create phase cycles.
def __getattr__(name: str):
    if name == "AVAILABLE_SMOKE_MODES":
        from .smoke import AVAILABLE_SMOKE_MODES

        return AVAILABLE_SMOKE_MODES
    if name in {"TRADING_JOB_PHASES", "run_job_phase", "run_smoke_mode"}:
        from .facade import TRADING_JOB_PHASES, run_job_phase, run_smoke_mode

        exports = {
            "TRADING_JOB_PHASES": TRADING_JOB_PHASES,
            "run_job_phase": run_job_phase,
            "run_smoke_mode": run_smoke_mode,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
