"""Universe, intent, and runtime ORM models."""
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

class PortfolioIntent(Base):
    """User-approved core holding and portfolio-intent configuration."""

    __tablename__ = "portfolio_intents"

    portfolio_intent_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    intent_type = Column(String(64), nullable=False)
    target_weight = Column(Numeric, nullable=False)
    max_weight = Column(Numeric, nullable=False)
    add_rules_json = Column(JSONB, nullable=False, default=list)
    trim_rules_json = Column(JSONB, nullable=False, default=list)
    thesis_invalidators_json = Column(JSONB, nullable=False, default=list)
    allowed_tactical_interactions_json = Column(JSONB, nullable=False, default=list)
    lifecycle_status = Column(
        String(32),
        nullable=False,
        default=PortfolioIntentLifecycleStatus.ACTIVE.value,
        server_default=PortfolioIntentLifecycleStatus.ACTIVE.value,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            f"intent_type IN {PortfolioIntentType.check_in_sql()}",
            name="ck_portfolio_intents_intent_type",
        ),
        CheckConstraint(
            f"lifecycle_status IN {PortfolioIntentLifecycleStatus.check_in_sql()}",
            name="ck_portfolio_intents_lifecycle_status",
        ),
        CheckConstraint("target_weight >= 0", name="ck_portfolio_intents_target_weight"),
        CheckConstraint("max_weight >= target_weight", name="ck_portfolio_intents_max_weight"),
    )

class TickerRelationship(Base):
    """Directed structured ticker relationship for read-through and peer baskets."""

    __tablename__ = "ticker_relationships"

    ticker_relationship_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_ticker = Column(String(16), nullable=False, index=True)
    target_ticker = Column(String(16), nullable=False, index=True)
    relationship_type = Column(String(64), nullable=False)
    theme_id = Column(String(64), nullable=True, index=True)
    confidence = Column(Numeric, nullable=False)
    strength_score = Column(Numeric, nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=True)
    source_refs_json = Column(JSONB, nullable=False, default=list)
    allowed_uses_json = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            f"relationship_type IN {TickerRelationshipType.check_in_sql()}",
            name="ck_ticker_relationships_relationship_type",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_ticker_relationships_confidence"),
        CheckConstraint(
            "strength_score >= 0 AND strength_score <= 1",
            name="ck_ticker_relationships_strength_score",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="ck_ticker_relationships_valid_window",
        ),
    )

class PeerBasket(Base):
    """Versioned decision-time peer basket used for attribution and replay."""

    __tablename__ = "peer_baskets"

    peer_basket_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    basket_key = Column(String(128), nullable=False)
    version = Column(String(32), nullable=False)
    trade_date = Column(Date, nullable=False, index=True)
    members_json = Column(JSONB, nullable=False, default=list)
    construction_method = Column(String(64), nullable=False)
    source_refs_json = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("basket_key", "version", "trade_date", name="uq_peer_baskets_key_version_trade_date"),
        Index("ix_peer_baskets_basket_key_version", "basket_key", "version"),
    )

class ThemeTaxonomy(Base):
    """User-maintained theme hierarchy for grouping and read-through."""

    __tablename__ = "theme_taxonomy"

    theme_id = Column(String(64), primary_key=True)
    display_name = Column(String(128), nullable=False)
    parent_theme_id = Column(String(64), nullable=True, index=True)
    description = Column(Text, nullable=True)
    lifecycle_status = Column(
        String(32),
        nullable=False,
        default=ThemeLifecycleStatus.ACTIVE.value,
        server_default=ThemeLifecycleStatus.ACTIVE.value,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            f"lifecycle_status IN {ThemeLifecycleStatus.check_in_sql()}",
            name="ck_theme_taxonomy_lifecycle_status",
        ),
    )

class UniverseFilterConfig(Base):
    """Versioned user-editable universe filter profile."""

    __tablename__ = "universe_filter_configs"

    universe_filter_config_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_name = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    min_price = Column(Numeric, nullable=False)
    min_avg_dollar_volume = Column(Numeric, nullable=False)
    included_sectors_json = Column(JSONB, nullable=False, default=list)
    excluded_sectors_json = Column(JSONB, nullable=False, default=list)
    included_industries_json = Column(JSONB, nullable=False, default=list)
    excluded_industries_json = Column(JSONB, nullable=False, default=list)
    exchanges_json = Column(JSONB, nullable=False, default=list)
    asset_types_json = Column(JSONB, nullable=False, default=list)
    manual_include_json = Column(JSONB, nullable=False, default=list)
    manual_exclude_json = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    universe_snapshots = relationship("UniverseSnapshot", back_populates="filter_config")

    __table_args__ = (
        UniqueConstraint("profile_name", "version", name="uq_universe_filter_configs_profile_version"),
        CheckConstraint("min_price >= 0", name="ck_universe_filter_configs_min_price"),
        CheckConstraint(
            "min_avg_dollar_volume >= 0",
            name="ck_universe_filter_configs_min_avg_dollar_volume",
        ),
    )

