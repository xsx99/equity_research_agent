"""Compatibility shim for intraday news alert helpers."""
from __future__ import annotations

import sys

from src.trading.phases.intraday import news_alerts as _canonical

AlertSourceItem = _canonical.AlertSourceItem
NewsAlertRecord = _canonical.NewsAlertRecord
NewsAlertService = _canonical.NewsAlertService
_merge_themes = _canonical._merge_themes
classify_source_item_severity = _canonical.classify_source_item_severity

__all__ = [
    "AlertSourceItem",
    "NewsAlertRecord",
    "NewsAlertService",
    "_merge_themes",
    "classify_source_item_severity",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
