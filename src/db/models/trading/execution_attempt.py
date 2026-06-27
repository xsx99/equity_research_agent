"""Execution attempt audit ORM model."""
from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.db.models.base import Base


_EXECUTION_ATTEMPT_REASON_CODES = (
    "submitted",
    "not_executable_action",
    "instrument_mismatch",
    "not_authorized",
    "risk_missing",
    "risk_rejected",
    "dry_run",
    "broker_unavailable",
    "order_rejected",
    "no_fill",
    "missing_credentials",
    "broker_error",
)


class ExecutionAttempt(Base):
    """Persisted execution outcome for every decision reaching an execution path."""

    __tablename__ = "execution_attempts"

    execution_attempt_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trading_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trading_decisions.trading_decision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    risk_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("risk_decisions.risk_decision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    paper_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paper_orders.paper_order_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    paper_option_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paper_option_orders.paper_option_order_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    instrument_type = Column(String(32), nullable=False)
    phase = Column(String(32), nullable=False)
    action = Column(String(64), nullable=False)
    outcome = Column(String(16), nullable=False, index=True)
    reason_code = Column(String(64), nullable=False, index=True)
    detail = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('submitted', 'skipped', 'failed')",
            name="ck_execution_attempts_outcome",
        ),
        CheckConstraint(
            "phase IN ('preopen', 'intraday', 'manual_review')",
            name="ck_execution_attempts_phase",
        ),
        CheckConstraint(
            f"reason_code IN {tuple(_EXECUTION_ATTEMPT_REASON_CODES)}",
            name="ck_execution_attempts_reason_code",
        ),
        Index("ix_execution_attempts_phase_created", "phase", "created_at"),
    )
