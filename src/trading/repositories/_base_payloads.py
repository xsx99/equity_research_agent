"""Dictionary payload builders for SQLAlchemy trading repositories."""
from __future__ import annotations

from typing import Any

from src.trading.risk.lookahead import HedgeActionRecord, PositionRiskActionRecord

from src.trading.repositories._base_common import _decimal_to_float


def _portfolio_snapshot_payload(row: Any) -> dict[str, Any]:
    return {
        "snapshot_time": row.snapshot_time.isoformat(),
        "cash_balance": _decimal_to_float(row.cash_balance),
        "account_equity": _decimal_to_float(row.account_equity),
        "net_liquidation_value": _decimal_to_float(row.net_liquidation_value),
        "buying_power": _decimal_to_float(row.buying_power),
        "day_pnl": _decimal_to_float(row.day_pnl),
        "realized_pnl": _decimal_to_float(row.realized_pnl),
        "unrealized_pnl": _decimal_to_float(row.unrealized_pnl),
        "metadata_json": dict(row.metadata_json or {}),
    }


def _portfolio_outcome_payload(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "snapshot_time": row.snapshot_time.isoformat(),
        "account_equity": _decimal_to_float(row.account_equity),
        "day_pnl": _decimal_to_float(row.day_pnl),
        "realized_pnl": _decimal_to_float(row.realized_pnl),
        "unrealized_pnl": _decimal_to_float(row.unrealized_pnl),
    }


def _candidate_score_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "strategy_id": row.strategy_id,
        "strategy_version": row.strategy_version,
        "candidate_score": _decimal_to_float(row.candidate_score),
        "selection_source": row.selection_source,
        "manual_request_id": str(row.manual_request_id) if row.manual_request_id is not None else None,
        "decision_time": row.decision_time.isoformat(),
    }


def _rejected_candidate_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "strategy_id": row.strategy_id,
        "strategy_version": row.strategy_version,
        "rejection_reason": row.rejection_reason,
        "selection_source": row.selection_source,
        "selection_reason": row.selection_reason,
        "core_signal_evidence": dict(row.core_signal_evidence_json or {}),
        "risk_tags": list(row.risk_tags_json or ()),
    }


def _trading_decision_payload(row: Any) -> dict[str, Any]:
    metadata_json = dict(getattr(row, "metadata_json", {}) or {})
    return {
        "ticker": row.ticker,
        "decision": row.decision,
        "strategy_id": row.strategy_id,
        "trade_identity": row.trade_identity,
        "instrument_type": row.instrument_type,
        "selection_source": row.selection_source,
        "confidence": _decimal_to_float(row.confidence),
        "target_weight": _decimal_to_float(row.target_weight),
        "approved_weight": _decimal_to_float(row.approved_weight),
        "key_drivers": list(getattr(row, "key_drivers_json", None) or metadata_json.get("key_drivers") or []),
        "counterarguments": list(
            getattr(row, "counterarguments_json", None) or metadata_json.get("counterarguments") or []
        ),
        "invalidators": list(getattr(row, "invalidators_json", None) or []),
        "decision_time": row.decision_time.isoformat(),
        "metadata_json": metadata_json,
    }


def _news_alert_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "alert_type": row.alert_type,
        "severity": row.severity,
        "sentiment": row.sentiment,
        "headline": row.headline,
        "summary": row.summary,
        "action_required": bool(row.action_required),
        "published_at": row.published_at.isoformat(),
    }


def _intraday_rebalance_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "action": row.action,
        "status": row.status,
        "reason_code": row.reason_code,
        "confidence": _decimal_to_float(row.confidence),
        "decision_time": row.decision_time.isoformat(),
    }


def _paper_order_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "action": row.action,
        "quantity": _decimal_to_float(row.quantity),
        "order_price": _decimal_to_float(row.order_price),
        "status": row.status,
        "trade_date": row.trade_date.isoformat(),
        "created_at": row.created_at.isoformat(),
    }


def _paper_execution_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "quantity": _decimal_to_float(row.quantity),
        "fill_price": _decimal_to_float(row.fill_price),
        "trade_date": row.trade_date.isoformat(),
        "executed_at": row.executed_at.isoformat(),
        "net_cash_effect": _decimal_to_float(row.net_cash_effect),
    }


def _portfolio_risk_snapshot_payload(row: Any) -> dict[str, Any]:
    return {
        "decision_time": row.decision_time.isoformat(),
        "account_equity": _decimal_to_float(row.account_equity),
        "cash_balance": _decimal_to_float(row.cash_balance),
        "buying_power": _decimal_to_float(row.buying_power),
        "net_exposure": _decimal_to_float(row.net_exposure),
        "gross_exposure": _decimal_to_float(row.gross_exposure),
        "metadata_json": dict(row.metadata_json or {}),
    }


