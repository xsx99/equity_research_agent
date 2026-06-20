"""Public facade for the live preopen runtime."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from src.db.connection import get_session
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository

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
    execute_paper_option_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Execute one live preopen run with injected dependencies."""
    return run_preopen_once(
        dependencies=dependencies,
        execute_paper_orders=execute_paper_orders,
        execute_paper_option_orders=execute_paper_option_orders,
        now=now,
    )


def run_preopen_once(
    *,
    dependencies: LivePreopenDependencies | None = None,
    execute_paper_orders: bool = False,
    execute_paper_option_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Execute one live preopen run with injected dependencies."""
    if dependencies is not None:
        return LivePreopenRuntime(
            dependencies=dependencies,
            now=now,
            execute_paper_orders=execute_paper_orders,
            execute_paper_option_orders=execute_paper_option_orders,
        ).run()

    with get_session() as session:
        started_at = _resolve_now(now)
        try:
            result = LivePreopenRuntime(
                dependencies=build_live_preopen_dependencies(session),
                now=now,
                execute_paper_orders=execute_paper_orders,
                execute_paper_option_orders=execute_paper_option_orders,
            ).run()
        except Exception as exc:
            session.rollback()
            completed_at = _resolve_now(now)
            save_failed_preopen_runtime_run(
                session,
                started_at=started_at,
                completed_at=completed_at,
                exc=exc,
            )
            session.commit()
            raise
        save_preopen_runtime_run(session, result)
        session.commit()
        return result


def _save_runtime_run(session: object, payload: dict[str, object]) -> None:
    SqlAlchemyTradingRepository(session).save_runtime_run(payload)


def save_preopen_runtime_run(session: object, report: dict[str, object]) -> None:
    _save_runtime_run(session, _runtime_run_payload_from_report(report))


def save_failed_preopen_runtime_run(
    session: object,
    *,
    started_at: datetime,
    completed_at: datetime,
    exc: Exception,
) -> None:
    _save_runtime_run(
        session,
        _failed_runtime_run_payload(
            started_at=started_at,
            completed_at=completed_at,
            exc=exc,
        ),
    )


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
            "source": "run_live_preopen_once",
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
        "phase": "preopen",
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
            "source": "run_live_preopen_once",
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
