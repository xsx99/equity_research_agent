"""Compatibility shim for preopen dependency assembly."""
from __future__ import annotations

import sys

from src.trading.phases.preopen import dependencies as _canonical

ActiveManualRequestLoader = _canonical.ActiveManualRequestLoader
ActiveUniverseFilterLoader = _canonical.ActiveUniverseFilterLoader
LivePaperExecutionWorkflow = _canonical.LivePaperExecutionWorkflow
LivePortfolioSyncWorkflow = _canonical.LivePortfolioSyncWorkflow
LivePreopenDependencies = _canonical.LivePreopenDependencies
LiveRiskWorkflow = _canonical.LiveRiskWorkflow
LiveSignalPipeline = _canonical.LiveSignalPipeline
LiveStrategyPipeline = _canonical.LiveStrategyPipeline
LiveTradingDecisionPipeline = _canonical.LiveTradingDecisionPipeline
LiveUniverseScanPipeline = _canonical.LiveUniverseScanPipeline
_ConfiguredLiveUniverseScanPipeline = _canonical._ConfiguredLiveUniverseScanPipeline
_RepositoryUniverseFilterLoader = _canonical._RepositoryUniverseFilterLoader
build_live_preopen_dependencies = _canonical.build_live_preopen_dependencies

__all__ = [
    "ActiveManualRequestLoader",
    "ActiveUniverseFilterLoader",
    "LivePaperExecutionWorkflow",
    "LivePortfolioSyncWorkflow",
    "LivePreopenDependencies",
    "LiveRiskWorkflow",
    "LiveSignalPipeline",
    "LiveStrategyPipeline",
    "LiveTradingDecisionPipeline",
    "LiveUniverseScanPipeline",
    "_ConfiguredLiveUniverseScanPipeline",
    "_RepositoryUniverseFilterLoader",
    "build_live_preopen_dependencies",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
