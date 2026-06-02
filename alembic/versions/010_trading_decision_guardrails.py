"""Add trading decision guardrail tables.

Revision ID: 010
Revises: 009
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trading_decisions",
        sa.Column("trading_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_score_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trade_classification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prompt_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=16), nullable=False),
        sa.Column("expression_bucket_id", sa.String(length=64), nullable=False),
        sa.Column("expression_bucket_version", sa.String(length=16), nullable=False),
        sa.Column("trade_identity", sa.String(length=64), nullable=False),
        sa.Column("instrument_type", sa.String(length=32), nullable=False),
        sa.Column("selection_source", sa.String(length=32), nullable=False),
        sa.Column("manual_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("target_weight", sa.Numeric(), nullable=False),
        sa.Column("approved_weight", sa.Numeric(), nullable=False),
        sa.Column("max_loss_pct", sa.Numeric(), nullable=False),
        sa.Column("time_horizon", sa.String(length=32), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("invalidators_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fallback_action", sa.String(length=64), nullable=True),
        sa.Column("paper_trade_authorized", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("context_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "decision IN ('enter_long', 'enter_short', 'hold', 'reduce', 'exit', "
            "'no_trade', 'open_option_strategy', 'close_option_strategy', "
            "'roll_option_strategy', 'adjust_option_strategy', 'avoid_event_option')",
            name="ck_trading_decisions_decision",
        ),
        sa.CheckConstraint(
            "trade_identity IN ('core_holding', 'tactical_stock_trade', 'tactical_option_trade', 'risk_hedge_overlay', 'watch_only')",
            name="ck_trading_decisions_trade_identity",
        ),
        sa.CheckConstraint(
            "instrument_type IN ('stock', 'option', 'watch')",
            name="ck_trading_decisions_instrument_type",
        ),
        sa.CheckConstraint(
            "selection_source IN ('scanner', 'manual_request', 'watchlist_pin')",
            name="ck_trading_decisions_selection_source",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1 "
            "AND target_weight >= 0 AND target_weight <= 1 "
            "AND approved_weight >= 0 AND approved_weight <= 1 "
            "AND max_loss_pct >= 0 AND max_loss_pct <= 1",
            name="ck_trading_decisions_weight_ranges",
        ),
        sa.ForeignKeyConstraint(["candidate_score_id"], ["candidate_scores.candidate_score_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trade_classification_id"], ["trade_classifications.trade_classification_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["risk_decision_id"], ["risk_decisions.risk_decision_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prompt_run_id"], ["llm_prompt_runs.prompt_run_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("trading_decision_id"),
    )
    op.create_index("ix_trading_decisions_available_for_decision_at", "trading_decisions", ["available_for_decision_at"], unique=False)
    op.create_index("ix_trading_decisions_candidate_score_id", "trading_decisions", ["candidate_score_id"], unique=False)
    op.create_index("ix_trading_decisions_decision", "trading_decisions", ["decision"], unique=False)
    op.create_index("ix_trading_decisions_decision_time", "trading_decisions", ["decision_time"], unique=False)
    op.create_index("ix_trading_decisions_expression_bucket_id", "trading_decisions", ["expression_bucket_id"], unique=False)
    op.create_index("ix_trading_decisions_manual_request_id", "trading_decisions", ["manual_request_id"], unique=False)
    op.create_index("ix_trading_decisions_prompt_run_id", "trading_decisions", ["prompt_run_id"], unique=False)
    op.create_index("ix_trading_decisions_risk_decision_id", "trading_decisions", ["risk_decision_id"], unique=False)
    op.create_index("ix_trading_decisions_selection_source", "trading_decisions", ["selection_source"], unique=False)
    op.create_index("ix_trading_decisions_strategy_id", "trading_decisions", ["strategy_id"], unique=False)
    op.create_index("ix_trading_decisions_ticker", "trading_decisions", ["ticker"], unique=False)
    op.create_index("ix_trading_decisions_ticker_decision_time", "trading_decisions", ["ticker", "decision_time"], unique=False)
    op.create_index("ix_trading_decisions_trade_classification_id", "trading_decisions", ["trade_classification_id"], unique=False)
    op.create_index("ix_trading_decisions_trade_identity", "trading_decisions", ["trade_identity"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trading_decisions_trade_identity", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_trade_classification_id", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_ticker_decision_time", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_ticker", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_strategy_id", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_selection_source", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_risk_decision_id", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_prompt_run_id", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_manual_request_id", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_expression_bucket_id", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_decision_time", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_decision", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_candidate_score_id", table_name="trading_decisions")
    op.drop_index("ix_trading_decisions_available_for_decision_at", table_name="trading_decisions")
    op.drop_table("trading_decisions")
