"""Manual-review and intraday linkage helpers for SQLAlchemy trading repositories."""
from __future__ import annotations

from typing import Any


def _manual_request_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "mode": row.mode,
        "status": row.status,
        "latest_result_status": row.latest_result_status,
        "created_at": row.created_at.isoformat() if row.created_at is not None else None,
        "last_evaluated_at": row.last_evaluated_at.isoformat() if row.last_evaluated_at is not None else None,
    }


def _manual_review_execution_path_state(
    *,
    request: Any,
    decision: Any | None,
    risk: Any | None,
    order: Any | None,
    execution: Any | None,
    latest_signal_snapshot_id: str | None,
) -> tuple[str, str | None]:
    if latest_signal_snapshot_id is None:
        return "pending_evaluation", None
    if decision is None:
        return "snapshot_only", None
    if risk is not None and getattr(risk, "status", None) == "rejected":
        return "risk_blocked", getattr(risk, "reason_code", None)
    if order is None:
        if _manual_review_actionable_decision(decision):
            if getattr(request, "mode", None) == "review_only":
                return "eligible_no_order", "manual_request_review_only"
            return "eligible_no_order", "paper_order_not_submitted"
        return "decision_recorded", None
    if getattr(order, "status", None) == "rejected":
        return "order_rejected", getattr(order, "rejection_reason", None)
    if execution is not None or getattr(order, "status", None) == "filled":
        return "filled", None
    return "order_submitted", getattr(order, "rejection_reason", None)


def _manual_review_linkage_state(
    *,
    latest_signal_snapshot_id: str | None,
    decision: Any | None,
    risk: Any | None,
    order: Any | None,
    execution: Any | None,
) -> str:
    if latest_signal_snapshot_id is None:
        return "pending_evaluation"
    if decision is None:
        return "snapshot_only"
    if execution is not None:
        return "execution_linked"
    if order is not None:
        return "order_linked"
    if risk is not None:
        return "risk_linked"
    return "decision_linked"


def _manual_review_actionable_decision(decision: Any | None) -> bool:
    if decision is None:
        return False
    action = str(getattr(decision, "decision", "") or "").strip()
    metadata_json = dict(getattr(decision, "metadata_json", {}) or {})
    return bool(metadata_json.get("paper_trade_authorized", False)) and action not in {"", "hold", "no_trade"}


def _intraday_context_metadata(*, decision: Any | None, option_position: Any | None) -> dict[str, Any]:
    metadata_json: dict[str, Any] = {}
    decision_metadata = dict(getattr(decision, "metadata_json", {}) or {})
    option_strategy = decision_metadata.get("option_strategy")
    if isinstance(option_strategy, dict):
        metadata_json["option_strategy"] = dict(option_strategy)
    option_strategy_type = None
    if option_position is not None:
        metadata_json["paper_option_position_id"] = option_position.paper_option_position_id
        option_strategy_type = option_position.option_strategy_type
    elif isinstance(option_strategy, dict):
        option_strategy_type = option_strategy.get("option_strategy_type")
    if isinstance(option_strategy_type, str) and option_strategy_type:
        metadata_json["option_strategy_type"] = option_strategy_type
    return metadata_json
