"""Intraday scan and alert ORM models."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.db.models.base import Base
from src.db.models.trading.enums import *

class IntradaySignalScan(Base):
    """Persisted metadata for one hourly intraday refresh run."""

    __tablename__ = "intraday_signal_scans"

    intraday_signal_scan_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(16), nullable=False, index=True)
    scope_json = Column(JSONB, nullable=False, default=dict)
    coverage_json = Column(JSONB, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class IntradaySignalSnapshot(Base):
    """Per-ticker intraday snapshot with deltas versus baseline and prior refresh."""

    __tablename__ = "intraday_signal_snapshots"

    intraday_signal_snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intraday_signal_scan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("intraday_signal_scans.intraday_signal_scan_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    baseline_signal_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("signal_snapshots.signal_snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    previous_intraday_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("intraday_signal_snapshots.intraday_signal_snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    refreshed_signals_json = Column(JSONB, nullable=False, default=dict)
    carried_forward_signals_json = Column(JSONB, nullable=False, default=dict)
    delta_vs_baseline_json = Column(JSONB, nullable=False, default=dict)
    delta_vs_previous_json = Column(JSONB, nullable=False, default=dict)
    source_freshness_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    intraday_signal_scan = relationship("IntradaySignalScan")

class NewsAlert(Base):
    """Normalized intraday alert derived from event/news items."""

    __tablename__ = "news_alerts"

    news_alert_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    source_ticker = Column(String(16), nullable=True, index=True)
    alert_type = Column(String(64), nullable=False, index=True)
    sentiment = Column(String(16), nullable=True, index=True)
    severity = Column(String(16), nullable=False, index=True)
    source = Column(String(64), nullable=False, index=True)
    published_at = Column(DateTime(timezone=True), nullable=False, index=True)
    headline = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    strategy_relevance_json = Column(JSONB, nullable=False, default=list)
    affected_positions_json = Column(JSONB, nullable=False, default=list)
    affected_candidates_json = Column(JSONB, nullable=False, default=list)
    affected_themes_json = Column(JSONB, nullable=False, default=list)
    readthrough_source_ticker = Column(String(16), nullable=True)
    action_required = Column(Boolean, nullable=False, default=False, server_default="false")
    dedupe_key = Column(String(255), nullable=False, unique=True, index=True)
    event_news_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("event_news_items.event_news_item_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class IntradayRebalanceDecision(Base):
    """Persisted intraday rebalance action and final status."""

    __tablename__ = "intraday_rebalance_decisions"

    intraday_rebalance_decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    status = Column(String(16), nullable=False, index=True)
    reason_code = Column(String(64), nullable=False, index=True)
    confidence = Column(Numeric, nullable=False)
    target_weight = Column(Numeric, nullable=False)
    approved_quantity = Column(Numeric, nullable=False)
    thesis = Column(Text, nullable=False)
    urgency = Column(String(16), nullable=False, index=True)
    rationale_json = Column(JSONB, nullable=False, default=list)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False, index=True)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    risk_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("risk_decisions.risk_decision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
