from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


REASON_SUBMITTED = "submitted"
REASON_NOT_EXECUTABLE_ACTION = "not_executable_action"
REASON_INSTRUMENT_MISMATCH = "instrument_mismatch"
REASON_NOT_AUTHORIZED = "not_authorized"
REASON_RISK_MISSING = "risk_missing"
REASON_RISK_REJECTED = "risk_rejected"
REASON_DRY_RUN = "dry_run"
REASON_BROKER_UNAVAILABLE = "broker_unavailable"
REASON_ORDER_REJECTED = "order_rejected"
REASON_NO_FILL = "no_fill"
REASON_MISSING_CREDENTIALS = "missing_credentials"
REASON_BROKER_ERROR = "broker_error"
REASON_NO_ACTION_REQUIRED = "no_action_required"

ALL_REASON_CODES = frozenset(
    {
        REASON_SUBMITTED,
        REASON_NOT_EXECUTABLE_ACTION,
        REASON_INSTRUMENT_MISMATCH,
        REASON_NOT_AUTHORIZED,
        REASON_RISK_MISSING,
        REASON_RISK_REJECTED,
        REASON_DRY_RUN,
        REASON_BROKER_UNAVAILABLE,
        REASON_ORDER_REJECTED,
        REASON_NO_FILL,
        REASON_MISSING_CREDENTIALS,
        REASON_BROKER_ERROR,
        REASON_NO_ACTION_REQUIRED,
    }
)


@dataclass(frozen=True)
class ExecutionAttemptRecord:
    execution_attempt_id: str
    trading_decision_id: str | None
    risk_decision_id: str | None
    paper_order_id: str | None
    paper_option_order_id: str | None
    ticker: str
    strategy_id: str
    trade_identity: str
    instrument_type: str
    phase: str
    action: str
    outcome: str
    reason_code: str
    detail: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        trading_decision_id: str | None,
        risk_decision_id: str | None,
        paper_order_id: str | None,
        paper_option_order_id: str | None,
        ticker: str,
        strategy_id: str,
        trade_identity: str,
        instrument_type: str,
        phase: str,
        action: str,
        outcome: str,
        reason_code: str,
        detail: str | None = None,
        created_at: datetime | None = None,
        metadata_json: dict[str, Any] | None = None,
        execution_attempt_id: str | None = None,
    ) -> "ExecutionAttemptRecord":
        return cls(
            execution_attempt_id=execution_attempt_id or str(uuid4()),
            trading_decision_id=trading_decision_id,
            risk_decision_id=risk_decision_id,
            paper_order_id=paper_order_id,
            paper_option_order_id=paper_option_order_id,
            ticker=ticker,
            strategy_id=strategy_id,
            trade_identity=trade_identity,
            instrument_type=instrument_type,
            phase=phase,
            action=action,
            outcome=outcome,
            reason_code=reason_code,
            detail=detail,
            created_at=created_at or datetime.now(timezone.utc),
            metadata_json=dict(metadata_json or {}),
        )


def skipped(
    *,
    trading_decision: Any,
    phase: str,
    reason_code: str,
    detail: str | None = None,
    risk_decision_id: str | None = None,
    paper_order_id: str | None = None,
    paper_option_order_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> ExecutionAttemptRecord:
    return ExecutionAttemptRecord.create(
        trading_decision_id=getattr(trading_decision, "trading_decision_id", None),
        risk_decision_id=risk_decision_id or getattr(trading_decision, "risk_decision_id", None),
        paper_order_id=paper_order_id,
        paper_option_order_id=paper_option_order_id,
        ticker=str(getattr(trading_decision, "ticker", "")),
        strategy_id=str(getattr(trading_decision, "strategy_id", "")),
        trade_identity=str(getattr(trading_decision, "trade_identity", "")),
        instrument_type=str(getattr(trading_decision, "instrument_type", "")),
        phase=phase,
        action=str(getattr(trading_decision, "decision", "")),
        outcome="skipped",
        reason_code=reason_code,
        detail=detail,
        metadata_json=metadata_json,
    )


def submitted(
    *,
    trading_decision: Any,
    phase: str,
    paper_order_id: str | None = None,
    paper_option_order_id: str | None = None,
    risk_decision_id: str | None = None,
    detail: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> ExecutionAttemptRecord:
    return ExecutionAttemptRecord.create(
        trading_decision_id=getattr(trading_decision, "trading_decision_id", None),
        risk_decision_id=risk_decision_id or getattr(trading_decision, "risk_decision_id", None),
        paper_order_id=paper_order_id,
        paper_option_order_id=paper_option_order_id,
        ticker=str(getattr(trading_decision, "ticker", "")),
        strategy_id=str(getattr(trading_decision, "strategy_id", "")),
        trade_identity=str(getattr(trading_decision, "trade_identity", "")),
        instrument_type=str(getattr(trading_decision, "instrument_type", "")),
        phase=phase,
        action=str(getattr(trading_decision, "decision", "")),
        outcome="submitted",
        reason_code=REASON_SUBMITTED,
        detail=detail,
        metadata_json=metadata_json,
    )


def failed(
    *,
    trading_decision: Any,
    phase: str,
    reason_code: str,
    paper_order_id: str | None = None,
    paper_option_order_id: str | None = None,
    risk_decision_id: str | None = None,
    detail: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> ExecutionAttemptRecord:
    return ExecutionAttemptRecord.create(
        trading_decision_id=getattr(trading_decision, "trading_decision_id", None),
        risk_decision_id=risk_decision_id or getattr(trading_decision, "risk_decision_id", None),
        paper_order_id=paper_order_id,
        paper_option_order_id=paper_option_order_id,
        ticker=str(getattr(trading_decision, "ticker", "")),
        strategy_id=str(getattr(trading_decision, "strategy_id", "")),
        trade_identity=str(getattr(trading_decision, "trade_identity", "")),
        instrument_type=str(getattr(trading_decision, "instrument_type", "")),
        phase=phase,
        action=str(getattr(trading_decision, "decision", "")),
        outcome="failed",
        reason_code=reason_code,
        detail=detail,
        metadata_json=metadata_json,
    )
