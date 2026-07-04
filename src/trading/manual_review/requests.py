"""Compatibility shim for manual review request contracts."""
from __future__ import annotations

import sys

from src.trading.phases.manual_review import requests as _canonical

ACTIVE_STATUS = _canonical.ACTIVE_STATUS
REQUEST_MODES = _canonical.REQUEST_MODES
ManualTickerRequest = _canonical.ManualTickerRequest
ManualTickerRequestService = _canonical.ManualTickerRequestService

__all__ = [
    "ACTIVE_STATUS",
    "REQUEST_MODES",
    "ManualTickerRequest",
    "ManualTickerRequestService",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