def _position_risk_action_payload(action: PositionRiskActionRecord) -> dict[str, Any]:
    return {
        "ticker": action.ticker,
        "trade_identity": action.trade_identity,
        "action": action.action,
        "risk_source": action.risk_source,
        "severity": action.severity,
        "max_allowed_weight_override": action.max_allowed_weight_override,
        "reason_code": action.reason_code,
        "metadata_json": dict(action.metadata_json),
    }


def _hedge_action_payload(action: HedgeActionRecord) -> dict[str, Any]:
    return {
        "action": action.action,
        "risk_source": action.risk_source,
        "severity": action.severity,
        "target_underlier": action.target_underlier,
        "target_exposure_type": action.target_exposure_type,
        "coverage_ratio": action.coverage_ratio,
        "reason_code": action.reason_code,
        "metadata_json": dict(action.metadata_json),
    }


def _risk_factor_exposure_payload(row: Any) -> dict[str, Any]:
    return {
        "factor_type": row.factor_type,
        "factor_value": row.factor_value,
        "gross_exposure": _decimal_to_float(row.gross_exposure),
        "net_exposure": _decimal_to_float(row.net_exposure),
        "metadata_json": dict(row.metadata_json or {}),
    }


def _candidate_outcome_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "strategy_id": row.strategy_id,
        "trade_identity": row.trade_identity,
        "evaluation_status": row.evaluation_status,
        "candidate_return": _decimal_to_float(row.candidate_return),
        "alpha": _decimal_to_float(row.alpha),
        "benchmark_returns": dict(row.benchmark_returns_json or {}),
        "decision_time": row.decision_time.isoformat(),
    }


def _paper_option_decision_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "option_strategy_type": row.option_strategy_type,
        "status": row.status,
        "decision_action": row.decision_action,
        "created_at": row.created_at.isoformat(),
    }


def _paper_option_position_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "option_strategy_type": row.option_strategy_type,
        "quantity": row.quantity,
        "status": row.status,
        "opened_at": row.opened_at.isoformat(),
    }


def _option_risk_snapshot_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "option_strategy_type": row.option_strategy_type,
        "risk_status": row.risk_status,
        "reason_code": row.reason_code,
        "created_at": row.created_at.isoformat(),
    }


def _risk_hedge_overlay_payload(row: Any) -> dict[str, Any]:
    metadata_json = dict(row.metadata_json or {})
    generated_hedge_action = dict(metadata_json.get("generated_hedge_action") or {})
    return {
        "ticker": row.ticker,
        "action": row.action,
        "option_strategy_type": row.option_strategy_type,
        "rationale": row.rationale,
        "hedge_cost": _decimal_to_float(row.hedge_cost),
        "protected_notional": _decimal_to_float(row.protected_notional),
        "target_exposure_type": generated_hedge_action.get("target_exposure_type"),
        "protected_exposure_basis": generated_hedge_action.get("protected_exposure_basis"),
        "created_at": row.created_at.isoformat(),
        "metadata_json": metadata_json,
    }


def _hedge_effectiveness_payload(rows: tuple[Any, ...]) -> dict[str, Any]:
    action_counts: dict[str, int] = {}
    exposure_basis_counts: dict[str, int] = {}
    assignment_overlay_count = 0
    protected_notional = 0.0
    hedge_cost = 0.0
    for row in rows:
        action_counts[row.action] = action_counts.get(row.action, 0) + 1
        protected_notional += _decimal_to_float(row.protected_notional)
        hedge_cost += _decimal_to_float(row.hedge_cost)
        metadata_json = dict(row.metadata_json or {})
        generated_hedge_action = dict(metadata_json.get("generated_hedge_action") or {})
        target_exposure_type = generated_hedge_action.get("target_exposure_type")
        if target_exposure_type == "assignment":
            assignment_overlay_count += 1
        basis = generated_hedge_action.get("protected_exposure_basis")
        if isinstance(basis, str) and basis:
            exposure_basis_counts[basis] = exposure_basis_counts.get(basis, 0) + 1
    return {
        "overlay_count": len(rows),
        "assignment_overlay_count": assignment_overlay_count,
        "protected_notional": protected_notional,
        "hedge_cost": hedge_cost,
        "action_counts": action_counts,
        "protected_exposure_basis_counts": exposure_basis_counts,
    }
