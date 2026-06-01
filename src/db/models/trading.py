"""Trading foundation ORM models."""
import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
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
