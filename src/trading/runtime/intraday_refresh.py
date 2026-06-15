"""Public facade for the live intraday refresh runtime."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from .intraday_refresh_dependencies import (
    LiveIntradayRefreshDependencies,
    _RepositoryBaselineLoader,
    _RepositoryIntradayRequestContextLoader,
    _RepositoryIntradayScopeLoader,
    _RepositoryPreviousIntradaySnapshotLoader,
    build_live_intraday_refresh_dependencies,
)
from .intraday_refresh_helpers import (
    _build_intraday_refresh_payload,
    _build_rebalance_request,
    _event_item_from_source_record,
    _load_event_items,
    _position_by_ticker,
)
from .intraday_refresh_runner import LiveIntradayRefreshRuntime


def run_live_intraday_refresh_once(
    *,
    dependencies: LiveIntradayRefreshDependencies | None = None,
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
    dependencies: LiveIntradayRefreshDependencies | None = None,
    execute_paper_orders: bool = False,
    execute_paper_option_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Execute one live intraday refresh run with injected dependencies."""
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
