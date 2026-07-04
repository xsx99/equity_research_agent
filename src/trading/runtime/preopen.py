"""Compatibility shim for the preopen phase facade."""
from __future__ import annotations

import sys

from src.trading.phases import preopen as _canonical

ActiveManualRequestLoader = _canonical.ActiveManualRequestLoader
ActiveUniverseFilterLoader = _canonical.ActiveUniverseFilterLoader
LivePaperExecutionWorkflow = _canonical.LivePaperExecutionWorkflow
LivePortfolioSyncWorkflow = _canonical.LivePortfolioSyncWorkflow
LivePreopenDependencies = _canonical.LivePreopenDependencies
LivePreopenRuntime = _canonical.LivePreopenRuntime
LiveRiskWorkflow = _canonical.LiveRiskWorkflow
LiveSignalPipeline = _canonical.LiveSignalPipeline
LiveStrategyPipeline = _canonical.LiveStrategyPipeline
LiveTradingDecisionPipeline = _canonical.LiveTradingDecisionPipeline
LiveUniverseScanPipeline = _canonical.LiveUniverseScanPipeline
_ConfiguredLiveUniverseScanPipeline = _canonical._ConfiguredLiveUniverseScanPipeline
_LiveRiskWorkflow = _canonical._LiveRiskWorkflow
build_live_preopen_dependencies = _canonical.build_live_preopen_dependencies
run_live_preopen_once = _canonical.run_live_preopen_once
run_preopen_once = _canonical.run_preopen_once
save_failed_preopen_runtime_run = _canonical.save_failed_preopen_runtime_run
save_preopen_runtime_run = _canonical.save_preopen_runtime_run

__all__ = [
    "ActiveManualRequestLoader",
    "ActiveUniverseFilterLoader",
    "LivePaperExecutionWorkflow",
    "LivePortfolioSyncWorkflow",
    "LivePreopenDependencies",
    "LivePreopenRuntime",
    "LiveRiskWorkflow",
    "LiveSignalPipeline",
    "LiveStrategyPipeline",
    "LiveTradingDecisionPipeline",
    "LiveUniverseScanPipeline",
    "_ConfiguredLiveUniverseScanPipeline",
    "_LiveRiskWorkflow",
    "build_live_preopen_dependencies",
    "run_live_preopen_once",
    "run_preopen_once",
    "save_failed_preopen_runtime_run",
    "save_preopen_runtime_run",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
