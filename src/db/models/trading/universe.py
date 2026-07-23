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
    ranking_runs = relationship("UniverseRankingRun", back_populates="universe_snapshot")

    __table_args__ = (
        CheckConstraint("included_count >= 0", name="ck_universe_snapshots_included_count"),
        CheckConstraint("excluded_count >= 0", name="ck_universe_snapshots_excluded_count"),
        Index("ix_universe_snapshots_date_provider", "snapshot_date", "provider"),
    )


class UniverseRankingRun(Base):
    """One persisted full-universe cross-sectional ranking decision."""

    __tablename__ = "universe_ranking_runs"

    universe_ranking_run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    universe_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("universe_snapshots.universe_snapshot_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    model_version = Column(String(64), nullable=False)
    config_json = Column(JSONB, nullable=False, default=dict)
    input_count = Column(Integer, nullable=False, default=0, server_default="0")
    eligible_count = Column(Integer, nullable=False, default=0, server_default="0")
    shortlist_count = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(32), nullable=False, index=True)
    source_metadata_json = Column(JSONB, nullable=False, default=dict)
    error_metadata_json = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    universe_snapshot = relationship("UniverseSnapshot", back_populates="ranking_runs")
    rankings = relationship("UniverseRanking", back_populates="ranking_run")

    __table_args__ = (
        CheckConstraint(
            f"status IN {UniverseRankingRunStatus.check_in_sql()}",
            name="ck_universe_ranking_runs_status",
        ),
        CheckConstraint("input_count >= 0", name="ck_universe_ranking_runs_input_count"),
        CheckConstraint("eligible_count >= 0", name="ck_universe_ranking_runs_eligible_count"),
        CheckConstraint("shortlist_count >= 0", name="ck_universe_ranking_runs_shortlist_count"),
        CheckConstraint("eligible_count <= input_count", name="ck_universe_ranking_runs_eligible_input"),
        CheckConstraint("shortlist_count <= eligible_count", name="ck_universe_ranking_runs_shortlist_eligible"),
        Index("ix_universe_ranking_runs_snapshot_decision", "universe_snapshot_id", "decision_time"),
    )


class UniverseRanking(Base):
    """One complete cohort row, including insufficient-data symbols."""

    __tablename__ = "universe_rankings"

    universe_ranking_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    universe_ranking_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("universe_ranking_runs.universe_ranking_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    overall_rank = Column(Integer, nullable=True)
    overall_percentile = Column(Numeric, nullable=True)
    relative_strength_score = Column(Numeric, nullable=True)
    data_confidence = Column(Numeric, nullable=True)
    peer_group_type = Column(String(32), nullable=True)
    peer_group_id = Column(String(128), nullable=True)
    peer_group_size = Column(Integer, nullable=True)
    is_automatic_shortlist = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    forced_inclusion_reasons_json = Column(JSONB, nullable=False, default=list)
    raw_metrics_json = Column(JSONB, nullable=False, default=dict)
    normalized_metrics_json = Column(JSONB, nullable=False, default=dict)
    positive_contributors_json = Column(JSONB, nullable=False, default=list)
    negative_contributors_json = Column(JSONB, nullable=False, default=list)
    missing_inputs_json = Column(JSONB, nullable=False, default=list)
    source_refs_json = Column(JSONB, nullable=False, default=list)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    ranking_run = relationship("UniverseRankingRun", back_populates="rankings")
    candidate_scores = relationship("CandidateScore", back_populates="universe_ranking")

    __table_args__ = (
        UniqueConstraint("universe_ranking_run_id", "ticker", name="uq_universe_rankings_run_ticker"),
        CheckConstraint(
            f"status IN {UniverseRankingStatus.check_in_sql()}",
            name="ck_universe_rankings_status",
        ),
        CheckConstraint(
            "relative_strength_score IS NULL OR "
            "(relative_strength_score >= 0 AND relative_strength_score <= 1)",
            name="ck_universe_rankings_score_range",
        ),
        CheckConstraint(
            "data_confidence IS NULL OR (data_confidence >= 0 AND data_confidence <= 1)",
            name="ck_universe_rankings_confidence_range",
        ),
        CheckConstraint(
            "overall_percentile IS NULL OR "
            "(overall_percentile >= 0 AND overall_percentile <= 1)",
            name="ck_universe_rankings_percentile_range",
        ),
        CheckConstraint("overall_rank IS NULL OR overall_rank >= 0", name="ck_universe_rankings_rank"),
        CheckConstraint("peer_group_size IS NULL OR peer_group_size >= 0", name="ck_universe_rankings_peer_size"),
        Index("ix_universe_rankings_run_rank", "universe_ranking_run_id", "overall_rank"),
        Index("ix_universe_rankings_ticker_decision_time", "ticker", "decision_time"),
        Index("ix_universe_rankings_automatic_shortlist", "is_automatic_shortlist"),
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
