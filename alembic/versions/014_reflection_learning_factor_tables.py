"""Add PR9 reflection and learning-factor tables.

Revision ID: 014
Revises: 013
Create Date: 2026-06-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_reflections",
        sa.Column("daily_reflection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("prompt_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("portfolio_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reflection_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("strategy_proposal_hints_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('succeeded', 'fallback')", name="ck_daily_reflections_status"),
        sa.ForeignKeyConstraint(["prompt_run_id"], ["llm_prompt_runs.prompt_run_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("daily_reflection_id"),
        sa.UniqueConstraint("trade_date", name="uq_daily_reflections_trade_date"),
    )
    op.create_index("ix_daily_reflections_trade_date", "daily_reflections", ["trade_date"], unique=True)
    op.create_index("ix_daily_reflections_prompt_run_id", "daily_reflections", ["prompt_run_id"], unique=False)
    op.create_index("ix_daily_reflections_status", "daily_reflections", ["status"], unique=False)

    op.create_table(
        "learning_factors",
        sa.Column("learning_factor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("factor_key", sa.String(length=64), nullable=False),
        sa.Column("daily_reflection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("factor_type", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=True),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("activation_policy", sa.String(length=32), nullable=False),
        sa.Column("effect_tags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("scope IN ('strategy', 'portfolio', 'trade', 'watchlist', 'risk')", name="ck_learning_factors_scope"),
        sa.CheckConstraint("status IN ('candidate', 'observation', 'shadow', 'active', 'suppressed', 'retired')", name="ck_learning_factors_status"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_learning_factors_confidence_range"),
        sa.ForeignKeyConstraint(["daily_reflection_id"], ["daily_reflections.daily_reflection_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("learning_factor_id"),
        sa.UniqueConstraint("factor_key", name="uq_learning_factors_factor_key"),
    )
    op.create_index("ix_learning_factors_factor_key", "learning_factors", ["factor_key"], unique=True)
    op.create_index("ix_learning_factors_daily_reflection_id", "learning_factors", ["daily_reflection_id"], unique=False)
    op.create_index("ix_learning_factors_trade_date", "learning_factors", ["trade_date"], unique=False)
    op.create_index("ix_learning_factors_factor_type", "learning_factors", ["factor_type"], unique=False)
    op.create_index("ix_learning_factors_scope", "learning_factors", ["scope"], unique=False)
    op.create_index("ix_learning_factors_status", "learning_factors", ["status"], unique=False)
    op.create_index("ix_learning_factors_strategy_id", "learning_factors", ["strategy_id"], unique=False)

    op.create_table(
        "learning_factor_applications",
        sa.Column("learning_factor_application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("learning_factor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trading_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_scope", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["learning_factor_id"], ["learning_factors.learning_factor_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trading_decision_id"], ["trading_decisions.trading_decision_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("learning_factor_application_id"),
        sa.UniqueConstraint(
            "learning_factor_id",
            "trading_decision_id",
            name="uq_learning_factor_applications_factor_decision",
        ),
    )
    op.create_index(
        "ix_learning_factor_applications_learning_factor_id",
        "learning_factor_applications",
        ["learning_factor_id"],
        unique=False,
    )
    op.create_index(
        "ix_learning_factor_applications_trading_decision_id",
        "learning_factor_applications",
        ["trading_decision_id"],
        unique=False,
    )
    op.create_index(
        "ix_learning_factor_applications_application_scope",
        "learning_factor_applications",
        ["application_scope"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_learning_factor_applications_application_scope", table_name="learning_factor_applications")
    op.drop_index("ix_learning_factor_applications_trading_decision_id", table_name="learning_factor_applications")
    op.drop_index("ix_learning_factor_applications_learning_factor_id", table_name="learning_factor_applications")
    op.drop_table("learning_factor_applications")

    op.drop_index("ix_learning_factors_strategy_id", table_name="learning_factors")
    op.drop_index("ix_learning_factors_status", table_name="learning_factors")
    op.drop_index("ix_learning_factors_scope", table_name="learning_factors")
    op.drop_index("ix_learning_factors_factor_type", table_name="learning_factors")
    op.drop_index("ix_learning_factors_trade_date", table_name="learning_factors")
    op.drop_index("ix_learning_factors_daily_reflection_id", table_name="learning_factors")
    op.drop_index("ix_learning_factors_factor_key", table_name="learning_factors")
    op.drop_table("learning_factors")

    op.drop_index("ix_daily_reflections_status", table_name="daily_reflections")
    op.drop_index("ix_daily_reflections_prompt_run_id", table_name="daily_reflections")
    op.drop_index("ix_daily_reflections_trade_date", table_name="daily_reflections")
    op.drop_table("daily_reflections")
