"""Macro snapshot and calendar ORM models."""
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

class MacroSnapshot(Base):
    """Canonical macro snapshot per trade date and source set."""

    __tablename__ = "macro_snapshots"

    macro_snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_date = Column(Date, nullable=False, index=True)
    snapshot_time = Column(DateTime(timezone=True), nullable=False, index=True)
    regime = Column(String(32), nullable=False, index=True)
    risk_budget_multiplier = Column(Numeric, nullable=False)
    volatility_state = Column(String(32), nullable=True)
    rates_state = Column(String(32), nullable=True)
    liquidity_state = Column(String(32), nullable=True)
    source_set_key = Column(String(255), nullable=False)
    blocked_strategy_tags_json = Column(JSONB, nullable=False, default=list)
    invalidators_json = Column(JSONB, nullable=False, default=list)
    source_freshness_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "snapshot_time",
            "source_set_key",
            name="uq_macro_snapshots_trade_date_snapshot_time_source_set_key",
        ),
        Index("ix_macro_snapshots_trade_date_snapshot_time", "trade_date", "snapshot_time"),
    )

class CalendarEvent(Base):
    """Normalized calendar event with point-in-time availability."""

    __tablename__ = "calendar_events"

    calendar_event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_key = Column(String(255), nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    ticker = Column(String(16), nullable=True, index=True)
    event_time = Column(DateTime(timezone=True), nullable=False, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False, index=True)
    title = Column(Text, nullable=False)
    severity_hint = Column(String(32), nullable=False, index=True)
    source = Column(String(64), nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    portfolio_event_risk_assessments = relationship(
        "PortfolioEventRiskAssessment",
        back_populates="calendar_event",
    )

    __table_args__ = (
        UniqueConstraint("event_key", name="uq_calendar_events_event_key"),
        Index("ix_calendar_events_ticker_event_time", "ticker", "event_time"),
    )

class PortfolioEventRiskAssessment(Base):
    """Persisted portfolio-specific event-risk assessment."""

    __tablename__ = "portfolio_event_risk_assessments"

    portfolio_event_risk_assessment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_key = Column(String(255), nullable=False)
    calendar_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("calendar_events.calendar_event_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    portfolio_risk_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_risk_snapshots.portfolio_risk_snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decision_time = Column(DateTime(timezone=True), nullable=True, index=True)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    risk_source = Column(String(64), nullable=False, index=True)
    severity = Column(String(32), nullable=False, index=True)
    event_type = Column(String(64), nullable=True)
    days_until_event = Column(Integer, nullable=True)
    affects_existing_position = Column(Boolean, nullable=False, default=False, server_default="false")
    affects_pending_trade = Column(Boolean, nullable=False, default=False, server_default="false")
    recommended_action = Column(String(64), nullable=False, default="monitor", server_default="monitor")
    rationale = Column(Text, nullable=False, default="", server_default="")
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    calendar_event = relationship("CalendarEvent", back_populates="portfolio_event_risk_assessments")
    portfolio_risk_snapshot = relationship(
        "PortfolioRiskSnapshot",
        back_populates="portfolio_event_risk_assessments",
    )

    __table_args__ = (
        UniqueConstraint("assessment_key", name="uq_portfolio_event_risk_assessments_assessment_key"),
        Index(
            "ix_portfolio_event_risk_assessments_ticker_available",
            "ticker",
            "available_for_decision_at",
        ),
        Index(
            "ix_portfolio_event_risk_assessments_source_severity",
            "risk_source",
            "severity",
        ),
    )
