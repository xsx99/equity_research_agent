"""Compatibility shim for historical replay orchestration."""
from __future__ import annotations

import sys

from src.trading.phases.replay import historical as _canonical

HistoricalReplayResult = _canonical.HistoricalReplayResult
HistoricalReplayRunRecord = _canonical.HistoricalReplayRunRecord
HistoricalReplayRunner = _canonical.HistoricalReplayRunner

__all__ = [
    "HistoricalReplayResult",
    "HistoricalReplayRunRecord",
    "HistoricalReplayRunner",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
