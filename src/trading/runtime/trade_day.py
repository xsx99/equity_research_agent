"""Compatibility shim for trade-day helpers."""
from __future__ import annotations

import sys

from src.trading import trade_day as _canonical

local_day_bounds_utc = _canonical.local_day_bounds_utc
trade_date_for = _canonical.trade_date_for

__all__ = [
    "local_day_bounds_utc",
    "trade_date_for",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
