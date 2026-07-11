"""Candidate loader helpers for the today router."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import selectinload

from src.db.models.trading import CandidateScore, TradingDecision
from src.web.presenters.today_copy import (
    candidate_result_label,
    manual_request_mode_label,
    manual_request_status_label,
    strategy_label,
    trade_identity_label,
)
from src.web.routers import today_loaders


_CANDIDATE_LOOKBACK_LIMIT = 500
_CANDIDATE_FALLBACK_LIMIT = 25
_SCANNER_SELECTION_SOURCE = "scanner"
_MANUAL_SELECTION_SOURCES = {"manual_request", "watchlist_pin"}


def _attach_candidate_summary(candidates: dict[str, Any]) -> dict[str, Any]:
    decision_readout = tuple(candidates.get("decision_readout") or ())
    actionable = sum(1 for row in decision_readout if row.get("action_required"))
    watch = sum(
        1
        for row in decision_readout
        if "watch" in str(row.get("current_outcome_label") or "").strip().lower()
    )
    blocked = sum(
        1
        for row in decision_readout
        if "blocked" in str(row.get("current_outcome_label") or "").strip().lower()
        or "no trade" in str(row.get("current_outcome_label") or "").strip().lower()
    )
    return {
        **candidates,
        "aggregate_summary": {
            "scored": len(decision_readout),
            "actionable": actionable,
            "watch": watch,
            "blocked": blocked,
        },
    }


def _build_candidates_summary(
    *,
    rows: tuple[dict[str, Any], ...],
    manual_requests: tuple[dict[str, Any], ...],
    themes: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    action_queue: list[dict[str, Any]] = []
    for row in manual_requests[:3]:
        action_queue.append(
            {
                "ticker": row["ticker"],
                "label": row["status_label"],
                "summary": row["operator_summary"],
            }
        )
    for row in rows[:4]:
        action_queue.append(
            {
                "ticker": row["ticker"],
                "label": row["current_outcome_label"],
                "summary": row["operator_summary"],
            }
        )

    return {
        "action_queue": tuple(action_queue),
        "theme_count": len(themes),
    }


def _load_candidate_rows(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(CandidateScore)
        .options(
            selectinload(CandidateScore.trade_classifications),
            selectinload(CandidateScore.watch_candidates),
        )
        .order_by(CandidateScore.decision_time.desc(), CandidateScore.candidate_score.desc())
        .limit(_CANDIDATE_LOOKBACK_LIMIT)
        .all()
    )
    rows = _select_today_candidate_rows(rows)
    latest_decisions = _latest_trading_decisions_by_ticker(session, rows)
    return tuple(
        _candidate_row_payload(row, latest_decisions.get(str(row.ticker or "").strip().upper()))
        for row in rows
    )


def _select_today_candidate_rows(rows: list[CandidateScore]) -> tuple[CandidateScore, ...]:
    """Keep the latest scanner cohort even when a narrower manual-review run is newer."""
    ordered_rows = tuple(rows)
    scanner_key = _latest_candidate_run_key_for_sources(ordered_rows, {_SCANNER_SELECTION_SOURCE})
    if scanner_key is None:
        return ordered_rows[:_CANDIDATE_FALLBACK_LIMIT]

    manual_key = _latest_candidate_run_key_for_sources(ordered_rows, _MANUAL_SELECTION_SOURCES)
    selected: list[CandidateScore] = []
    for row in ordered_rows:
        row_key = _candidate_run_key(row)
        selection_source = str(getattr(row, "selection_source", "") or "").strip()
        if row_key == scanner_key:
            selected.append(row)
            continue
        if manual_key is not None and row_key == manual_key and selection_source in _MANUAL_SELECTION_SOURCES:
            selected.append(row)
    return tuple(selected)


def _latest_candidate_run_key_for_sources(rows: tuple[CandidateScore, ...], sources: set[str]) -> tuple[str, str] | None:
    for row in rows:
        selection_source = str(getattr(row, "selection_source", "") or "").strip()
        if selection_source in sources:
            return _candidate_run_key(row)
    return None


def _candidate_run_key(row: CandidateScore) -> tuple[str, str]:
    strategy_run_id = getattr(row, "strategy_run_id", None)
    if strategy_run_id:
        return ("run", str(strategy_run_id))
    decision_time = getattr(row, "decision_time", None)
    if decision_time is not None:
        return ("decision_time", str(decision_time))
    return ("row", str(id(row)))


def _candidate_row_payload(row: CandidateScore, latest_decision: Any | None) -> dict[str, Any]:
    result_status = _candidate_result_status(row, latest_decision=latest_decision)
    trade_identity = _candidate_trade_identity(row, latest_decision=latest_decision)
    return {
        "ticker": row.ticker,
        "candidate_score": float(row.candidate_score) if row.candidate_score is not None else None,
        "confidence": float(row.candidate_score) if row.candidate_score is not None else None,
        "decision_time": row.decision_time.isoformat() if row.decision_time is not None else None,
        "selection_source": row.selection_source,
        "why_reviewed_label": strategy_label(row.selection_source),
        "result_status": result_status,
        "current_outcome_label": candidate_result_label(result_status),
        "trade_identity": trade_identity,
        "trade_identity_label": trade_identity_label(trade_identity),
        "strategy_match": row.strategy_id,
        "strategy_label": strategy_label(row.strategy_id),
        "core_signal_evidence": dict(getattr(row, "core_signal_evidence_json", None) or {}),
        "selection_reason": getattr(row, "selection_reason", None),
        "risk_tags": list(getattr(row, "risk_tags_json", None) or []),
        "invalidators": list(getattr(row, "invalidators_json", None) or []),
        "missing_required_signals": list(getattr(row, "missing_required_signals_json", None) or []),
        "operator_summary": today_loaders._sentence_join(
            strategy_label(row.selection_source),
            candidate_result_label(result_status),
            trade_identity_label(trade_identity),
        ),
        "detail_internal_ids": {
            "selection_source": row.selection_source,
            "result_status": result_status,
            "trade_identity": trade_identity,
            "strategy_match": row.strategy_id,
        },
    }


def _latest_trading_decisions_by_ticker(session: Any, rows: list[CandidateScore]) -> dict[str, Any]:
    tickers = sorted({str(row.ticker or "").strip().upper() for row in rows if str(row.ticker or "").strip()})
    if not tickers:
        return {}
    decisions = (
        session.query(TradingDecision)
        .filter(TradingDecision.ticker.in_(tickers))
        .order_by(TradingDecision.decision_time.desc(), TradingDecision.created_at.desc())
        .limit(100)
        .all()
    )
    latest: dict[str, Any] = {}
    for decision in decisions:
        ticker = str(getattr(decision, "ticker", "") or "").strip().upper()
        if ticker and ticker not in latest:
            latest[ticker] = decision
    return latest


def _load_manual_requests(session: Any) -> tuple[dict[str, Any], ...]:
    rows = today_loaders.SqlAlchemyTradingRepository(session).load_manual_review_audit_rows()
    return tuple(
        {
            "manual_ticker_request_id": row.manual_ticker_request_id,
            "ticker": row.ticker,
            "reason": row.reason,
            "mode": row.mode,
            "mode_label": manual_request_mode_label(row.mode),
            "status": row.status,
            "status_label": manual_request_status_label(row.status),
            "latest_result_status": row.latest_result_status,
            "latest_result_label": candidate_result_label(row.latest_result_status),
            "last_evaluated_at": row.last_evaluated_at.isoformat() if row.last_evaluated_at is not None else None,
            "latest_signal_snapshot_id": row.latest_signal_snapshot_id,
            "latest_trading_decision_id": row.latest_trading_decision_id,
            "latest_decision_action": row.latest_decision_action,
            "latest_risk_outcome": row.latest_risk_outcome,
            "latest_order_status": row.latest_order_status,
            "latest_execution_status": row.latest_execution_status,
            "latest_execution_time": row.latest_execution_time.isoformat() if row.latest_execution_time is not None else None,
            "execution_path_state": row.execution_path_state,
            "latest_block_reason": row.latest_block_reason,
            "linkage_state": row.linkage_state,
            "operator_summary": today_loaders._sentence_join(
                f"{manual_request_mode_label(row.mode)} because {row.reason}",
                f"Latest result: {candidate_result_label(row.latest_result_status)}"
                if row.latest_result_status
                else None,
            ),
        }
        for row in rows
    )


def _candidate_result_status(row: CandidateScore, *, latest_decision: Any | None = None) -> str:
    decision_status = _candidate_result_status_from_decision(latest_decision)
    if decision_status is not None:
        return decision_status
    if row.trade_classifications:
        return str(row.trade_classifications[0].result_status or "candidate")
    if row.watch_candidates:
        return str(row.watch_candidates[0].result_status or row.rejection_reason or row.candidate_status or "candidate")
    return str(row.rejection_reason or row.candidate_status or "candidate")


def _candidate_result_status_from_decision(decision: Any | None) -> str | None:
    if decision is None:
        return None
    action = str(getattr(decision, "decision", "") or "").strip().lower()
    if action in {"no_trade", "avoid_event_option"}:
        return "no_trade"
    if action == "hold":
        return "ordinary_watch"
    if action in {"enter_long", "enter_short", "open_option_strategy"}:
        return "actionable_trade"
    if action in {"reduce", "exit", "close_option_strategy", "roll_option_strategy", "adjust_option_strategy"}:
        return "ordinary_watch"
    return None


def _candidate_trade_identity(row: CandidateScore, *, latest_decision: Any | None = None) -> str | None:
    if latest_decision is not None:
        trade_identity = str(getattr(latest_decision, "trade_identity", "") or "").strip()
        if trade_identity:
            return trade_identity
        if _candidate_result_status_from_decision(latest_decision) in {"no_trade", "ordinary_watch"}:
            return "watch_only"
    if row.trade_classifications:
        return row.trade_classifications[0].trade_identity
    if row.watch_candidates:
        return "watch_only"
    return None
