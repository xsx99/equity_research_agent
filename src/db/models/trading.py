"""Trading foundation ORM models."""
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
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .base import Base, ChoiceEnum


class StrategyLifecycleStatus(ChoiceEnum):
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    EXPERIMENTAL = "experimental"
    ACTIVE = "active"
    RETIRED = "retired"


class StrategySource(ChoiceEnum):
    SEED = "seed"
    REFLECTION_LEARNING = "reflection_learning"
    MANUAL = "manual"


class LlmPromptLifecycleStatus(ChoiceEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class LlmParseStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LlmUsageStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PortfolioIntentLifecycleStatus(ChoiceEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


class PortfolioIntentType(ChoiceEnum):
    CORE_GROWTH = "core_growth"
    CORE_INDEX = "core_index"
    CORE_THEME = "core_theme"
    CORE_CASH_LIKE = "core_cash_like"


class TickerRelationshipType(ChoiceEnum):
    PEER = "peer"
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    COMPETITOR = "competitor"
    SECTOR_LEADER = "sector_leader"
    ETF_COMPONENT = "etf_component"
    THEME_LEADER = "theme_leader"
    THEME_CONSTITUENT = "theme_constituent"


class ThemeLifecycleStatus(ChoiceEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class UniverseSymbolStatus(ChoiceEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"


class ManualTickerRequestMode(ChoiceEnum):
    REVIEW_ONLY = "review_only"
    PAPER_TRADE_ELIGIBLE = "paper_trade_eligible"


class ManualTickerRequestStatus(ChoiceEnum):
    ACTIVE = "active"
    DISMISSED = "dismissed"
    CANCELLED = "cancelled"


class ProviderRequestStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CACHE_HIT = "cache_hit"
    BUDGET_EXCEEDED = "budget_exceeded"
    CIRCUIT_OPEN = "circuit_open"


class SourceIngestionStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEGRADED = "degraded"


class StrategyDefinition(Base):
    """Versioned strategy metadata and JSON scoring/config policy."""

    __tablename__ = "strategy_definitions"

    strategy_definition_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id = Column(String(64), nullable=False)
    version = Column(String(16), nullable=False)
    display_name = Column(String(128), nullable=False)
    strategy_layer = Column(String(32), nullable=False, index=True)
    typical_horizon = Column(String(32), nullable=False)
    allowed_common_stock_direction = Column(
        String(16),
        nullable=False,
        default="long_only",
        server_default="long_only",
    )
    config_json = Column(JSONB, nullable=False, default=dict)
    lifecycle_status = Column(
        String(16),
        nullable=False,
        default=StrategyLifecycleStatus.ACTIVE.value,
        server_default=StrategyLifecycleStatus.ACTIVE.value,
        index=True,
    )
    source = Column(
        String(32),
        nullable=False,
        default=StrategySource.SEED.value,
        server_default=StrategySource.SEED.value,
        index=True,
    )
    parent_strategy_id = Column(String(64), nullable=True)
    evidence_json = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strategy_definitions_strategy_id_version"),
        CheckConstraint(
            "strategy_layer IN ('tactical_pattern', 'expression_bucket')",
            name="ck_strategy_definitions_strategy_layer",
        ),
        CheckConstraint(
            "allowed_common_stock_direction IN ('long_only')",
            name="ck_strategy_definitions_allowed_common_stock_direction",
        ),
        CheckConstraint(
            f"lifecycle_status IN {StrategyLifecycleStatus.check_in_sql()}",
            name="ck_strategy_definitions_lifecycle_status",
        ),
        CheckConstraint(
            f"source IN {StrategySource.check_in_sql()}",
            name="ck_strategy_definitions_source",
        ),
        Index("ix_strategy_definitions_strategy_id_version", "strategy_id", "version"),
    )


class LlmPromptTemplate(Base):
    """Persisted metadata for one versioned prompt template."""

    __tablename__ = "llm_prompt_templates"

    prompt_template_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_id = Column(String(128), nullable=False)
    prompt_version = Column(String(32), nullable=False)
    pipeline_name = Column(String(64), nullable=False, index=True)
    template_path = Column(String(255), nullable=False)
    template_hash = Column(String(128), nullable=False)
    git_commit = Column(String(64), nullable=True)
    output_schema_id = Column(String(128), nullable=False)
    output_schema_version = Column(String(32), nullable=False)
    lifecycle_status = Column(
        String(16),
        nullable=False,
        default=LlmPromptLifecycleStatus.ACTIVE.value,
        server_default=LlmPromptLifecycleStatus.ACTIVE.value,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    prompt_runs = relationship("LlmPromptRun", back_populates="prompt_template")

    __table_args__ = (
        UniqueConstraint("prompt_id", "prompt_version", name="uq_llm_prompt_templates_prompt_id_version"),
        CheckConstraint(
            f"lifecycle_status IN {LlmPromptLifecycleStatus.check_in_sql()}",
            name="ck_llm_prompt_templates_lifecycle_status",
        ),
        Index("ix_llm_prompt_templates_prompt_id_version", "prompt_id", "prompt_version"),
    )


class LlmPromptRun(Base):
    """One rendered prompt, raw output, parsed output, and validation result."""

    __tablename__ = "llm_prompt_runs"

    prompt_run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_prompt_templates.prompt_template_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    pipeline_name = Column(String(64), nullable=False, index=True)
    pipeline_run_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    rendered_prompt_hash = Column(String(128), nullable=False)
    rendered_prompt_redacted = Column(Text, nullable=True)
    input_context_json = Column(JSONB, nullable=False, default=dict)
    raw_output_text = Column(Text, nullable=False)
    parsed_output_json = Column(JSONB, nullable=False, default=dict)
    parse_status = Column(String(16), nullable=False, index=True)
    validation_errors_json = Column(JSONB, nullable=False, default=list)
    fallback_action = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    prompt_template = relationship("LlmPromptTemplate", back_populates="prompt_runs")
    usage_events = relationship("LlmUsageEvent", back_populates="prompt_run")

    __table_args__ = (
        CheckConstraint(
            f"parse_status IN {LlmParseStatus.check_in_sql()}",
            name="ck_llm_prompt_runs_parse_status",
        ),
        Index("ix_llm_prompt_runs_pipeline_name_status", "pipeline_name", "parse_status"),
    )


class LlmUsageEvent(Base):
    """LLM provider/model usage telemetry for a prompt run."""

    __tablename__ = "llm_usage_events"

    llm_usage_event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_prompt_runs.prompt_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = Column(String(64), nullable=False)
    model = Column(String(128), nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    estimated_cost = Column(Numeric, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(16), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    prompt_run = relationship("LlmPromptRun", back_populates="usage_events")

    __table_args__ = (
        CheckConstraint(
            f"status IN {LlmUsageStatus.check_in_sql()}",
            name="ck_llm_usage_events_status",
        ),
        CheckConstraint("prompt_tokens >= 0", name="ck_llm_usage_events_prompt_tokens"),
        CheckConstraint("completion_tokens >= 0", name="ck_llm_usage_events_completion_tokens"),
        CheckConstraint("total_tokens >= 0", name="ck_llm_usage_events_total_tokens"),
        CheckConstraint("latency_ms >= 0", name="ck_llm_usage_events_latency_ms"),
        CheckConstraint("retry_count >= 0", name="ck_llm_usage_events_retry_count"),
        Index("ix_llm_usage_events_provider_model", "provider", "model"),
    )


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
    )


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
