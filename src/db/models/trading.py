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
    text,
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


class StrategyRunStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MacroCompatibility(ChoiceEnum):
    ALLOWED = "allowed"
    REDUCED_SIZE = "reduced_size"
    BLOCKED = "blocked"


class CandidateStatus(ChoiceEnum):
    ACTIONABLE = "actionable"
    WATCH = "watch"
    BLOCKED = "blocked"


class TradeIdentity(ChoiceEnum):
    CORE_HOLDING = "core_holding"
    TACTICAL_STOCK_TRADE = "tactical_stock_trade"
    TACTICAL_OPTION_TRADE = "tactical_option_trade"
    RISK_HEDGE_OVERLAY = "risk_hedge_overlay"
    WATCH_ONLY = "watch_only"


class WatchType(ChoiceEnum):
    CATALYST_WATCH = "catalyst_watch"
    ORDINARY_WATCH = "ordinary_watch"


class CandidateOutcomeEvaluationStatus(ChoiceEnum):
    INTERIM = "interim"
    FINAL = "final"


class DailyReflectionStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FALLBACK = "fallback"


class LearningFactorStatus(ChoiceEnum):
    CANDIDATE = "candidate"
    OBSERVATION = "observation"
    SHADOW = "shadow"
    ACTIVE = "active"
    SUPPRESSED = "suppressed"
    RETIRED = "retired"


class StrategyProposalStatus(ChoiceEnum):
    ACCEPTED = "accepted"
    DUPLICATE_REJECTED = "duplicate_rejected"
    PROPOSAL_FAILED = "proposal_failed"


class StrategyEvaluationStatus(ChoiceEnum):
    OBSERVED = "observed"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    RETIRED = "retired"


