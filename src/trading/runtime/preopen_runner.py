"""Compatibility shim for the preopen runtime runner."""
from __future__ import annotations

import sys

from src.trading.phases.preopen import runner as _canonical

LivePreopenRuntime = _canonical.LivePreopenRuntime

__all__ = [
    "LivePreopenRuntime",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
