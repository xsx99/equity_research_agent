"""Trade loader helpers for the today router."""
from __future__ import annotations

import uuid
from typing import Any

from src.db.models.trading import CandidateOutcomeEvaluation, CandidateScore, PaperOptionOrder, PaperOrder, TradingDecision
from src.web.presenters.signal_evidence import signal_groups
from src.web.routers import today_loaders


def _load_trade_rows(session: Any) -> list[dict[str, Any]]:
    material_change_tickers = today_loaders._load_material_signal_change_tickers(session)
    rows = (
        session.query(TradingDecision)
        .order_by(TradingDecision.decision_time.desc())
        .limit(25)
        .all()
    )
    return [_serialize_trade_row(session, row, material_change_tickers) for row in rows]


def _serialize_trade_row(
    session: Any,
    row: TradingDecision,
    material_change_tickers: set[str],
) -> dict[str, Any]:
    metadata_json = dict(getattr(row, "metadata_json", {}) or {})
    key_drivers = list(getattr(row, "key_drivers_json", None) or metadata_json.get("key_drivers") or [])
    counterarguments = list(
        getattr(row, "counterarguments_json", None) or metadata_json.get("counterarguments") or []
    )
    candidate_score = getattr(row, "candidate_score", None)
    return {
        "trading_decision_id": str(row.trading_decision_id),
        "decision_time": row.decision_time,
        "created_at": row.created_at or row.decision_time,
        "ticker": row.ticker,
        "decision": row.decision,
        "instrument_type": row.instrument_type,
        "trade_identity": row.trade_identity,
        "selected_strategy_id": row.strategy_id,
        "expression_bucket_id": row.expression_bucket_id,
        "approved_weight": getattr(row, "approved_weight", None),
        "target_weight": getattr(row, "target_weight", None),
        "time_horizon": getattr(row, "time_horizon", None),
        "max_loss_pct": getattr(row, "max_loss_pct", None),
        "entry_plan": metadata_json.get("entry_plan"),
        "exit_plan": metadata_json.get("exit_plan"),
        "confidence": row.confidence,
        "risk_status": row.risk_decision.status if row.risk_decision else None,
        "order_status": _load_order_status(session, row.trading_decision_id),
        "material_signal_change": str(row.ticker).upper() in material_change_tickers,
        "thesis": getattr(row, "thesis", None),
        "key_drivers": key_drivers,
        "counterarguments": counterarguments,
        "invalidators": list(getattr(row, "invalidators_json", None) or []),
        "metadata_json": metadata_json,
        "core_signal_evidence": dict(getattr(candidate_score, "core_signal_evidence_json", None) or {})
        if candidate_score
        else {},
    }


def _ensure_trade_rows_include_ticker(
    session: Any,
    trade_rows: list[dict[str, Any]],
    ticker: str | None,
) -> list[dict[str, Any]]:
    normalized_ticker = str(ticker or "").strip().upper()
    if not normalized_ticker:
        return trade_rows
    if any(str(row.get("ticker") or "").strip().upper() == normalized_ticker for row in trade_rows):
        return trade_rows

    material_change_tickers = today_loaders._load_material_signal_change_tickers(session)
    latest_row = (
        session.query(TradingDecision)
        .filter(TradingDecision.ticker == normalized_ticker)
        .order_by(TradingDecision.decision_time.desc())
        .first()
    )
    if latest_row is None:
        return trade_rows

    return [*trade_rows, _serialize_trade_row(session, latest_row, material_change_tickers)]


def _load_order_status(session: Any, trading_decision_id: uuid.UUID) -> str | None:
    paper_order = session.query(PaperOrder).filter(PaperOrder.trading_decision_id == trading_decision_id).first()
    if paper_order is not None:
        return today_loaders._normalize_order_status(paper_order.status)
    option_order = (
        session.query(PaperOptionOrder)
        .filter(PaperOptionOrder.trading_decision_id == trading_decision_id)
        .first()
    )
    if option_order is not None:
        return today_loaders._normalize_order_status(option_order.status)
    return None