class UniverseSnapshot(Base):
    """One daily universe refresh run."""

    __tablename__ = "universe_snapshots"

    universe_snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    universe_filter_config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("universe_filter_configs.universe_filter_config_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    snapshot_date = Column(Date, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    provider = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)
    included_count = Column(Integer, nullable=False, default=0, server_default="0")
    excluded_count = Column(Integer, nullable=False, default=0, server_default="0")
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    filter_config = relationship("UniverseFilterConfig", back_populates="universe_snapshots")
    symbols = relationship("UniverseSymbol", back_populates="universe_snapshot")

    __table_args__ = (
        CheckConstraint("included_count >= 0", name="ck_universe_snapshots_included_count"),
        CheckConstraint("excluded_count >= 0", name="ck_universe_snapshots_excluded_count"),
        Index("ix_universe_snapshots_date_provider", "snapshot_date", "provider"),
    )

class UniverseSymbol(Base):
    """Included or excluded symbol in a universe snapshot with reason."""

    __tablename__ = "universe_symbols"

    universe_symbol_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    universe_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("universe_snapshots.universe_snapshot_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol = Column(String(16), nullable=False, index=True)
    company_name = Column(String(255), nullable=True)
    asset_type = Column(String(64), nullable=False)
    exchange = Column(String(64), nullable=True)
    sector = Column(String(128), nullable=True)
    industry = Column(String(128), nullable=True)
    price = Column(Numeric, nullable=True)
    avg_dollar_volume = Column(Numeric, nullable=True)
    status = Column(String(16), nullable=False, index=True)
    exclusion_reason = Column(String(64), nullable=True, index=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    universe_snapshot = relationship("UniverseSnapshot", back_populates="symbols")

    __table_args__ = (
        UniqueConstraint("universe_snapshot_id", "symbol", name="uq_universe_symbols_snapshot_symbol"),
        CheckConstraint(
            f"status IN {UniverseSymbolStatus.check_in_sql()}",
            name="ck_universe_symbols_status",
        ),
    )

class ManualTickerRequest(Base):
    """User-pinned ticker that remains active until dismissed or cancelled."""

    __tablename__ = "manual_ticker_requests"

    manual_ticker_request_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    mode = Column(String(32), nullable=False)
    status = Column(
        String(32),
        nullable=False,
        default=ManualTickerRequestStatus.ACTIVE.value,
        server_default=ManualTickerRequestStatus.ACTIVE.value,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    last_evaluated_at = Column(DateTime(timezone=True), nullable=True)
    latest_result_status = Column(String(64), nullable=True)
    latest_signal_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("signal_snapshots.signal_snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metadata_json = Column(JSONB, nullable=False, default=dict)

    latest_signal_snapshot = relationship("SignalSnapshot", foreign_keys=[latest_signal_snapshot_id])

    __table_args__ = (
        CheckConstraint(
            f"mode IN {ManualTickerRequestMode.check_in_sql()}",
            name="ck_manual_ticker_requests_mode",
        ),
        CheckConstraint(
            f"status IN {ManualTickerRequestStatus.check_in_sql()}",
            name="ck_manual_ticker_requests_status",
        ),
        Index("ix_manual_ticker_requests_ticker_status", "ticker", "status"),
        Index(
            "uq_manual_ticker_requests_active_ticker",
            "ticker",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

class TradingRuntimeRun(Base):
    """Persisted normalized runtime report for one scheduler-facing invocation."""

    __tablename__ = "trading_runtime_runs"

    trading_runtime_run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phase = Column(String(32), nullable=False, index=True)
    status = Column(String(16), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    as_of = Column(DateTime(timezone=True), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    summary_json = Column(JSONB, nullable=False, default=dict)
    execution_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('passed', 'failed', 'skipped')",
            name="ck_trading_runtime_runs_status",
        ),
        Index(
            "ix_trading_runtime_runs_phase_completed_at",
            "phase",
            "completed_at",
        ),
        Index(
            "ix_trading_runtime_runs_phase_trade_date_completed_at",
            "phase",
            "trade_date",
            "completed_at",
        ),
    )
