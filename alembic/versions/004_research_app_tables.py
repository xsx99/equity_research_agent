"""Add research app tables.

Revision ID: 004
Revises: 002
Create Date: 2026-03-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", name="uq_watchlists_ticker"),
    )

    op.create_table(
        "research_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_research_runs_status",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_research_runs_as_of", "research_runs", ["as_of"], unique=False)
    op.create_index("ix_research_runs_created_at", "research_runs", ["created_at"], unique=False)
    op.create_index("ix_research_runs_status", "research_runs", ["status"], unique=False)
    op.create_index("ix_research_runs_ticker", "research_runs", ["ticker"], unique=False)
    op.create_index(
        "ix_research_runs_ticker_as_of",
        "research_runs",
        ["ticker", "as_of"],
        unique=False,
    )

    op.create_table(
        "research_outputs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("time_horizon", sa.String(length=8), nullable=False),
        sa.Column("actionability", sa.String(length=16), nullable=False),
        sa.Column("thesis_summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "decision IN ('bullish', 'bearish', 'neutral', 'abstain')",
            name="ck_research_outputs_decision",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_research_outputs_confidence",
        ),
        sa.CheckConstraint(
            "time_horizon IN ('1d', '3d', '5d')",
            name="ck_research_outputs_time_horizon",
        ),
        sa.CheckConstraint(
            "actionability IN ('abstain', 'watch', 'actionable')",
            name="ck_research_outputs_actionability",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_research_outputs_actionability", "research_outputs", ["actionability"], unique=False)
    op.create_index("ix_research_outputs_decision", "research_outputs", ["decision"], unique=False)
    op.create_index("ix_research_outputs_time_horizon", "research_outputs", ["time_horizon"], unique=False)

    op.create_table(
        "eval_results",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("realized_return", sa.Numeric(), nullable=True),
        sa.Column("benchmark_return", sa.Numeric(), nullable=True),
        sa.Column(
            "benchmark_symbol",
            sa.String(length=16),
            nullable=False,
            server_default="SPY",
        ),
        sa.Column(
            "evaluation_method",
            sa.String(length=32),
            nullable=False,
            server_default="rule_v1",
        ),
        sa.Column("evaluation_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("outcome_label", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("horizon_days > 0", name="ck_eval_results_horizon_days"),
        sa.CheckConstraint(
            "evaluation_method IN ('rule_v1')",
            name="ck_eval_results_evaluation_method",
        ),
        sa.CheckConstraint(
            "outcome_label IS NULL OR "
            "outcome_label IN ('correct', 'partially_correct', 'wrong_direction', 'uninformative')",
            name="ck_eval_results_outcome_label",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_eval_results_evaluation_method", "eval_results", ["evaluation_method"], unique=False)
    op.create_index("ix_eval_results_outcome_label", "eval_results", ["outcome_label"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_eval_results_outcome_label", table_name="eval_results")
    op.drop_index("ix_eval_results_evaluation_method", table_name="eval_results")
    op.drop_table("eval_results")

    op.drop_index("ix_research_outputs_time_horizon", table_name="research_outputs")
    op.drop_index("ix_research_outputs_decision", table_name="research_outputs")
    op.drop_index("ix_research_outputs_actionability", table_name="research_outputs")
    op.drop_table("research_outputs")

    op.drop_index("ix_research_runs_ticker_as_of", table_name="research_runs")
    op.drop_index("ix_research_runs_ticker", table_name="research_runs")
    op.drop_index("ix_research_runs_status", table_name="research_runs")
    op.drop_index("ix_research_runs_created_at", table_name="research_runs")
    op.drop_index("ix_research_runs_as_of", table_name="research_runs")
    op.drop_table("research_runs")

    op.drop_table("watchlists")
