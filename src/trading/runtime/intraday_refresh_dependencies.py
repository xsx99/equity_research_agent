"""Compatibility shim for intraday dependency assembly."""
from __future__ import annotations

import sys

from src.trading.phases.intraday import dependencies as _canonical

LiveIntradayRefreshDependencies = _canonical.LiveIntradayRefreshDependencies
_RepositoryBaselineLoader = _canonical._RepositoryBaselineLoader
_RepositoryExistingNewsDedupeKeyLoader = _canonical._RepositoryExistingNewsDedupeKeyLoader
_RepositoryIntradayCandidateContextLoader = _canonical._RepositoryIntradayCandidateContextLoader
_RepositoryIntradayRequestContextLoader = _canonical._RepositoryIntradayRequestContextLoader
_RepositoryIntradayScopeLoader = _canonical._RepositoryIntradayScopeLoader
_RepositoryMacroSnapshotLoader = _canonical._RepositoryMacroSnapshotLoader
_RepositoryPreviousIntradaySnapshotLoader = _canonical._RepositoryPreviousIntradaySnapshotLoader
_scheduler_trade_date = _canonical._scheduler_trade_date
build_live_intraday_refresh_dependencies = _canonical.build_live_intraday_refresh_dependencies

__all__ = [
    "LiveIntradayRefreshDependencies",
    "_RepositoryBaselineLoader",
    "_RepositoryExistingNewsDedupeKeyLoader",
    "_RepositoryIntradayCandidateContextLoader",
    "_RepositoryIntradayRequestContextLoader",
    "_RepositoryIntradayScopeLoader",
    "_RepositoryMacroSnapshotLoader",
    "_RepositoryPreviousIntradaySnapshotLoader",
    "_scheduler_trade_date",
    "build_live_intraday_refresh_dependencies",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
