"""DB repository helpers for the research pipeline.

All functions take an explicit ``session`` so callers control transaction
boundaries.  None of these helpers commit; that is the caller's responsibility.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.db.models.evaluation import EvalResult
from src.db.models.research import ResearchOutput, ResearchRun, ResearchTimeHorizon, RunStatus
from src.db.models.watch_list import Watchlist
from src.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Watchlist helpers
# ---------------------------------------------------------------------------


def get_watchlist(session: Session) -> list[Watchlist]:
    """Return all watchlist rows (active and inactive)."""
    return session.query(Watchlist).order_by(Watchlist.created_at).all()


def get_active_tickers(session: Session) -> list[str]:
    """Return ticker symbols for all active watchlist entries."""
    rows = session.query(Watchlist.ticker).filter(Watchlist.is_active.is_(True)).all()
    return [row.ticker for row in rows]


def add_ticker(session: Session, ticker: str) -> Watchlist:
    """Add a ticker to the watchlist (or reactivate if already present).

    Returns the upserted :class:`~src.db.models.watch_list.Watchlist` row.
    """
    ticker = ticker.upper().strip()
    existing = session.query(Watchlist).filter(Watchlist.ticker == ticker).first()
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            logger.info("watchlist_ticker_reactivated", ticker=ticker)
        return existing
    row = Watchlist(id=uuid.uuid4(), ticker=ticker, is_active=True)
    session.add(row)
    logger.info("watchlist_ticker_added", ticker=ticker)
    return row


def deactivate_ticker(session: Session, ticker: str) -> bool:
    """Deactivate a watchlist ticker.  Returns ``True`` if the row existed."""
    ticker = ticker.upper().strip()
    row = session.query(Watchlist).filter(Watchlist.ticker == ticker).first()
    if row is None:
        return False
    row.is_active = False
    logger.info("watchlist_ticker_deactivated", ticker=ticker)
    return True


# ---------------------------------------------------------------------------
# ResearchRun helpers
# ---------------------------------------------------------------------------


def create_run(
    session: Session,
    *,
    ticker: str,
    as_of: datetime,
    prompt_version: str,
    model_name: str,
    input_json: dict[str, Any],
) -> ResearchRun:
    """Create a new :class:`~src.db.models.research.ResearchRun` with ``queued`` status."""
    run = ResearchRun(
        run_id=uuid.uuid4(),
        ticker=ticker.upper(),
        as_of=as_of,
        prompt_version=prompt_version,
        model_name=model_name,
        input_json=input_json,
        status=RunStatus.QUEUED.value,
    )
    session.add(run)
    logger.info("research_run_created", ticker=ticker, run_id=str(run.run_id))
    return run


def mark_run_running(session: Session, run: ResearchRun) -> None:
    """Transition a run to ``running`` and record ``started_at``."""
    run.status = RunStatus.RUNNING.value
    run.started_at = datetime.now(timezone.utc)
    logger.info("research_run_started", run_id=str(run.run_id), ticker=run.ticker)


def mark_run_succeeded(session: Session, run: ResearchRun) -> None:
    """Transition a run to ``succeeded`` and record ``finished_at``."""
    run.status = RunStatus.SUCCEEDED.value
    run.finished_at = datetime.now(timezone.utc)
    logger.info("research_run_succeeded", run_id=str(run.run_id), ticker=run.ticker)


def mark_run_failed(
    session: Session, run: ResearchRun, error_message: str
) -> None:
    """Transition a run to ``failed``, record the error and ``finished_at``."""
    run.status = RunStatus.FAILED.value
    run.error_message = error_message
    run.finished_at = datetime.now(timezone.utc)
    logger.error(
        "research_run_failed",
        run_id=str(run.run_id),
        ticker=run.ticker,
        error=error_message,
    )


# ---------------------------------------------------------------------------
# ResearchOutput helpers
# ---------------------------------------------------------------------------


def persist_output(
    session: Session,
    run_id: uuid.UUID,
    output_data: dict[str, Any],
) -> ResearchOutput:
    """Persist a validated structured output for the given *run_id*.

    *output_data* must match :class:`~src.agents.research.StructuredResearchOutput`.
    """
    output = ResearchOutput(
        run_id=run_id,
        output_json=output_data,
        decision=output_data["decision"],
        confidence=output_data["confidence"],
        time_horizon=output_data["time_horizon"],
        actionability=output_data["actionability"],
        thesis_summary=output_data["thesis_summary"],
    )
    session.add(output)
    logger.info(
        "research_output_persisted",
        run_id=str(run_id),
        decision=output_data["decision"],
        confidence=output_data["confidence"],
    )
    return output


# ---------------------------------------------------------------------------
# EvalResult helpers
# ---------------------------------------------------------------------------


def get_eligible_runs(
    session: Session,
    as_of_cutoff: datetime,
) -> list[tuple[ResearchRun, ResearchOutput]]:
    """Return (run, output) pairs eligible for evaluation.

    Eligibility: succeeded status, valid time_horizon, and
    as_of + horizon_days <= as_of_cutoff (window has fully elapsed).
    Includes runs that already have an EvalResult (upsert semantics).
    """
    horizon_map = ResearchTimeHorizon.days_mapping()
    valid_horizons = list(horizon_map.keys())

    rows = (
        session.query(ResearchRun, ResearchOutput)
        .join(ResearchOutput, ResearchRun.run_id == ResearchOutput.run_id)
        .filter(
            ResearchRun.status == RunStatus.SUCCEEDED.value,
            ResearchOutput.time_horizon.in_(valid_horizons),
        )
        .all()
    )

    eligible = []
    for run, output in rows:
        horizon_days = horizon_map.get(output.time_horizon)
        if horizon_days is None:
            # Defensive: the SQL query already filters to valid_horizons,
            # so this branch is unreachable in practice.
            logger.warning(
                "get_eligible_runs_unknown_horizon",
                run_id=str(run.run_id),
                time_horizon=output.time_horizon,
            )
            continue
        if run.as_of + timedelta(days=horizon_days) <= as_of_cutoff:
            eligible.append((run, output))
    return eligible


def get_same_day_eval_candidates(
    session: Session,
    trade_date: date,
) -> list[tuple[ResearchRun, ResearchOutput]]:
    """Return succeeded `1d` runs created on *trade_date*."""
    rows = (
        session.query(ResearchRun, ResearchOutput)
        .join(ResearchOutput, ResearchRun.run_id == ResearchOutput.run_id)
        .filter(
            ResearchRun.status == RunStatus.SUCCEEDED.value,
            ResearchOutput.time_horizon == ResearchTimeHorizon.ONE_DAY.value,
        )
        .all()
    )

    eligible: list[tuple[ResearchRun, ResearchOutput]] = []
    for run, output in rows:
        if output.time_horizon != ResearchTimeHorizon.ONE_DAY.value:
            continue
        run_as_of = run.as_of
        if run_as_of.tzinfo is None:
            run_as_of = run_as_of.replace(tzinfo=timezone.utc)
        else:
            run_as_of = run_as_of.astimezone(timezone.utc)
        if run_as_of.date() == trade_date:
            eligible.append((run, output))
    return eligible


def get_latest_global_context_for_trade_date(
    session: Session,
    trade_date: date,
) -> Optional[dict[str, Any]]:
    """Return the latest stored global_context block for *trade_date*."""
    rows = (
        session.query(ResearchRun)
        .order_by(ResearchRun.as_of.desc())
        .all()
    )
    for run in rows:
        run_as_of = run.as_of
        if run_as_of.tzinfo is None:
            run_as_of = run_as_of.replace(tzinfo=timezone.utc)
        else:
            run_as_of = run_as_of.astimezone(timezone.utc)
        if run_as_of.date() != trade_date:
            continue
        input_json = run.input_json if isinstance(run.input_json, dict) else {}
        global_context = input_json.get("global_context")
        if isinstance(global_context, dict):
            return global_context
    return None


def upsert_eval_result(
    session: Session,
    *,
    run_id: uuid.UUID,
    horizon_days: int,
    realized_return: Optional[float],
    benchmark_return: Optional[float],
    benchmark_symbol: str,
    evaluation_method: str,
    evaluation_params: Optional[dict[str, Any]],
    outcome_label: Optional[str],
) -> EvalResult:
    """Insert or overwrite an EvalResult row for the given run_id."""
    existing = session.query(EvalResult).filter(EvalResult.run_id == run_id).first()
    if existing is not None:
        existing.horizon_days = horizon_days
        existing.realized_return = realized_return
        existing.benchmark_return = benchmark_return
        existing.benchmark_symbol = benchmark_symbol
        existing.evaluation_method = evaluation_method
        existing.evaluation_params = evaluation_params
        existing.outcome_label = outcome_label
        logger.info("eval_result_updated", run_id=str(run_id), outcome_label=outcome_label)
        return existing
    result = EvalResult(
        run_id=run_id,
        horizon_days=horizon_days,
        realized_return=realized_return,
        benchmark_return=benchmark_return,
        benchmark_symbol=benchmark_symbol,
        evaluation_method=evaluation_method,
        evaluation_params=evaluation_params,
        outcome_label=outcome_label,
    )
    session.add(result)
    logger.info("eval_result_created", run_id=str(run_id), outcome_label=outcome_label)
    return result