def _load_trade_detail(session: Any, decision_id: str) -> dict[str, Any] | None:
    try:
        rid = uuid.UUID(str(decision_id))
    except ValueError:
        return None
    row = session.query(TradingDecision).filter_by(trading_decision_id=rid).first()
    if row is None:
        return None
    candidate_score = getattr(row, "candidate_score", None)
    signal_snapshot = candidate_score.signal_snapshot if candidate_score else None
    metadata_json = dict(getattr(row, "metadata_json", {}) or {})
    score_rows = []
    if candidate_score:
        related_scores = (
            session.query(CandidateScore)
            .filter(CandidateScore.signal_snapshot_id == candidate_score.signal_snapshot_id)
            .order_by(CandidateScore.candidate_score.desc())
            .all()
        )
        score_rows = [
            {"strategy_id": score.strategy_id, "candidate_score": score.candidate_score}
            for score in related_scores
        ]
    outcomes = (
        session.query(CandidateOutcomeEvaluation)
        .filter(CandidateOutcomeEvaluation.candidate_score_id == getattr(row, "candidate_score_id", None))
        .order_by(CandidateOutcomeEvaluation.created_at.desc())
        .limit(10)
        .all()
    )
    risk_decision = None
    risk_decision_obj = getattr(row, "risk_decision", None)
    if risk_decision_obj:
        risk_decision = {
            "status": risk_decision_obj.status,
            "reason_code": risk_decision_obj.reason_code,
            "generated_hedge_action": getattr(risk_decision_obj, "generated_hedge_action_json", None),
            "lookahead_risk_source": today_loaders._risk_decision_lookahead_source(risk_decision_obj),
            "applied_rules": today_loaders._risk_applied_rules(getattr(risk_decision_obj, "applied_rules_json", None)),
        }
    prompt_run = getattr(row, "prompt_run", None)
    return {
        "trading_decision_id": str(row.trading_decision_id),
        "ticker": row.ticker,
        "decision": row.decision,
        "decision_time": row.decision_time,
        "strategy_id": row.strategy_id,
        "expression_bucket_id": row.expression_bucket_id,
        "trade_identity": row.trade_identity,
        "confidence": row.confidence,
        "approved_weight": getattr(row, "approved_weight", None),
        "target_weight": getattr(row, "target_weight", None),
        "time_horizon": getattr(row, "time_horizon", None),
        "max_loss_pct": getattr(row, "max_loss_pct", None),
        "thesis": getattr(row, "thesis", None),
        "entry_plan": metadata_json.get("entry_plan"),
        "exit_plan": metadata_json.get("exit_plan"),
        "key_drivers": list(getattr(row, "key_drivers_json", None) or metadata_json.get("key_drivers") or []),
        "counterarguments": list(
            getattr(row, "counterarguments_json", None) or metadata_json.get("counterarguments") or []
        ),
        "invalidators": list(getattr(row, "invalidators_json", None) or []),
        "metadata_json": metadata_json,
        "core_signal_evidence": dict(getattr(candidate_score, "core_signal_evidence_json", None) or {})
        if candidate_score
        else {},
        "llm_decision_json": prompt_run.parsed_output_json if prompt_run else {},
        "validation_status": prompt_run.parse_status if prompt_run else "unavailable",
        "signal_snapshot": signal_snapshot.signal_json if signal_snapshot else {},
        "strategy_scores": tuple(score_rows),
        "risk_decision": risk_decision,
        "outcomes": tuple(
            {
                "evaluation_status": outcome.evaluation_status,
                "alpha": outcome.alpha,
            }
            for outcome in outcomes
        ),
    }