class RiskAppetite(ChoiceEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class RiskDecisionStatus(ChoiceEnum):
    APPROVED = "approved"
    REDUCED = "reduced"
    REJECTED = "rejected"


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


class StrategyProposal(Base):
    """Persisted strategy proposal generated by PR10."""

    __tablename__ = "strategy_proposals"

    strategy_proposal_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_date = Column(Date, nullable=False, index=True)
    prompt_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_prompt_runs.prompt_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    daily_reflection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("daily_reflections.daily_reflection_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    proposal_status = Column(String(32), nullable=False, index=True)
    proposed_strategy_id = Column(String(64), nullable=False, index=True)
    display_name = Column(String(128), nullable=False)
    proposed_lifecycle_status = Column(String(16), nullable=True, index=True)
    duplicate_of_strategy_id = Column(String(64), nullable=True, index=True)
    rejection_reason = Column(String(128), nullable=True)
    source = Column(
        String(32),
        nullable=False,
        default=StrategySource.REFLECTION_LEARNING.value,
        server_default=StrategySource.REFLECTION_LEARNING.value,
        index=True,
    )
    evidence_summary = Column(Text, nullable=False)
    proposal_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    prompt_run = relationship("LlmPromptRun")
    daily_reflection = relationship("DailyReflection")
    evaluation_results = relationship("StrategyEvaluationResult", back_populates="strategy_proposal")

    __table_args__ = (
        CheckConstraint(
            f"proposal_status IN {StrategyProposalStatus.check_in_sql()}",
            name="ck_strategy_proposals_status",
        ),
        CheckConstraint(
            "proposed_lifecycle_status IS NULL OR "
            f"proposed_lifecycle_status IN {StrategyLifecycleStatus.check_in_sql()}",
            name="ck_strategy_proposals_lifecycle_status",
        ),
        CheckConstraint(
            f"source IN {StrategySource.check_in_sql()}",
            name="ck_strategy_proposals_source",
        ),
    )


class StrategyEvaluationResult(Base):
    """Persisted lifecycle evidence and promotion/retirement audit rows."""

    __tablename__ = "strategy_evaluation_results"

    strategy_evaluation_result_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_definition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategy_definitions.strategy_definition_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    strategy_proposal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategy_proposals.strategy_proposal_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    strategy_id = Column(String(64), nullable=False, index=True)
    evaluation_type = Column(String(64), nullable=False, index=True)
    evaluation_status = Column(String(16), nullable=False, index=True)
    prior_lifecycle_status = Column(String(16), nullable=True)
    new_lifecycle_status = Column(String(16), nullable=True, index=True)
    reason_code = Column(String(128), nullable=False)
    evidence_summary = Column(Text, nullable=False)
    metrics_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    strategy_definition = relationship("StrategyDefinition")
    strategy_proposal = relationship("StrategyProposal", back_populates="evaluation_results")

    __table_args__ = (
        CheckConstraint(
            f"evaluation_status IN {StrategyEvaluationStatus.check_in_sql()}",
            name="ck_strategy_evaluation_results_status",
        ),
        CheckConstraint(
            "prior_lifecycle_status IS NULL OR "
            f"prior_lifecycle_status IN {StrategyLifecycleStatus.check_in_sql()}",
            name="ck_strategy_evaluation_results_prior_status",
        ),
        CheckConstraint(
            "new_lifecycle_status IS NULL OR "
            f"new_lifecycle_status IN {StrategyLifecycleStatus.check_in_sql()}",
            name="ck_strategy_evaluation_results_new_status",
        ),
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
        Index(
            "uq_manual_ticker_requests_active_ticker",
            "ticker",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
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


class MacroReadthroughEvent(Base):
    """Structured peer or theme read-through event."""

    __tablename__ = "macro_readthrough_events"

    macro_readthrough_event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_key = Column(String(255), nullable=False)
    source_ticker = Column(String(16), nullable=False, index=True)
    affected_ticker = Column(String(16), nullable=True, index=True)
    scope = Column(String(64), nullable=False, index=True)
    mechanism = Column(String(64), nullable=False)
    direction = Column(String(32), nullable=True)
    title = Column(Text, nullable=False)
    source = Column(String(64), nullable=False)
    event_time = Column(DateTime(timezone=True), nullable=False, index=True)
    published_at = Column(DateTime(timezone=True), nullable=False)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False, index=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("event_key", name="uq_macro_readthrough_events_event_key"),
        Index(
            "ix_macro_readthrough_events_ticker_available",
            "source_ticker",
            "available_for_decision_at",
        ),
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


class StrategyRun(Base):
    """One candidate-scoring batch for a decision time."""

    __tablename__ = "strategy_runs"

    strategy_run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    snapshot_type = Column(String(32), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    candidate_scores = relationship("CandidateScore", back_populates="strategy_run")
    trade_classifications = relationship("TradeClassification", back_populates="strategy_run")
    watch_candidates = relationship("WatchCandidate", back_populates="strategy_run")

    __table_args__ = (
        CheckConstraint(
            "snapshot_type IN ('pre_open', 'intraday')",
            name="ck_strategy_runs_snapshot_type",
        ),
        CheckConstraint(
            f"status IN {StrategyRunStatus.check_in_sql()}",
            name="ck_strategy_runs_status",
        ),
    )


class CandidateScore(Base):
    """Ranked ticker candidate for one strategy definition."""

    __tablename__ = "candidate_scores"

    candidate_score_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategy_runs.strategy_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    signal_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("signal_snapshots.signal_snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    strategy_version = Column(String(16), nullable=False)
    strategy_definition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategy_definitions.strategy_definition_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    candidate_score = Column(Numeric, nullable=False)
    candidate_status = Column(String(32), nullable=False, index=True)
    direction = Column(String(32), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    typical_horizon = Column(String(32), nullable=False)
    core_signal_evidence_json = Column(JSONB, nullable=False, default=dict)
    missing_required_signals_json = Column(JSONB, nullable=False, default=list)
    unsupported_missing_signal_families_json = Column(JSONB, nullable=False, default=list)
    invalidators_json = Column(JSONB, nullable=False, default=list)
    risk_tags_json = Column(JSONB, nullable=False, default=list)
    macro_compatibility = Column(String(32), nullable=False, index=True)
    selection_source = Column(String(32), nullable=False, index=True)
    manual_request_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    selection_reason = Column(Text, nullable=False)
    rejection_reason = Column(String(128), nullable=True, index=True)
    benchmark_context_json = Column(JSONB, nullable=False, default=dict)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False, index=True)
    source_record_refs_json = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    strategy_run = relationship("StrategyRun", back_populates="candidate_scores")
    signal_snapshot = relationship("SignalSnapshot")
    strategy_definition = relationship("StrategyDefinition")
    trade_classifications = relationship("TradeClassification", back_populates="candidate_score")
    watch_candidates = relationship("WatchCandidate", back_populates="candidate_score")
    outcome_evaluations = relationship("CandidateOutcomeEvaluation", back_populates="candidate_score")

    __table_args__ = (
        UniqueConstraint(
            "strategy_run_id",
            "ticker",
            "strategy_id",
            name="uq_candidate_scores_run_ticker_strategy",
        ),
        CheckConstraint(
            "candidate_score >= 0 AND candidate_score <= 1",
            name="ck_candidate_scores_score_range",
        ),
        CheckConstraint(
            f"candidate_status IN {CandidateStatus.check_in_sql()}",
            name="ck_candidate_scores_candidate_status",
        ),
        CheckConstraint(
            f"macro_compatibility IN {MacroCompatibility.check_in_sql()}",
            name="ck_candidate_scores_macro_compatibility",
        ),
        CheckConstraint(
            "selection_source IN ('scanner', 'manual_request', 'watchlist_pin', 'risk_manager')",
            name="ck_candidate_scores_selection_source",
        ),
        Index("ix_candidate_scores_run_score", "strategy_run_id", "candidate_score"),
        Index("ix_candidate_scores_ticker_strategy", "ticker", "strategy_id"),
    )


class WatchCandidate(Base):
    """Retained non-trade outcome linked to a scored strategy candidate."""

    __tablename__ = "watch_candidates"

    watch_candidate_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_score_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidate_scores.candidate_score_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategy_runs.strategy_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    watch_strategy_id = Column(String(64), nullable=False, index=True)
    watch_strategy_version = Column(String(16), nullable=False)
    watch_type = Column(String(64), nullable=True, index=True)
    result_status = Column(String(64), nullable=False, index=True)
    watch_reason = Column(Text, nullable=False)
    selection_context_json = Column(JSONB, nullable=False, default=dict)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    candidate_score = relationship("CandidateScore", back_populates="watch_candidates")
    strategy_run = relationship("StrategyRun", back_populates="watch_candidates")

    __table_args__ = (
        CheckConstraint(
            "watch_type IS NULL OR watch_type IN ('catalyst_watch', 'ordinary_watch')",
            name="ck_watch_candidates_watch_type",
        ),
        Index("ix_watch_candidates_ticker_strategy", "ticker", "watch_strategy_id"),
    )


class TradeClassification(Base):
    """Selected primary strategy context and portfolio-pool trade identity."""

    __tablename__ = "trade_classifications"

    trade_classification_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_score_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidate_scores.candidate_score_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategy_runs.strategy_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    selected_strategy_id = Column(String(64), nullable=False, index=True)
    selected_strategy_version = Column(String(16), nullable=False)
    expression_bucket_id = Column(String(64), nullable=False, index=True)
    expression_bucket_version = Column(String(16), nullable=False)
    trade_identity = Column(String(64), nullable=False, index=True)
    watch_type = Column(String(64), nullable=True, index=True)
    direction = Column(String(32), nullable=False, index=True)
    intended_horizon = Column(String(32), nullable=False)
    exit_policy = Column(String(128), nullable=False)
    result_status = Column(String(64), nullable=False, index=True)
    classification_reason = Column(Text, nullable=False)
    selected_strategy_context_json = Column(JSONB, nullable=False, default=dict)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    candidate_score = relationship("CandidateScore", back_populates="trade_classifications")
    strategy_run = relationship("StrategyRun", back_populates="trade_classifications")
    outcome_evaluations = relationship("CandidateOutcomeEvaluation", back_populates="trade_classification")

    __table_args__ = (
        CheckConstraint(
            f"trade_identity IN {TradeIdentity.check_in_sql()}",
            name="ck_trade_classifications_trade_identity",
        ),
        CheckConstraint(
            "watch_type IS NULL OR watch_type IN ('catalyst_watch', 'ordinary_watch')",
            name="ck_trade_classifications_watch_type",
        ),
        Index("ix_trade_classifications_ticker_strategy", "ticker", "selected_strategy_id"),
    )


class HistoricalReplayRun(Base):
    """Deterministic replay batch metadata."""

    __tablename__ = "historical_replay_runs"

    historical_replay_run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    snapshot_type = Column(String(32), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    decision_filter_json = Column(JSONB, nullable=False, default=dict)
    outcome_horizon_policy_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    outcome_evaluations = relationship("CandidateOutcomeEvaluation", back_populates="historical_replay_run")

    __table_args__ = (
        CheckConstraint(
            "snapshot_type IN ('pre_open', 'intraday')",
            name="ck_historical_replay_runs_snapshot_type",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_historical_replay_runs_status",
        ),
    )


class CandidateOutcomeEvaluation(Base):
    """Outcome attribution for candidates, trades, rejected rows, and watch items."""

    __tablename__ = "candidate_outcome_evaluations"

    candidate_outcome_evaluation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    historical_replay_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("historical_replay_runs.historical_replay_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    candidate_score_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidate_scores.candidate_score_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trade_classification_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trade_classifications.trade_classification_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    strategy_version = Column(String(16), nullable=False)
    expression_bucket_id = Column(String(64), nullable=False, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    direction = Column(String(32), nullable=False, index=True)
    catalyst_type = Column(String(128), nullable=True, index=True)
    confidence_bucket = Column(String(255), nullable=False, index=True)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    horizon_start_at = Column(DateTime(timezone=True), nullable=False)
    horizon_end_at = Column(DateTime(timezone=True), nullable=False, index=True)
    evaluation_status = Column(String(32), nullable=False, index=True)
    candidate_return = Column(Numeric, nullable=True)
    benchmark_returns_json = Column(JSONB, nullable=False, default=dict)
    peer_basket_id = Column(
        UUID(as_uuid=True),
        ForeignKey("peer_baskets.peer_basket_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    peer_basket_return = Column(Numeric, nullable=True)
    alpha = Column(Numeric, nullable=True)
    max_favorable_excursion = Column(Numeric, nullable=True)
    max_adverse_excursion = Column(Numeric, nullable=True)
    regime = Column(String(64), nullable=True, index=True)
    sector_theme = Column(String(128), nullable=True, index=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    historical_replay_run = relationship("HistoricalReplayRun", back_populates="outcome_evaluations")
    candidate_score = relationship("CandidateScore", back_populates="outcome_evaluations")
    trade_classification = relationship("TradeClassification", back_populates="outcome_evaluations")
    peer_basket = relationship("PeerBasket")

    __table_args__ = (
        CheckConstraint(
            f"trade_identity IN {TradeIdentity.check_in_sql()}",
            name="ck_candidate_outcome_evaluations_trade_identity",
        ),
        CheckConstraint(
            f"evaluation_status IN {CandidateOutcomeEvaluationStatus.check_in_sql()}",
            name="ck_candidate_outcome_evaluations_status",
        ),
        CheckConstraint(
            "horizon_end_at >= horizon_start_at",
            name="ck_candidate_outcome_evaluations_horizon_window",
        ),
        Index("ix_candidate_outcomes_strategy_bucket", "strategy_id", "confidence_bucket"),
        Index("ix_candidate_outcomes_ticker_horizon", "ticker", "horizon_end_at"),
    )


class DailyReflection(Base):
    """Persisted post-close reflection artifact and structured output."""

    __tablename__ = "daily_reflections"

    daily_reflection_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_date = Column(Date, nullable=False, unique=True, index=True)
    prompt_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_prompt_runs.prompt_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(16), nullable=False, index=True)
    portfolio_summary_json = Column(JSONB, nullable=False, default=dict)
    reflection_json = Column(JSONB, nullable=False, default=dict)
    strategy_proposal_hints_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    prompt_run = relationship("LlmPromptRun")
    learning_factors = relationship("LearningFactor", back_populates="daily_reflection")

    __table_args__ = (
        CheckConstraint(
            f"status IN {DailyReflectionStatus.check_in_sql()}",
            name="ck_daily_reflections_status",
        ),
    )


class LearningFactor(Base):
    """Persisted structured lesson extracted from daily reflection."""

    __tablename__ = "learning_factors"

    learning_factor_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    factor_key = Column(String(64), nullable=False, unique=True, index=True)
    daily_reflection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("daily_reflections.daily_reflection_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trade_date = Column(Date, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    factor_type = Column(String(64), nullable=False, index=True)
    scope = Column(String(32), nullable=False, index=True)
    status = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=True, index=True)
    condition = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False)
    confidence = Column(Numeric, nullable=False)
    activation_policy = Column(String(32), nullable=False)
    effect_tags_json = Column(JSONB, nullable=False, default=list)
    evidence_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    daily_reflection = relationship("DailyReflection", back_populates="learning_factors")
    applications = relationship("LearningFactorApplication", back_populates="learning_factor")

    __table_args__ = (
        CheckConstraint(
            "scope IN ('strategy', 'portfolio', 'trade', 'watchlist', 'risk')",
            name="ck_learning_factors_scope",
        ),
        CheckConstraint(
            f"status IN {LearningFactorStatus.check_in_sql()}",
            name="ck_learning_factors_status",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_learning_factors_confidence_range",
        ),
    )


class LearningFactorApplication(Base):
    """Join table for future learning-factor injection into trading decisions."""

    __tablename__ = "learning_factor_applications"

    learning_factor_application_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    learning_factor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("learning_factors.learning_factor_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trading_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trading_decisions.trading_decision_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_scope = Column(String(32), nullable=False, index=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    learning_factor = relationship("LearningFactor", back_populates="applications")
    trading_decision = relationship("TradingDecision")

    __table_args__ = (
        UniqueConstraint(
            "learning_factor_id",
            "trading_decision_id",
            name="uq_learning_factor_applications_factor_decision",
        ),
    )


class PositionSizingDecision(Base):
    """Deterministic position sizing output before final risk approval."""

    __tablename__ = "position_sizing_decisions"

    position_sizing_decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_score_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidate_scores.candidate_score_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trade_classification_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trade_classifications.trade_classification_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    risk_appetite = Column(String(32), nullable=False, index=True)
    base_weight = Column(Numeric, nullable=False)
    volatility_adjusted_weight = Column(Numeric, nullable=False)
    liquidity_capped_weight = Column(Numeric, nullable=False)
    final_weight = Column(Numeric, nullable=False)
    final_notional = Column(Numeric, nullable=False)
    applied_caps_json = Column(JSONB, nullable=False, default=list)
    binding_constraint = Column(String(128), nullable=True)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    candidate_score = relationship("CandidateScore")
    trade_classification = relationship("TradeClassification")
    risk_decisions = relationship("RiskDecision", back_populates="position_sizing_decision")

    __table_args__ = (
        CheckConstraint(
            f"risk_appetite IN {RiskAppetite.check_in_sql()}",
            name="ck_position_sizing_decisions_risk_appetite",
        ),
        CheckConstraint(
            "base_weight >= 0 AND base_weight <= 1 "
            "AND volatility_adjusted_weight >= 0 AND volatility_adjusted_weight <= 1 "
            "AND liquidity_capped_weight >= 0 AND liquidity_capped_weight <= 1 "
            "AND final_weight >= 0 AND final_weight <= 1",
            name="ck_position_sizing_decisions_weight_range",
        ),
    )


class PortfolioRiskSnapshot(Base):
    """Account-level risk snapshot persisted before later order wiring."""

    __tablename__ = "portfolio_risk_snapshots"

    portfolio_risk_snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    risk_appetite = Column(String(32), nullable=False, index=True)
    resolver_version = Column(String(64), nullable=False)
    margin_model_profile = Column(String(128), nullable=False)
    margin_model_version = Column(String(32), nullable=False)
    account_equity = Column(Numeric, nullable=False)
    cash_balance = Column(Numeric, nullable=False)
    buying_power = Column(Numeric, nullable=False)
    excess_liquidity = Column(Numeric, nullable=False)
    stock_margin_requirement = Column(Numeric, nullable=False)
    option_margin_requirement = Column(Numeric, nullable=False)
    total_margin_requirement = Column(Numeric, nullable=False)
    initial_margin_requirement = Column(Numeric, nullable=True)
    maintenance_margin_requirement = Column(Numeric, nullable=True)
    margin_requirement_source = Column(String(64), nullable=False)
    net_exposure = Column(Numeric, nullable=False)
    gross_exposure = Column(Numeric, nullable=False)
    beta_adjusted_net_exposure = Column(Numeric, nullable=False)
    concentration_flags_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    portfolio_risk_intents = relationship("PortfolioRiskIntent", back_populates="portfolio_risk_snapshot")
    portfolio_event_risk_assessments = relationship(
        "PortfolioEventRiskAssessment",
        back_populates="portfolio_risk_snapshot",
    )
    risk_factor_exposures = relationship("RiskFactorExposure", back_populates="portfolio_risk_snapshot")
    risk_decisions = relationship("RiskDecision", back_populates="portfolio_risk_snapshot")

    __table_args__ = (
        CheckConstraint(
            f"risk_appetite IN {RiskAppetite.check_in_sql()}",
            name="ck_portfolio_risk_snapshots_risk_appetite",
        ),
    )


class PortfolioRiskIntent(Base):
    """Persisted lookahead risk intent emitted before final risk approvals."""

    __tablename__ = "portfolio_risk_intents"

    portfolio_risk_intent_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_risk_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_risk_snapshots.portfolio_risk_snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    risk_window = Column(String(32), nullable=False)
    aggregate_risk_state = Column(String(32), nullable=False, index=True)
    position_actions_json = Column(JSONB, nullable=False, default=list)
    hedge_actions_json = Column(JSONB, nullable=False, default=list)
    binding_constraints_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    portfolio_risk_snapshot = relationship("PortfolioRiskSnapshot", back_populates="portfolio_risk_intents")


class RiskFactorExposure(Base):
    """Approximate factor concentration snapshot."""

    __tablename__ = "risk_factor_exposures"

    risk_factor_exposure_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_risk_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_risk_snapshots.portfolio_risk_snapshot_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    factor_type = Column(String(64), nullable=False, index=True)
    factor_value = Column(String(128), nullable=False, index=True)
    gross_exposure = Column(Numeric, nullable=False)
    net_exposure = Column(Numeric, nullable=False)
    long_exposure = Column(Numeric, nullable=False)
    short_exposure = Column(Numeric, nullable=False)
    position_count = Column(Integer, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    portfolio_risk_snapshot = relationship("PortfolioRiskSnapshot", back_populates="risk_factor_exposures")

    __table_args__ = (
        CheckConstraint("position_count >= 0", name="ck_risk_factor_exposures_position_count"),
        Index("ix_risk_factor_exposures_type_value", "factor_type", "factor_value"),
    )


class RiskDecision(Base):
    """Final deterministic risk outcome for one candidate/trade request."""

    __tablename__ = "risk_decisions"

    risk_decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_score_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidate_scores.candidate_score_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trade_classification_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trade_classifications.trade_classification_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    position_sizing_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("position_sizing_decisions.position_sizing_decision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    portfolio_risk_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_risk_snapshots.portfolio_risk_snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    reason_code = Column(String(128), nullable=False, index=True)
    approved_weight = Column(Numeric, nullable=False)
    approved_notional = Column(Numeric, nullable=False)
    approved_quantity = Column(Numeric, nullable=False)
    applied_rules_json = Column(JSONB, nullable=False, default=list)
    generated_hedge_action_json = Column(JSONB, nullable=True)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    candidate_score = relationship("CandidateScore")
    trade_classification = relationship("TradeClassification")
    position_sizing_decision = relationship("PositionSizingDecision", back_populates="risk_decisions")
    portfolio_risk_snapshot = relationship("PortfolioRiskSnapshot", back_populates="risk_decisions")

    __table_args__ = (
        CheckConstraint(
            f"status IN {RiskDecisionStatus.check_in_sql()}",
            name="ck_risk_decisions_status",
        ),
        CheckConstraint(
            "approved_weight >= 0 AND approved_weight <= 1",
            name="ck_risk_decisions_weight_range",
        ),
    )


class TradingDecision(Base):
    """Persisted PR05 trading decision artifact before any paper-order wiring."""

    __tablename__ = "trading_decisions"

    trading_decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_score_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidate_scores.candidate_score_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trade_classification_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trade_classifications.trade_classification_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    risk_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("risk_decisions.risk_decision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prompt_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_prompt_runs.prompt_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    decision = Column(String(64), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    strategy_version = Column(String(16), nullable=False)
    expression_bucket_id = Column(String(64), nullable=False, index=True)
    expression_bucket_version = Column(String(16), nullable=False)
    trade_identity = Column(String(64), nullable=False, index=True)
    instrument_type = Column(String(32), nullable=False)
    selection_source = Column(String(32), nullable=False, index=True)
    manual_request_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    confidence = Column(Numeric, nullable=False)
    target_weight = Column(Numeric, nullable=False)
    approved_weight = Column(Numeric, nullable=False)
    max_loss_pct = Column(Numeric, nullable=False)
    time_horizon = Column(String(32), nullable=False)
    thesis = Column(Text, nullable=False)
    key_drivers_json = Column(JSONB, nullable=False, default=list)
    counterarguments_json = Column(JSONB, nullable=False, default=list)
    invalidators_json = Column(JSONB, nullable=False, default=list)
    fallback_action = Column(String(64), nullable=True)
    paper_trade_authorized = Column(Boolean, nullable=False, default=False, server_default="false")
    context_snapshot_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    candidate_score = relationship("CandidateScore")
    trade_classification = relationship("TradeClassification")
    risk_decision = relationship("RiskDecision")
    prompt_run = relationship("LlmPromptRun")

    __table_args__ = (
        CheckConstraint(
            "decision IN ('enter_long', 'enter_short', 'hold', 'reduce', 'exit', "
            "'no_trade', 'open_option_strategy', 'close_option_strategy', "
            "'roll_option_strategy', 'adjust_option_strategy', 'avoid_event_option')",
            name="ck_trading_decisions_decision",
        ),
        CheckConstraint(
            f"trade_identity IN {TradeIdentity.check_in_sql()}",
            name="ck_trading_decisions_trade_identity",
        ),
        CheckConstraint(
            "instrument_type IN ('stock', 'option', 'watch')",
            name="ck_trading_decisions_instrument_type",
        ),
        CheckConstraint(
            "selection_source IN ('scanner', 'manual_request', 'watchlist_pin', 'risk_manager')",
            name="ck_trading_decisions_selection_source",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1 "
            "AND target_weight >= 0 AND target_weight <= 1 "
            "AND approved_weight >= 0 AND approved_weight <= 1 "
            "AND max_loss_pct >= 0 AND max_loss_pct <= 1",
            name="ck_trading_decisions_weight_ranges",
        ),
        Index("ix_trading_decisions_ticker_decision_time", "ticker", "decision_time"),
    )


class PaperOrder(Base):
    """Paper stock order staged from a validated trading decision and risk approval."""

    __tablename__ = "paper_orders"

    paper_order_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broker_order_id = Column(String(128), nullable=True, index=True)
    client_order_id = Column(String(255), nullable=False)
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
    ticker = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    action = Column(String(32), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric, nullable=False)
    order_price = Column(Numeric, nullable=True)
    status = Column(String(32), nullable=False, index=True)
    rejection_reason = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    trading_decision = relationship("TradingDecision")
    risk_decision = relationship("RiskDecision")
    executions = relationship("PaperExecution", back_populates="paper_order")

    __table_args__ = (
        UniqueConstraint("client_order_id", name="uq_paper_orders_client_order_id"),
        CheckConstraint(
            "action IN ('enter_long', 'enter_short', 'reduce', 'exit')",
            name="ck_paper_orders_action",
        ),
        CheckConstraint(
            "status IN ('new', 'accepted', 'pending_new', 'partially_filled', 'filled', "
            "'canceled', 'expired', 'rejected')",
            name="ck_paper_orders_status",
        ),
    )


class PaperExecution(Base):
    """Paper fill record for a stock order."""

    __tablename__ = "paper_executions"

    paper_execution_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paper_orders.paper_order_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    broker_order_id = Column(String(128), nullable=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    quantity = Column(Numeric, nullable=False)
    fill_price = Column(Numeric, nullable=False)
    trade_date = Column(Date, nullable=False, index=True)
    executed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    net_cash_effect = Column(Numeric, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    paper_order = relationship("PaperOrder", back_populates="executions")


class PaperPosition(Base):
    """Open or closed stock position in the unified paper margin account."""

    __tablename__ = "paper_positions"

    paper_position_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=True, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    direction = Column(String(16), nullable=False, default="long", server_default="long")
    quantity = Column(Numeric, nullable=False)
    average_cost = Column(Numeric, nullable=False)
    market_price = Column(Numeric, nullable=False)
    market_value = Column(Numeric, nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(16), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            f"trade_identity IN {TradeIdentity.check_in_sql()}",
            name="ck_paper_positions_trade_identity",
        ),
        CheckConstraint(
            "direction IN ('long', 'short')",
            name="ck_paper_positions_direction",
        ),
        CheckConstraint(
            "status IN ('open', 'closed')",
            name="ck_paper_positions_status",
        ),
    )


class PortfolioSnapshot(Base):
    """Unified simulated margin-account snapshot after stock paper executions."""

    __tablename__ = "portfolio_snapshots"

    portfolio_snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_time = Column(DateTime(timezone=True), nullable=False, index=True)
    cash_balance = Column(Numeric, nullable=False)
    account_equity = Column(Numeric, nullable=False)
    net_liquidation_value = Column(Numeric, nullable=False)
    buying_power = Column(Numeric, nullable=False)
    excess_liquidity = Column(Numeric, nullable=False)
    stock_market_value = Column(Numeric, nullable=False)
    option_market_value = Column(Numeric, nullable=False)
    stock_margin_requirement = Column(Numeric, nullable=False)
    option_margin_requirement = Column(Numeric, nullable=False)
    total_margin_requirement = Column(Numeric, nullable=False)
    initial_margin_requirement = Column(Numeric, nullable=False)
    maintenance_margin_requirement = Column(Numeric, nullable=False)
    margin_model_profile = Column(String(128), nullable=False)
    margin_model_version = Column(String(32), nullable=False)
    margin_requirement_source = Column(String(64), nullable=False)
    day_pnl = Column(Numeric, nullable=False)
    realized_pnl = Column(Numeric, nullable=False)
    unrealized_pnl = Column(Numeric, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class OptionStrategyDecision(Base):
    """Persisted PR7 paper option strategy decision."""

    __tablename__ = "option_strategy_decisions"

    option_strategy_decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trading_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trading_decisions.trading_decision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    decision_action = Column(String(64), nullable=False, index=True)
    option_strategy_type = Column(String(64), nullable=False, index=True)
    status = Column(String(16), nullable=False, index=True)
    rejection_reason = Column(String(128), nullable=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    strategy_version = Column(String(16), nullable=False)
    expression_bucket_id = Column(String(64), nullable=False, index=True)
    expression_bucket_version = Column(String(16), nullable=False)
    underlying_price = Column(Numeric, nullable=False)
    expiry = Column(Date, nullable=False, index=True)
    net_debit_or_credit = Column(Numeric, nullable=False)
    max_loss = Column(Numeric, nullable=False)
    max_profit = Column(Numeric, nullable=True)
    breakevens_json = Column(JSONB, nullable=False, default=list)
    margin_requirement = Column(Numeric, nullable=False)
    buying_power_effect = Column(Numeric, nullable=False)
    assignment_notional = Column(Numeric, nullable=False)
    portfolio_delta = Column(Numeric, nullable=False)
    portfolio_gamma = Column(Numeric, nullable=False)
    portfolio_theta = Column(Numeric, nullable=False)
    portfolio_vega = Column(Numeric, nullable=False)
    earnings_date = Column(Date, nullable=True)
    event_through_expiry = Column(Boolean, nullable=False, default=False, server_default="false")
    strategy_pairing_method = Column(String(64), nullable=False)
    assignment_plan = Column(Text, nullable=True)
    margin_model_profile = Column(String(128), nullable=False)
    margin_model_version = Column(String(32), nullable=False)
    margin_requirement_source = Column(String(64), nullable=False)
    profit_target_pct = Column(Numeric, nullable=False)
    max_loss_rule = Column(String(128), nullable=False)
    roll_conditions_json = Column(JSONB, nullable=False, default=list)
    close_conditions_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            f"trade_identity IN {TradeIdentity.check_in_sql()}",
            name="ck_option_strategy_decisions_trade_identity",
        ),
        CheckConstraint(
            "decision_action IN ('open_option_strategy', 'close_option_strategy', 'roll_option_strategy', 'adjust_option_strategy', 'avoid_event_option')",
            name="ck_option_strategy_decisions_action",
        ),
        CheckConstraint(
            "option_strategy_type IN ('long_call', 'long_put', 'put_credit_spread', 'call_credit_spread', 'long_straddle', 'long_strangle')",
            name="ck_option_strategy_decisions_type",
        ),
        CheckConstraint("status IN ('ready', 'rejected')", name="ck_option_strategy_decisions_status"),
    )


class OptionStrategyLeg(Base):
    """Per-leg option strategy metadata."""

    __tablename__ = "option_strategy_legs"

    option_strategy_leg_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    option_strategy_decision_id = Column(UUID(as_uuid=True), ForeignKey("option_strategy_decisions.option_strategy_decision_id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    contract_symbol = Column(String(32), nullable=False, index=True)
    option_type = Column(String(8), nullable=False)
    side = Column(String(8), nullable=False)
    quantity = Column(Integer, nullable=False)
    ratio_qty = Column(Integer, nullable=False, default=1, server_default="1")
    strike = Column(Numeric, nullable=False)
    expiry = Column(Date, nullable=False, index=True)
    dte = Column(Integer, nullable=False)
    delta = Column(Numeric, nullable=False)
    gamma = Column(Numeric, nullable=False)
    theta = Column(Numeric, nullable=False)
    vega = Column(Numeric, nullable=False)
    implied_volatility = Column(Numeric, nullable=True)
    iv_rank = Column(Numeric, nullable=True)
    bid = Column(Numeric, nullable=False)
    ask = Column(Numeric, nullable=False)
    mid = Column(Numeric, nullable=False)
    chosen_price = Column(Numeric, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperOptionOrder(Base):
    """Paper-only option order state."""

    __tablename__ = "paper_option_orders"

    paper_option_order_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trading_decision_id = Column(UUID(as_uuid=True), ForeignKey("trading_decisions.trading_decision_id", ondelete="SET NULL"), nullable=True, index=True)
    risk_decision_id = Column(UUID(as_uuid=True), ForeignKey("risk_decisions.risk_decision_id", ondelete="SET NULL"), nullable=True, index=True)
    option_strategy_decision_id = Column(UUID(as_uuid=True), ForeignKey("option_strategy_decisions.option_strategy_decision_id", ondelete="SET NULL"), nullable=True, index=True)
    broker_order_id = Column(String(128), nullable=True, index=True)
    client_order_id = Column(String(255), nullable=False)
    ticker = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    option_strategy_type = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    order_class = Column(String(16), nullable=False, default="simple", server_default="simple")
    trade_identity = Column(String(64), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    limit_price = Column(Numeric, nullable=False)
    status = Column(String(16), nullable=False, index=True)
    rejection_reason = Column(String(128), nullable=True)
    margin_requirement = Column(Numeric, nullable=False)
    buying_power_effect = Column(Numeric, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("client_order_id", name="uq_paper_option_orders_client_order_id"),)


class PaperOptionExecution(Base):
    """Paper-only option fill record."""

    __tablename__ = "paper_option_executions"

    paper_option_execution_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_option_order_id = Column(UUID(as_uuid=True), ForeignKey("paper_option_orders.paper_option_order_id", ondelete="CASCADE"), nullable=False, index=True)
    broker_order_id = Column(String(128), nullable=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    fill_price = Column(Numeric, nullable=False)
    trade_date = Column(Date, nullable=False, index=True)
    executed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    net_cash_effect = Column(Numeric, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperOptionPosition(Base):
    """Open option strategy state persisted locally."""

    __tablename__ = "paper_option_positions"

    paper_option_position_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    option_strategy_decision_id = Column(UUID(as_uuid=True), ForeignKey("option_strategy_decisions.option_strategy_decision_id", ondelete="SET NULL"), nullable=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    option_strategy_type = Column(String(64), nullable=False, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(16), nullable=False, index=True)
    expiry = Column(Date, nullable=False, index=True)
    max_loss = Column(Numeric, nullable=False)
    margin_requirement = Column(Numeric, nullable=False)
    buying_power_effect = Column(Numeric, nullable=False)
    assignment_notional = Column(Numeric, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class OptionRiskSnapshot(Base):
    """Persisted strategy-level option risk snapshot."""

    __tablename__ = "option_risk_snapshots"

    option_risk_snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    option_strategy_type = Column(String(64), nullable=False, index=True)
    underlying_price = Column(Numeric, nullable=False)
    portfolio_delta = Column(Numeric, nullable=False)
    portfolio_gamma = Column(Numeric, nullable=False)
    portfolio_theta = Column(Numeric, nullable=False)
    portfolio_vega = Column(Numeric, nullable=False)
    net_debit_or_credit = Column(Numeric, nullable=False)
    max_loss = Column(Numeric, nullable=False)
    max_profit = Column(Numeric, nullable=True)
    margin_requirement = Column(Numeric, nullable=False)
    buying_power_effect = Column(Numeric, nullable=False)
    assignment_notional = Column(Numeric, nullable=False)
    worst_case_assignment_notional = Column(Numeric, nullable=False)
    margin_model_profile = Column(String(128), nullable=False)
    margin_model_version = Column(String(32), nullable=False)
    margin_requirement_source = Column(String(64), nullable=False)
    risk_status = Column(String(16), nullable=False, index=True)
    reason_code = Column(String(64), nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RiskHedgeDecision(Base):
    """Persisted paper-only risk hedge overlay decision."""

    __tablename__ = "risk_hedge_decisions"

    risk_hedge_decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    risk_decision_id = Column(UUID(as_uuid=True), ForeignKey("risk_decisions.risk_decision_id", ondelete="SET NULL"), nullable=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    option_strategy_type = Column(String(64), nullable=False, index=True)
    rationale = Column(Text, nullable=False)
    hedge_cost = Column(Numeric, nullable=False)
    protected_notional = Column(Numeric, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


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
