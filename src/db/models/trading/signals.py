"""Signal ingestion and snapshot ORM models."""
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

class SourceIngestionRun(Base):
    """Scheduled or targeted source refresh metadata."""

    __tablename__ = "source_ingestion_runs"

    source_ingestion_run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_family = Column(String(64), nullable=False, index=True)
    run_type = Column(String(64), nullable=False)
    scope_json = Column(JSONB, nullable=False, default=dict)
    provider = Column(String(64), nullable=True)
    as_of = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, index=True)
    coverage_json = Column(JSONB, nullable=False, default=dict)
    error_code = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            f"status IN {SourceIngestionStatus.check_in_sql()}",
            name="ck_source_ingestion_runs_status",
        ),
        Index("ix_source_ingestion_runs_family_status", "source_family", "status"),
    )

class ProviderRequestRun(Base):
    """Per-provider request telemetry from resilience guardrails."""

    __tablename__ = "provider_request_runs"

    provider_request_run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_ingestion_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("source_ingestion_runs.source_ingestion_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider = Column(String(64), nullable=False, index=True)
    endpoint = Column(String(128), nullable=False, index=True)
    source_family = Column(String(64), nullable=False, index=True)
    scope_json = Column(JSONB, nullable=False, default=dict)
    cache_status = Column(String(32), nullable=False)
    request_count = Column(Integer, nullable=False)
    budget_remaining = Column(Integer, nullable=False)
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    backoff_ms = Column(Integer, nullable=False, default=0, server_default="0")
    latency_ms = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(32), nullable=False, index=True)
    error_code = Column(String(128), nullable=True)
    circuit_state = Column(String(32), nullable=False)
    degraded_mode = Column(Boolean, nullable=False, default=False, server_default="false")
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)

    source_ingestion_run = relationship("SourceIngestionRun")

    __table_args__ = (
        CheckConstraint(
            f"status IN {ProviderRequestStatus.check_in_sql()}",
            name="ck_provider_request_runs_status",
        ),
        CheckConstraint("request_count >= 0", name="ck_provider_request_runs_request_count"),
        CheckConstraint("budget_remaining >= 0", name="ck_provider_request_runs_budget_remaining"),
        CheckConstraint("retry_count >= 0", name="ck_provider_request_runs_retry_count"),
        CheckConstraint("backoff_ms >= 0", name="ck_provider_request_runs_backoff_ms"),
        CheckConstraint("latency_ms >= 0", name="ck_provider_request_runs_latency_ms"),
        Index("ix_provider_request_runs_provider_endpoint_status", "provider", "endpoint", "status"),
    )

class FundamentalSnapshot(Base):
    """Point-in-time provider or normalized fundamental source row."""

    __tablename__ = "fundamental_snapshots"

    fundamental_snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    fiscal_period = Column(String(32), nullable=True)
    as_of_date = Column(Date, nullable=True, index=True)
    provider = Column(String(64), nullable=False)
    source_refs_json = Column(JSONB, nullable=False, default=list)
    event_time = Column(DateTime(timezone=True), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=False)
    ingested_at = Column(DateTime(timezone=True), nullable=False)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False, index=True)
    raw_payload_ref = Column(String(255), nullable=True)
    normalized_metrics_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_fundamental_snapshots_ticker_available", "ticker", "available_for_decision_at"),
    )

class EventNewsItem(Base):
    """Point-in-time headline, calendar, or provider-event row."""

    __tablename__ = "event_news_items"

    event_news_item_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    source_ticker = Column(String(16), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    direction = Column(String(32), nullable=True)
    sentiment = Column(String(32), nullable=True)
    importance = Column(String(32), nullable=True, index=True)
    headline = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    provider = Column(String(64), nullable=False)
    source_refs_json = Column(JSONB, nullable=False, default=list)
    dedupe_key = Column(String(255), nullable=False)
    event_time = Column(DateTime(timezone=True), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=False)
    ingested_at = Column(DateTime(timezone=True), nullable=False)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False, index=True)
    raw_payload_ref = Column(String(255), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_event_news_items_dedupe_key"),
        Index("ix_event_news_items_ticker_available", "ticker", "available_for_decision_at"),
    )

class SocialMacroItem(Base):
    """Point-in-time deterministic social/policy context row normalized for trading."""

    __tablename__ = "social_macro_items"

    social_macro_item_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    category = Column(String(64), nullable=False, index=True)
    source_type = Column(String(64), nullable=False)
    source_key = Column(String(64), nullable=False, index=True)
    provider = Column(String(64), nullable=False)
    title = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    direction = Column(String(32), nullable=True)
    sentiment_direction = Column(String(32), nullable=True)
    importance_score = Column(Numeric, nullable=True)
    importance_label = Column(String(32), nullable=True, index=True)
    policy_headwind_flag = Column(Boolean, nullable=False, default=False, server_default="false")
    policy_tailwind_flag = Column(Boolean, nullable=False, default=False, server_default="false")
    explicit_ticker_mention_flag = Column(Boolean, nullable=False, default=False, server_default="false")
    explicit_theme_mention_flag = Column(Boolean, nullable=False, default=False, server_default="false")
    theme_tags_json = Column(JSONB, nullable=False, default=list)
    company_name_mentions_json = Column(JSONB, nullable=False, default=list)
    source_refs_json = Column(JSONB, nullable=False, default=list)
    dedupe_key = Column(String(255), nullable=False)
    event_time = Column(DateTime(timezone=True), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=False)
    ingested_at = Column(DateTime(timezone=True), nullable=False)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False, index=True)
    raw_payload_ref = Column(String(255), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_social_macro_items_dedupe_key"),
        Index("ix_social_macro_items_ticker_available", "ticker", "available_for_decision_at"),
    )

class SignalSnapshot(Base):
    """Per-ticker pre-open quant features and point-in-time audit metadata."""

    __tablename__ = "signal_snapshots"

    signal_snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    snapshot_type = Column(String(32), nullable=False, index=True)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False)
    max_input_available_for_decision_at = Column(DateTime(timezone=True), nullable=True)
    signal_json = Column(JSONB, nullable=False, default=dict)
    source_freshness_json = Column(JSONB, nullable=False, default=dict)
    missing_signals_json = Column(JSONB, nullable=False, default=list)
    stale_signals_json = Column(JSONB, nullable=False, default=list)
    source_record_refs_json = Column(JSONB, nullable=False, default=list)
    source_available_times_json = Column(JSONB, nullable=False, default=dict)
    excluded_future_source_count = Column(Integer, nullable=False, default=0, server_default="0")
    point_in_time_passed = Column(Boolean, nullable=False, default=True, server_default="true")
    selection_source = Column(String(32), nullable=False, default="scanner", server_default="scanner")
    manual_request_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    universe_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("universe_snapshots.universe_snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    universe_snapshot = relationship("UniverseSnapshot")

    __table_args__ = (
        CheckConstraint(
            "snapshot_type IN ('pre_open', 'intraday')",
            name="ck_signal_snapshots_snapshot_type",
        ),
        CheckConstraint(
            "excluded_future_source_count >= 0",
            name="ck_signal_snapshots_excluded_future_source_count",
        ),
        Index("ix_signal_snapshots_ticker_decision_type", "ticker", "decision_time", "snapshot_type"),
    )
