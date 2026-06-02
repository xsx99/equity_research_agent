"""DB repository helpers for the research pipeline.

All functions take an explicit ``session`` so callers control transaction
boundaries.  None of these helpers commit; that is the caller's responsibility.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.core.timezones import as_trade_date
from src.db.models.evaluation import EvalResult
from src.db.models.insider_trades import InsiderTrade
from src.db.models.research import ResearchOutput, ResearchRun, ResearchTimeHorizon, RunStatus
from src.db.models.watch_list import Watchlist
from src.core.logging import get_logger
from src.providers.market_data import MARKET_TIMEZONE

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
        if as_trade_date(run.as_of, MARKET_TIMEZONE) == trade_date:
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
        if as_trade_date(run.as_of, MARKET_TIMEZONE) != trade_date:
            continue
        input_json = run.input_json if isinstance(run.input_json, dict) else {}
        global_context = input_json.get("global_context")
        if isinstance(global_context, dict):
            return global_context
    return None


def _normalize_as_of(as_of: datetime) -> datetime:
    if as_of.tzinfo is None:
        return as_of.replace(tzinfo=timezone.utc)
    return as_of.astimezone(timezone.utc)


def _trade_to_research_input_dict(trade: InsiderTrade) -> dict[str, Any]:
    return {
        "insider_name": trade.insider_name,
        "insider_title": trade.insider_title,
        "transaction_type": trade.transaction_type,
        "transaction_date": trade.transaction_date.isoformat() if trade.transaction_date else None,
        "filing_date": trade.filing_date.isoformat() if trade.filing_date else None,
        "shares": trade.shares,
        "price_per_share": float(trade.price_per_share) if trade.price_per_share is not None else None,
        "total_value": float(trade.total_value) if trade.total_value is not None else None,
        "filing_url": trade.filing_url,
    }


def get_recent_insider_activity(
    session: Session,
    *,
    ticker: str,
    as_of: datetime,
    days: int = 30,
    limit: int = 5,
) -> dict[str, Any]:
    """Return a structured insider-activity summary for the research input."""
    normalized_as_of = _normalize_as_of(as_of)
    trade_date = normalized_as_of.date()
    cutoff = trade_date - timedelta(days=days)
    trades = (
        session.query(InsiderTrade)
        .filter(
            InsiderTrade.ticker == ticker.upper(),
            InsiderTrade.filing_date >= cutoff,
            InsiderTrade.filing_date <= trade_date,
        )
        .order_by(InsiderTrade.filing_date.desc(), InsiderTrade.transaction_date.desc())
        .all()
    )
    if not isinstance(trades, list):
        trades = []

    purchase_count = 0
    sale_count = 0
    net_shares = 0.0
    net_value = 0.0
    has_net_activity = False

    for trade in trades:
        tx_type = (trade.transaction_type or "").upper()
        shares = float(trade.shares) if trade.shares is not None else None
        total_value = (
            float(trade.total_value)
            if trade.total_value is not None
            else (
                float(trade.shares) * float(trade.price_per_share)
                if trade.shares is not None and trade.price_per_share is not None
                else None
            )
        )
        if tx_type == "P":
            purchase_count += 1
            has_net_activity = True
            if shares is not None:
                net_shares += shares
            if total_value is not None:
                net_value += total_value
        elif tx_type == "S":
            sale_count += 1
            has_net_activity = True
            if shares is not None:
                net_shares -= shares
            if total_value is not None:
                net_value -= total_value

    return {
        "window_days": days,
        "purchase_count": purchase_count,
        "sale_count": sale_count,
        "net_shares": net_shares if has_net_activity else None,
        "net_value": net_value if has_net_activity else None,
        "recent_trades": [_trade_to_research_input_dict(trade) for trade in trades[:limit]],
    }


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
