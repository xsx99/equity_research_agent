"""Public facade for the live preopen runtime."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from .preopen_dependencies import (
    ActiveManualRequestLoader,
    ActiveUniverseFilterLoader,
    LivePaperExecutionWorkflow,
    LivePortfolioSyncWorkflow,
    LivePreopenDependencies,
    LiveRiskWorkflow,
    LiveSignalPipeline,
    LiveStrategyPipeline,
    LiveTradingDecisionPipeline,
    LiveUniverseScanPipeline,
    _ConfiguredLiveUniverseScanPipeline,
    build_live_preopen_dependencies,
)
from .preopen_risk import _LiveRiskWorkflow
from .preopen_runner import LivePreopenRuntime


def run_live_preopen_once(
    *,
    dependencies: LivePreopenDependencies | None = None,
    execute_paper_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Execute one live preopen run with injected dependencies."""
    return run_preopen_once(
        dependencies=dependencies,
        execute_paper_orders=execute_paper_orders,
        now=now,
    )


def run_preopen_once(
    *,
    dependencies: LivePreopenDependencies | None = None,
    execute_paper_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Execute one live preopen run with injected dependencies."""
    if dependencies is not None:
        return LivePreopenRuntime(
            dependencies=dependencies,
            now=now,
            execute_paper_orders=execute_paper_orders,
        ).run()

    from src.db.connection import get_session

    with get_session() as session:
        return LivePreopenRuntime(
            dependencies=build_live_preopen_dependencies(session),
            now=now,
            execute_paper_orders=execute_paper_orders,
        ).run()


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
]
