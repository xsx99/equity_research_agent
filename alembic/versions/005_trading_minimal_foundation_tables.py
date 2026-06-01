"""Add minimal trading foundation tables.

Revision ID: 005
Revises: 004
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategy_definitions",
        sa.Column("strategy_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("strategy_layer", sa.String(length=32), nullable=False),
        sa.Column("typical_horizon", sa.String(length=32), nullable=False),
        sa.Column(
            "allowed_common_stock_direction",
            sa.String(length=16),
            nullable=False,
            server_default="long_only",
        ),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "lifecycle_status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="seed"),
        sa.Column("parent_strategy_id", sa.String(length=64), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "strategy_layer IN ('tactical_pattern', 'expression_bucket')",
            name="ck_strategy_definitions_strategy_layer",
        ),
        sa.CheckConstraint(
            "allowed_common_stock_direction IN ('long_only')",
            name="ck_strategy_definitions_allowed_common_stock_direction",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('candidate', 'shadow', 'experimental', 'active', 'retired')",
            name="ck_strategy_definitions_lifecycle_status",
        ),
        sa.CheckConstraint(
            "source IN ('seed', 'reflection_learning', 'manual')",
            name="ck_strategy_definitions_source",
        ),
        sa.PrimaryKeyConstraint("strategy_definition_id"),
        sa.UniqueConstraint("strategy_id", "version", name="uq_strategy_definitions_strategy_id_version"),
    )
    op.create_index("ix_strategy_definitions_is_active", "strategy_definitions", ["is_active"], unique=False)
    op.create_index("ix_strategy_definitions_lifecycle_status", "strategy_definitions", ["lifecycle_status"], unique=False)
    op.create_index("ix_strategy_definitions_source", "strategy_definitions", ["source"], unique=False)
    op.create_index("ix_strategy_definitions_strategy_id_version", "strategy_definitions", ["strategy_id", "version"], unique=False)
    op.create_index("ix_strategy_definitions_strategy_layer", "strategy_definitions", ["strategy_layer"], unique=False)

    op.create_table(
        "llm_prompt_templates",
        sa.Column("prompt_template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("pipeline_name", sa.String(length=64), nullable=False),
        sa.Column("template_path", sa.String(length=255), nullable=False),
        sa.Column("template_hash", sa.String(length=128), nullable=False),
        sa.Column("git_commit", sa.String(length=64), nullable=True),
        sa.Column("output_schema_id", sa.String(length=128), nullable=False),
        sa.Column("output_schema_version", sa.String(length=32), nullable=False),
        sa.Column(
            "lifecycle_status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('active', 'retired')",
            name="ck_llm_prompt_templates_lifecycle_status",
        ),
        sa.PrimaryKeyConstraint("prompt_template_id"),
        sa.UniqueConstraint("prompt_id", "prompt_version", name="uq_llm_prompt_templates_prompt_id_version"),
    )
    op.create_index("ix_llm_prompt_templates_lifecycle_status", "llm_prompt_templates", ["lifecycle_status"], unique=False)
    op.create_index("ix_llm_prompt_templates_pipeline_name", "llm_prompt_templates", ["pipeline_name"], unique=False)
    op.create_index("ix_llm_prompt_templates_prompt_id_version", "llm_prompt_templates", ["prompt_id", "prompt_version"], unique=False)

    op.create_table(
        "llm_prompt_runs",
        sa.Column("prompt_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_name", sa.String(length=64), nullable=False),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rendered_prompt_hash", sa.String(length=128), nullable=False),
        sa.Column("rendered_prompt_redacted", sa.Text(), nullable=True),
        sa.Column("input_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_output_text", sa.Text(), nullable=False),
        sa.Column("parsed_output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("parse_status", sa.String(length=16), nullable=False),
        sa.Column("validation_errors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fallback_action", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "parse_status IN ('succeeded', 'failed')",
            name="ck_llm_prompt_runs_parse_status",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_template_id"],
            ["llm_prompt_templates.prompt_template_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("prompt_run_id"),
    )
    op.create_index("ix_llm_prompt_runs_parse_status", "llm_prompt_runs", ["parse_status"], unique=False)
    op.create_index("ix_llm_prompt_runs_pipeline_name", "llm_prompt_runs", ["pipeline_name"], unique=False)
    op.create_index("ix_llm_prompt_runs_pipeline_name_status", "llm_prompt_runs", ["pipeline_name", "parse_status"], unique=False)
    op.create_index("ix_llm_prompt_runs_pipeline_run_id", "llm_prompt_runs", ["pipeline_run_id"], unique=False)
    op.create_index("ix_llm_prompt_runs_prompt_template_id", "llm_prompt_runs", ["prompt_template_id"], unique=False)

    op.create_table(
        "llm_usage_events",
        sa.Column("llm_usage_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_llm_usage_events_status",
        ),
        sa.CheckConstraint("prompt_tokens >= 0", name="ck_llm_usage_events_prompt_tokens"),
        sa.CheckConstraint("completion_tokens >= 0", name="ck_llm_usage_events_completion_tokens"),
        sa.CheckConstraint("total_tokens >= 0", name="ck_llm_usage_events_total_tokens"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_llm_usage_events_latency_ms"),
        sa.CheckConstraint("retry_count >= 0", name="ck_llm_usage_events_retry_count"),
        sa.ForeignKeyConstraint(
            ["prompt_run_id"],
            ["llm_prompt_runs.prompt_run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("llm_usage_event_id"),
    )
    op.create_index("ix_llm_usage_events_provider_model", "llm_usage_events", ["provider", "model"], unique=False)
    op.create_index("ix_llm_usage_events_prompt_run_id", "llm_usage_events", ["prompt_run_id"], unique=False)
    op.create_index("ix_llm_usage_events_status", "llm_usage_events", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_llm_usage_events_status", table_name="llm_usage_events")
    op.drop_index("ix_llm_usage_events_prompt_run_id", table_name="llm_usage_events")
    op.drop_index("ix_llm_usage_events_provider_model", table_name="llm_usage_events")
    op.drop_table("llm_usage_events")

    op.drop_index("ix_llm_prompt_runs_prompt_template_id", table_name="llm_prompt_runs")
    op.drop_index("ix_llm_prompt_runs_pipeline_run_id", table_name="llm_prompt_runs")
    op.drop_index("ix_llm_prompt_runs_pipeline_name_status", table_name="llm_prompt_runs")
    op.drop_index("ix_llm_prompt_runs_pipeline_name", table_name="llm_prompt_runs")
    op.drop_index("ix_llm_prompt_runs_parse_status", table_name="llm_prompt_runs")
    op.drop_table("llm_prompt_runs")

    op.drop_index("ix_llm_prompt_templates_prompt_id_version", table_name="llm_prompt_templates")
    op.drop_index("ix_llm_prompt_templates_pipeline_name", table_name="llm_prompt_templates")
    op.drop_index("ix_llm_prompt_templates_lifecycle_status", table_name="llm_prompt_templates")
    op.drop_table("llm_prompt_templates")

    op.drop_index("ix_strategy_definitions_strategy_layer", table_name="strategy_definitions")
    op.drop_index("ix_strategy_definitions_strategy_id_version", table_name="strategy_definitions")
    op.drop_index("ix_strategy_definitions_source", table_name="strategy_definitions")
    op.drop_index("ix_strategy_definitions_lifecycle_status", table_name="strategy_definitions")
    op.drop_index("ix_strategy_definitions_is_active", table_name="strategy_definitions")
    op.drop_table("strategy_definitions")
