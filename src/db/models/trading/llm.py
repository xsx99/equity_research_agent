"""LLM telemetry ORM models."""
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
