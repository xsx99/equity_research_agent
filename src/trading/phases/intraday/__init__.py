"""Public facade for the live intraday refresh phase."""
from __future__ import annotations

from datetime import datetime, timezone
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
        started_at = _resolve_now(now)
        try:
            result = LiveIntradayRefreshRuntime(
                dependencies=build_live_intraday_refresh_dependencies(session),
                now=now,
                execute_paper_orders=execute_paper_orders,
                execute_paper_option_orders=execute_paper_option_orders,
            ).run()
        except Exception as exc:
            session.rollback()
            completed_at = _resolve_now(now)
            save_failed_intraday_runtime_run(
                session,
                started_at=started_at,
                completed_at=completed_at,
                exc=exc,
            )
            session.commit()
            raise
        save_intraday_runtime_run(session, result)
        session.commit()
        return result


def build_live_intraday_refresh_dependencies(session: object | None = None) -> object:
    """Build the default production dependency graph for one live intraday refresh run."""
    from src.trading.phases.intraday.dependencies import (
        build_live_intraday_refresh_dependencies as _build_live_intraday_refresh_dependencies,
    )

    return _build_live_intraday_refresh_dependencies(session)


def save_intraday_runtime_run(session: object, report: dict[str, object]) -> None:
    _sqlalchemy_repository_cls()(session).save_runtime_run(_runtime_run_payload_from_report(report))


def save_failed_intraday_runtime_run(
    session: object,
    *,
    started_at: datetime,
    completed_at: datetime,
    exc: Exception,
) -> None:
    _sqlalchemy_repository_cls()(session).save_runtime_run(
        _failed_runtime_run_payload(started_at=started_at, completed_at=completed_at, exc=exc)
    )


def _sqlalchemy_repository_cls() -> object:
    repository_cls = globals().get("SqlAlchemyTradingRepository")
    if repository_cls is not None:
        return repository_cls
    from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository

    return SqlAlchemyTradingRepository


def _runtime_run_payload_from_report(report: dict[str, object]) -> dict[str, object]:
    raw_as_of = report["as_of"]
    raw_started_at = report.get("started_at") or raw_as_of
    raw_completed_at = report.get("completed_at") or raw_as_of
    trade_date = report.get("trade_date") or _datetime_like(raw_as_of).date()
    return {
        "phase": report["phase"],
        "status": report["status"],
        "trade_date": trade_date,
        "as_of": raw_as_of,
        "started_at": raw_started_at,
        "completed_at": raw_completed_at,
        "summary_json": dict(report.get("summary") or {}),
        "execution_json": dict(report.get("execution") or {}),
        "metadata_json": {
            "source": "run_live_intraday_refresh_once",
            "report_version": "v1",
        },
    }


def _failed_runtime_run_payload(
    *,
    started_at: datetime,
    completed_at: datetime,
    exc: Exception,
) -> dict[str, object]:
    reason = str(exc).strip() or exc.__class__.__name__
    return {
        "phase": "intraday_refresh",
        "status": "failed",
        "trade_date": completed_at.date(),
        "as_of": completed_at,
        "started_at": started_at,
        "completed_at": completed_at,
        "summary_json": {
            "reasons": [reason],
            "exception_type": exc.__class__.__name__,
        },
        "execution_json": {},
        "metadata_json": {
            "source": "run_live_intraday_refresh_once",
            "report_version": "v1",
        },
    }


def _resolve_now(now: Callable[[], datetime] | None) -> datetime:
    current = now() if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current


def _datetime_like(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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