def _merge_audit_detail_into_workspace_detail(
    detail: dict[str, Any] | None,
    audit_detail: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if detail is None:
        return None
    if audit_detail is None:
        return detail
    if "latest_conclusion" in audit_detail and "tabs" in audit_detail:
        return audit_detail

    latest_conclusion = dict(detail.get("latest_conclusion") or {})
    trade_decision = dict(latest_conclusion.get("trade_decision") or {})
    risk_summary = dict(latest_conclusion.get("risk_summary") or {})
    tabs = dict(detail.get("tabs") or {})
    risk_tab = dict(tabs.get("risk") or {})

    trade_decision["summary"] = (
        trade_decision.get("summary")
        if str(trade_decision.get("summary") or "").strip() and trade_decision.get("summary") != "No material update"
        else _audit_trade_summary(audit_detail)
    )
    if not trade_decision.get("key_drivers"):
        trade_decision["key_drivers"] = list(audit_detail.get("key_drivers") or [])
    if not trade_decision.get("counterarguments"):
        trade_decision["counterarguments"] = list(audit_detail.get("counterarguments") or [])
    if not trade_decision.get("invalidators"):
        trade_decision["invalidators"] = list(audit_detail.get("invalidators") or [])
    if not trade_decision.get("strategy_id") or trade_decision.get("strategy_id") == "No material update":
        trade_decision["strategy_id"] = audit_detail.get("strategy_id") or trade_decision.get("strategy_id")
    if (
        not trade_decision.get("expression_bucket_id")
        or trade_decision.get("expression_bucket_id") == "No material update"
    ):
        trade_decision["expression_bucket_id"] = (
            audit_detail.get("expression_bucket_id") or trade_decision.get("expression_bucket_id")
        )
    if audit_detail.get("confidence") is not None:
        trade_decision["confidence"] = audit_detail.get("confidence")
    if audit_detail.get("approved_weight") is not None:
        trade_decision["approved_weight"] = audit_detail.get("approved_weight")

    trade_plan = dict(latest_conclusion.get("trade_plan") or {})
    if audit_detail.get("thesis"):
        trade_plan["thesis"] = _audit_trade_summary(audit_detail)
    if audit_detail.get("time_horizon") is not None:
        trade_plan["time_horizon"] = audit_detail.get("time_horizon")
    if audit_detail.get("target_weight") is not None:
        trade_plan["target_weight"] = audit_detail.get("target_weight")
    if audit_detail.get("approved_weight") is not None:
        trade_plan["approved_weight"] = audit_detail.get("approved_weight")
    if audit_detail.get("max_loss_pct") is not None:
        trade_plan["max_loss_pct"] = audit_detail.get("max_loss_pct")
    if audit_detail.get("entry_plan") is not None:
        trade_plan["entry_plan"] = audit_detail.get("entry_plan")
    if audit_detail.get("exit_plan") is not None:
        trade_plan["exit_plan"] = audit_detail.get("exit_plan")
    if audit_detail.get("key_drivers"):
        trade_plan["edge"] = tuple(audit_detail.get("key_drivers") or ())
    if audit_detail.get("invalidators"):
        trade_plan["invalidators"] = tuple(audit_detail.get("invalidators") or ())

    bull_bear = dict(latest_conclusion.get("bull_bear") or {})
    if audit_detail.get("confidence") is not None:
        bull_bear["confidence"] = audit_detail.get("confidence")
    if audit_detail.get("key_drivers"):
        bull_bear["bull_points"] = tuple(audit_detail.get("key_drivers") or ())
    if audit_detail.get("counterarguments"):
        bull_bear["bear_points"] = tuple(audit_detail.get("counterarguments") or ())

    signal_groups_value = signal_groups(audit_detail.get("core_signal_evidence"))
    if signal_groups_value:
        latest_conclusion["signal_groups"] = signal_groups_value

    if (
        not risk_summary.get("reason")
        or risk_summary.get("reason") == "No material update"
    ) and isinstance(audit_detail.get("risk_decision"), dict):
        risk_summary["reason"] = audit_detail["risk_decision"].get("reason_code") or risk_summary.get("reason")
    if not risk_summary.get("lookahead_risk_source") and isinstance(audit_detail.get("risk_decision"), dict):
        risk_summary["lookahead_risk_source"] = audit_detail["risk_decision"].get("lookahead_risk_source")
    if not risk_summary.get("hedge_overlay_reason") and isinstance(audit_detail.get("risk_decision"), dict):
        generated_hedge_action = audit_detail["risk_decision"].get("generated_hedge_action")
        if isinstance(generated_hedge_action, dict):
            risk_summary["hedge_overlay_reason"] = generated_hedge_action.get("reason_code")
    if not risk_summary.get("applied_rules") and isinstance(audit_detail.get("risk_decision"), dict):
        risk_summary["applied_rules"] = audit_detail["risk_decision"].get("applied_rules") or ()

    latest_conclusion["trade_decision"] = trade_decision
    latest_conclusion["trade_plan"] = trade_plan
    latest_conclusion["bull_bear"] = bull_bear
    latest_conclusion["risk_summary"] = risk_summary

    tabs["risk"] = risk_tab

    return {
        **detail,
        "latest_conclusion": latest_conclusion,
        "tabs": tabs,
    }


def _audit_trade_summary(audit_detail: dict[str, Any]) -> str:
    thesis = str(audit_detail.get("thesis") or "").strip()
    if thesis:
        return thesis
    metadata = audit_detail.get("metadata_json")
    if isinstance(metadata, dict):
        selection_reason = str(metadata.get("selection_reason") or "").strip()
        if selection_reason:
            return selection_reason
    return "No material update"


def _latest_trade_decision_id_for_ticker(
    trade_rows: list[dict[str, Any]],
    ticker: str | None,
) -> str | None:
    normalized_ticker = str(ticker or "").strip().upper()
    if not normalized_ticker:
        return None

    matching_rows = [row for row in trade_rows if str(row.get("ticker") or "").strip().upper() == normalized_ticker]
    if not matching_rows:
        return None

    latest_row = max(
        matching_rows,
        key=lambda row: row.get("decision_time") or row.get("created_at") or "",
    )
    return str(latest_row.get("trading_decision_id") or "") or None
