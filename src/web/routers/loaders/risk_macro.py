"""Risk and macro loader helpers for the today router."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session as SQLAlchemySession

from src.db.models.trading import IntradaySignalSnapshot, NewsAlert, PortfolioRiskSnapshot, RiskDecision, RiskFactorExposure
from src.web.presenters.today_risk_macro import build_today_risk_macro_payload
from src.web.routers import today_loaders


def _load_today_risk_macro(
    session: Any,
    *,
    latest_risk: PortfolioRiskSnapshot | None,
    latest_macro_snapshot: object | None,
) -> dict[str, Any]:
    exposures = today_loaders._load_risk_exposures(session)
    latest_intent = None
    risk_macro_context: dict[str, object] = {"macro_snapshot": latest_macro_snapshot}
    decision_time = latest_risk.decision_time if latest_risk is not None else None
    if isinstance(session, SQLAlchemySession):
        repository = today_loaders.SqlAlchemyTradingRepository(session)
        trade_date = (
            latest_risk.decision_time.date()
            if latest_risk is not None
            else None
        )
        if trade_date is not None and decision_time is not None:
            intents = repository.load_portfolio_risk_intents(trade_date=trade_date)
            latest_intent = intents[-1] if intents else None
            recent_news_since = decision_time - timedelta(days=4)
            risk_macro_context = repository.load_decision_available_risk_macro_context(
                trade_date=trade_date,
                decision_time=decision_time,
                event_time_start=decision_time,
                news_available_since=recent_news_since,
                news_limit=250,
                assessment_available_since=decision_time - timedelta(days=14),
                assessment_limit=250,
            )
    if latest_macro_snapshot is not None:
        risk_macro_context = {
            **risk_macro_context,
            "macro_snapshot": risk_macro_context.get("macro_snapshot") or latest_macro_snapshot,
        }
    return build_today_risk_macro_payload(
        latest_risk=latest_risk,
        latest_intent=latest_intent,
        risk_macro_context=risk_macro_context,
        exposures=exposures,
        as_of=decision_time,
    )


def _load_live_alerts(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(NewsAlert)
        .order_by(NewsAlert.published_at.desc())
        .limit(10)
        .all()
    )
    return tuple(
        {
            "ticker": row.ticker,
            "severity": row.severity,
            "headline": row.headline,
            "summary": row.summary,
            "source_ticker": getattr(row, "source_ticker", None),
            "readthrough_source_ticker": getattr(row, "readthrough_source_ticker", None),
        }
        for row in rows
    )


def _load_material_changes(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(IntradaySignalSnapshot)
        .order_by(IntradaySignalSnapshot.decision_time.desc())
        .limit(10)
        .all()
    )
    changes: list[dict[str, Any]] = []
    for row in rows:
        delta = row.delta_vs_baseline_json or {}
        if not delta:
            continue
        changes.append({"ticker": row.ticker, "summary": ", ".join(delta.keys())})
    return tuple(changes)


def _load_risk_exposures(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(RiskFactorExposure)
        .order_by(RiskFactorExposure.created_at.desc())
        .limit(20)
        .all()
    )
    return tuple(
        {
            "factor_type": row.factor_type,
            "factor_name": row.factor_value,
            "exposure": row.gross_exposure,
        }
        for row in rows
    )


def _load_material_signal_change_tickers(session: Any) -> set[str]:
    rows = (
        session.query(IntradaySignalSnapshot)
        .order_by(IntradaySignalSnapshot.decision_time.desc())
        .limit(100)
        .all()
    )
    tickers: set[str] = set()
    for row in rows:
        if row.delta_vs_baseline_json:
            tickers.add(str(row.ticker).upper())
    return tickers


def _load_risk_by_ticker(
    session: Any,
    *,
    tickers: tuple[str, ...] | None = None,
) -> dict[str, dict[str, Any]]:
    ticker_scope = _normalize_ticker_scope(tickers)
    query = session.query(RiskDecision)
    if ticker_scope is not None:
        query = query.filter(RiskDecision.ticker.in_(ticker_scope))
    rows = (
        query
        .order_by(RiskDecision.decision_time.desc(), RiskDecision.created_at.desc())
        .limit(100)
        .all()
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.ticker or "").strip().upper()
        if not ticker or ticker in grouped:
            continue
        lookahead_risk_source = _risk_decision_lookahead_source(row)
        generated_hedge_action = getattr(row, "generated_hedge_action_json", None)
        metadata_json = dict(getattr(row, "metadata_json", {}) or {})
        grouped[ticker] = {
            "status": row.status,
            "reason": row.reason_code,
            "lookahead_risk_source": lookahead_risk_source,
            "generated_hedge_action": generated_hedge_action,
            "applied_rules": _risk_applied_rules(getattr(row, "applied_rules_json", None)),
            "rule_checks": _risk_rule_checks(metadata_json.get("rule_checks")),
            "history": [
                {
                    "time": row.decision_time or row.created_at,
                    "status": row.status,
                    "summary": row.reason_code,
                }
            ],
        }
    return grouped


def _normalize_ticker_scope(tickers: tuple[str, ...] | None) -> tuple[str, ...] | None:
    if tickers is None:
        return None
    normalized = tuple(
        dict.fromkeys(
            ticker
            for raw_ticker in tickers
            if (ticker := str(raw_ticker or "").strip().upper())
        )
    )
    return normalized or None


def _risk_decision_lookahead_source(row: Any) -> str | None:
    metadata_json = dict(getattr(row, "metadata_json", {}) or {})
    direct_value = getattr(row, "lookahead_risk_source", None)
    if direct_value is not None:
        value = str(direct_value).strip()
        if value:
            return value
    metadata_value = metadata_json.get("lookahead_risk_source")
    if metadata_value is None:
        return None
    value = str(metadata_value).strip()
    return value or None


def _risk_applied_rules(value: Any) -> tuple[str, ...]:
    """Normalize ``applied_rules_json`` into readable rule labels.

    The risk manager is deterministic, so its "reasoning" is the set of rules it
    evaluated. Entries may be plain strings or dicts carrying a rule id / reason.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    labels: list[str] = []
    for item in value:
        if isinstance(item, dict):
            label = str(
                item.get("label")
                or item.get("rule")
                or item.get("rule_id")
                or item.get("name")
                or item.get("reason_code")
                or ""
            ).strip()
        else:
            label = str(item or "").strip()
        if label and label not in labels:
            labels.append(label)
    return tuple(labels)


def _risk_rule_checks(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    checks: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        checks.append(
            {
                "label": label,
                "observed": str(item.get("observed") or "").strip(),
                "cap": str(item.get("cap") or "").strip(),
                "passed": bool(item.get("passed")),
            }
        )
    return tuple(checks)


def _risk_decision_binding_constraint(row: Any) -> str | None:
    metadata_json = dict(getattr(row, "metadata_json", {}) or {})
    direct_value = getattr(row, "binding_constraint", None)
    if direct_value is not None:
        value = str(direct_value).strip()
        if value:
            return value
    metadata_value = metadata_json.get("binding_constraint")
    if metadata_value is None:
        return None
    value = str(metadata_value).strip()
    return value or None
