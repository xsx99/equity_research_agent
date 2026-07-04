"""Public facade for the live intraday refresh phase."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

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


def run_live_intraday_refresh_once(
    *,
    dependencies: object | None = None,
    execute_paper_orders: bool = False,
    execute_paper_option_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Execute one live intraday refresh run with injected dependencies."""
    return run_intraday_refresh_once(
        dependencies=dependencies,
        execute_paper_orders=execute_paper_orders,
        execute_paper_option_orders=execute_paper_option_orders,
        now=now,
    )


def run_intraday_refresh_once(
    *,
    dependencies: object | None = None,
    execute_paper_orders: bool = False,
    execute_paper_option_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Execute one live intraday refresh run with injected dependencies."""
    from src.trading.phases.intraday.runner import LiveIntradayRefreshRuntime

    if dependencies is not None:
        return LiveIntradayRefreshRuntime(
            dependencies=dependencies,
            now=now,
            execute_paper_orders=execute_paper_orders,
            execute_paper_option_orders=execute_paper_option_orders,
        ).run()

    from src.db.connection import get_session

    with get_session() as session:
        return LiveIntradayRefreshRuntime(
            dependencies=build_live_intraday_refresh_dependencies(session),
            now=now,
            execute_paper_orders=execute_paper_orders,
            execute_paper_option_orders=execute_paper_option_orders,
        ).run()


def build_live_intraday_refresh_dependencies(session: object | None = None) -> object:
    """Build the default production dependency graph for one live intraday refresh run."""
    from src.trading.phases.intraday.dependencies import (
        build_live_intraday_refresh_dependencies as _build_live_intraday_refresh_dependencies,
    )

    return _build_live_intraday_refresh_dependencies(session)


def __getattr__(name: str):
    if name == "LiveIntradayRefreshRuntime":
        from src.trading.phases.intraday.runner import LiveIntradayRefreshRuntime

        return LiveIntradayRefreshRuntime
    if name in {
        "LiveIntradayRefreshDependencies",
        "_RepositoryBaselineLoader",
        "_RepositoryIntradayRequestContextLoader",
        "_RepositoryIntradayScopeLoader",
        "_RepositoryPreviousIntradaySnapshotLoader",
        "build_live_intraday_refresh_dependencies",
    }:
        from src.trading.phases.intraday import dependencies

        return getattr(dependencies, name)
    if name in {
        "_build_intraday_refresh_payload",
        "_build_rebalance_request",
        "_event_item_from_source_record",
        "_load_event_items",
        "_position_by_ticker",
    }:
        from src.trading.phases.intraday import helpers

        return getattr(helpers, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
