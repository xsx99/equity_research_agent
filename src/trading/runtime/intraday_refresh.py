"""Compatibility shim for the intraday refresh phase facade."""
from __future__ import annotations

import sys

from src.trading.phases import intraday as _canonical

LiveIntradayRefreshDependencies = _canonical.LiveIntradayRefreshDependencies
LiveIntradayRefreshRuntime = _canonical.LiveIntradayRefreshRuntime
_RepositoryBaselineLoader = _canonical._RepositoryBaselineLoader
_RepositoryIntradayRequestContextLoader = _canonical._RepositoryIntradayRequestContextLoader
_RepositoryIntradayScopeLoader = _canonical._RepositoryIntradayScopeLoader
_RepositoryPreviousIntradaySnapshotLoader = _canonical._RepositoryPreviousIntradaySnapshotLoader
_build_intraday_refresh_payload = _canonical._build_intraday_refresh_payload
_build_rebalance_request = _canonical._build_rebalance_request
_event_item_from_source_record = _canonical._event_item_from_source_record
_load_event_items = _canonical._load_event_items
_position_by_ticker = _canonical._position_by_ticker
build_live_intraday_refresh_dependencies = _canonical.build_live_intraday_refresh_dependencies
run_intraday_refresh_once = _canonical.run_intraday_refresh_once
run_live_intraday_refresh_once = _canonical.run_live_intraday_refresh_once

__all__ = [
    "LiveIntradayRefreshDependencies",
    "LiveIntradayRefreshRuntime",
    "_RepositoryBaselineLoader",
    "_RepositoryIntradayRequestContextLoader",
    "_RepositoryIntradayScopeLoader",
    "_RepositoryPreviousIntradaySnapshotLoader",
    "_build_intraday_refresh_payload",
    "_build_rebalance_request",
    "_event_item_from_source_record",
    "_load_event_items",
    "_position_by_ticker",
    "build_live_intraday_refresh_dependencies",
    "run_intraday_refresh_once",
    "run_live_intraday_refresh_once",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
