"""DB repository helpers for the research pipeline.

All functions take an explicit ``session`` so callers control transaction
boundaries.  None of these helpers commit; that is the caller's responsibility.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.db.models.research import ResearchOutput, ResearchRun, RunStatus
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
