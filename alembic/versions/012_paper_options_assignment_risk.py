"""Add PR7 paper option and assignment-risk tables.

Revision ID: 012
Revises: 011
Create Date: 2026-06-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "option_strategy_decisions",
        sa.Column("option_strategy_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trading_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("trade_identity", sa.String(length=64), nullable=False),
        sa.Column("decision_action", sa.String(length=64), nullable=False),
        sa.Column("option_strategy_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rejection_reason", sa.String(length=128), nullable=True),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=16), nullable=False),
        sa.Column("expression_bucket_id", sa.String(length=64), nullable=False),
        sa.Column("expression_bucket_version", sa.String(length=16), nullable=False),
        sa.Column("underlying_price", sa.Numeric(), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("net_debit_or_credit", sa.Numeric(), nullable=False),
        sa.Column("max_loss", sa.Numeric(), nullable=False),
        sa.Column("max_profit", sa.Numeric(), nullable=True),
        sa.Column("breakevens_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("buying_power_effect", sa.Numeric(), nullable=False),
        sa.Column("assignment_notional", sa.Numeric(), nullable=False),
        sa.Column("portfolio_delta", sa.Numeric(), nullable=False),
        sa.Column("portfolio_gamma", sa.Numeric(), nullable=False),
        sa.Column("portfolio_theta", sa.Numeric(), nullable=False),
        sa.Column("portfolio_vega", sa.Numeric(), nullable=False),
        sa.Column("earnings_date", sa.Date(), nullable=True),
        sa.Column("event_through_expiry", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("strategy_pairing_method", sa.String(length=64), nullable=False),
        sa.Column("assignment_plan", sa.Text(), nullable=True),
        sa.Column("margin_model_profile", sa.String(length=128), nullable=False),
        sa.Column("margin_model_version", sa.String(length=32), nullable=False),
        sa.Column("margin_requirement_source", sa.String(length=64), nullable=False),
        sa.Column("profit_target_pct", sa.Numeric(), nullable=False),
        sa.Column("max_loss_rule", sa.String(length=128), nullable=False),
        sa.Column("roll_conditions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("close_conditions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "trade_identity IN ('core_holding', 'tactical_stock_trade', 'tactical_option_trade', 'risk_hedge_overlay', 'watch_only')",
            name="ck_option_strategy_decisions_trade_identity",
        ),
        sa.CheckConstraint(
            "decision_action IN ('open_option_strategy', 'close_option_strategy', 'roll_option_strategy', 'adjust_option_strategy', 'avoid_event_option')",
            name="ck_option_strategy_decisions_action",
        ),
        sa.CheckConstraint(
            "option_strategy_type IN ('long_call', 'long_put', 'put_credit_spread', 'call_credit_spread', 'long_straddle', 'long_strangle')",
            name="ck_option_strategy_decisions_type",
        ),
        sa.CheckConstraint("status IN ('ready', 'rejected')", name="ck_option_strategy_decisions_status"),
        sa.ForeignKeyConstraint(["trading_decision_id"], ["trading_decisions.trading_decision_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("option_strategy_decision_id"),
    )
    op.create_index("ix_option_strategy_decisions_trading_decision_id", "option_strategy_decisions", ["trading_decision_id"], unique=False)
    op.create_index("ix_option_strategy_decisions_ticker", "option_strategy_decisions", ["ticker"], unique=False)
    op.create_index("ix_option_strategy_decisions_trade_identity", "option_strategy_decisions", ["trade_identity"], unique=False)
    op.create_index("ix_option_strategy_decisions_decision_action", "option_strategy_decisions", ["decision_action"], unique=False)
    op.create_index("ix_option_strategy_decisions_option_strategy_type", "option_strategy_decisions", ["option_strategy_type"], unique=False)
    op.create_index("ix_option_strategy_decisions_status", "option_strategy_decisions", ["status"], unique=False)
    op.create_index("ix_option_strategy_decisions_strategy_id", "option_strategy_decisions", ["strategy_id"], unique=False)
    op.create_index("ix_option_strategy_decisions_expression_bucket_id", "option_strategy_decisions", ["expression_bucket_id"], unique=False)
    op.create_index("ix_option_strategy_decisions_expiry", "option_strategy_decisions", ["expiry"], unique=False)

    op.create_table(
        "paper_option_orders",
        sa.Column("paper_option_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trading_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("option_strategy_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("option_strategy_type", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("trade_identity", sa.String(length=64), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("limit_price", sa.Numeric(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rejection_reason", sa.String(length=128), nullable=True),
        sa.Column("margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("buying_power_effect", sa.Numeric(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["trading_decision_id"], ["trading_decisions.trading_decision_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["risk_decision_id"], ["risk_decisions.risk_decision_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["option_strategy_decision_id"], ["option_strategy_decisions.option_strategy_decision_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("paper_option_order_id"),
    )
    op.create_index("ix_paper_option_orders_trading_decision_id", "paper_option_orders", ["trading_decision_id"], unique=False)
    op.create_index("ix_paper_option_orders_risk_decision_id", "paper_option_orders", ["risk_decision_id"], unique=False)
    op.create_index("ix_paper_option_orders_option_strategy_decision_id", "paper_option_orders", ["option_strategy_decision_id"], unique=False)
    op.create_index("ix_paper_option_orders_ticker", "paper_option_orders", ["ticker"], unique=False)
    op.create_index("ix_paper_option_orders_strategy_id", "paper_option_orders", ["strategy_id"], unique=False)
    op.create_index("ix_paper_option_orders_option_strategy_type", "paper_option_orders", ["option_strategy_type"], unique=False)
    op.create_index("ix_paper_option_orders_action", "paper_option_orders", ["action"], unique=False)
    op.create_index("ix_paper_option_orders_trade_identity", "paper_option_orders", ["trade_identity"], unique=False)
    op.create_index("ix_paper_option_orders_trade_date", "paper_option_orders", ["trade_date"], unique=False)
    op.create_index("ix_paper_option_orders_status", "paper_option_orders", ["status"], unique=False)

    op.create_table(
        "option_strategy_legs",
        sa.Column("option_strategy_leg_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("option_strategy_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("option_type", sa.String(length=8), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("strike", sa.Numeric(), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("dte", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Numeric(), nullable=False),
        sa.Column("gamma", sa.Numeric(), nullable=False),
        sa.Column("theta", sa.Numeric(), nullable=False),
        sa.Column("vega", sa.Numeric(), nullable=False),
        sa.Column("iv_rank", sa.Numeric(), nullable=True),
        sa.Column("bid", sa.Numeric(), nullable=False),
        sa.Column("ask", sa.Numeric(), nullable=False),
        sa.Column("mid", sa.Numeric(), nullable=False),
        sa.Column("chosen_price", sa.Numeric(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["option_strategy_decision_id"], ["option_strategy_decisions.option_strategy_decision_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("option_strategy_leg_id"),
    )
    op.create_index("ix_option_strategy_legs_option_strategy_decision_id", "option_strategy_legs", ["option_strategy_decision_id"], unique=False)
    op.create_index("ix_option_strategy_legs_ticker", "option_strategy_legs", ["ticker"], unique=False)
    op.create_index("ix_option_strategy_legs_expiry", "option_strategy_legs", ["expiry"], unique=False)

    op.create_table(
        "paper_option_executions",
        sa.Column("paper_option_execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_option_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("fill_price", sa.Numeric(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("net_cash_effect", sa.Numeric(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["paper_option_order_id"], ["paper_option_orders.paper_option_order_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_option_execution_id"),
    )
    op.create_index("ix_paper_option_executions_paper_option_order_id", "paper_option_executions", ["paper_option_order_id"], unique=False)
    op.create_index("ix_paper_option_executions_ticker", "paper_option_executions", ["ticker"], unique=False)
    op.create_index("ix_paper_option_executions_trade_date", "paper_option_executions", ["trade_date"], unique=False)
    op.create_index("ix_paper_option_executions_executed_at", "paper_option_executions", ["executed_at"], unique=False)

    op.create_table(
        "paper_option_positions",
        sa.Column("paper_option_position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("option_strategy_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("option_strategy_type", sa.String(length=64), nullable=False),
        sa.Column("trade_identity", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("max_loss", sa.Numeric(), nullable=False),
        sa.Column("margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("buying_power_effect", sa.Numeric(), nullable=False),
        sa.Column("assignment_notional", sa.Numeric(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["option_strategy_decision_id"], ["option_strategy_decisions.option_strategy_decision_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("paper_option_position_id"),
    )
    op.create_index("ix_paper_option_positions_option_strategy_decision_id", "paper_option_positions", ["option_strategy_decision_id"], unique=False)
    op.create_index("ix_paper_option_positions_ticker", "paper_option_positions", ["ticker"], unique=False)
    op.create_index("ix_paper_option_positions_strategy_id", "paper_option_positions", ["strategy_id"], unique=False)
    op.create_index("ix_paper_option_positions_option_strategy_type", "paper_option_positions", ["option_strategy_type"], unique=False)
    op.create_index("ix_paper_option_positions_trade_identity", "paper_option_positions", ["trade_identity"], unique=False)
    op.create_index("ix_paper_option_positions_opened_at", "paper_option_positions", ["opened_at"], unique=False)
    op.create_index("ix_paper_option_positions_status", "paper_option_positions", ["status"], unique=False)
    op.create_index("ix_paper_option_positions_expiry", "paper_option_positions", ["expiry"], unique=False)

    op.create_table(
        "option_risk_snapshots",
        sa.Column("option_risk_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("trade_identity", sa.String(length=64), nullable=False),
        sa.Column("option_strategy_type", sa.String(length=64), nullable=False),
        sa.Column("underlying_price", sa.Numeric(), nullable=False),
        sa.Column("portfolio_delta", sa.Numeric(), nullable=False),
        sa.Column("portfolio_gamma", sa.Numeric(), nullable=False),
        sa.Column("portfolio_theta", sa.Numeric(), nullable=False),
        sa.Column("portfolio_vega", sa.Numeric(), nullable=False),
        sa.Column("net_debit_or_credit", sa.Numeric(), nullable=False),
        sa.Column("max_loss", sa.Numeric(), nullable=False),
        sa.Column("max_profit", sa.Numeric(), nullable=True),
        sa.Column("margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("buying_power_effect", sa.Numeric(), nullable=False),
        sa.Column("assignment_notional", sa.Numeric(), nullable=False),
        sa.Column("worst_case_assignment_notional", sa.Numeric(), nullable=False),
        sa.Column("margin_model_profile", sa.String(length=128), nullable=False),
        sa.Column("margin_model_version", sa.String(length=32), nullable=False),
        sa.Column("margin_requirement_source", sa.String(length=64), nullable=False),
        sa.Column("risk_status", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("option_risk_snapshot_id"),
    )
    op.create_index("ix_option_risk_snapshots_ticker", "option_risk_snapshots", ["ticker"], unique=False)
    op.create_index("ix_option_risk_snapshots_trade_identity", "option_risk_snapshots", ["trade_identity"], unique=False)
    op.create_index("ix_option_risk_snapshots_option_strategy_type", "option_risk_snapshots", ["option_strategy_type"], unique=False)
    op.create_index("ix_option_risk_snapshots_risk_status", "option_risk_snapshots", ["risk_status"], unique=False)

    op.create_table(
        "risk_hedge_decisions",
        sa.Column("risk_hedge_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("trade_identity", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("option_strategy_type", sa.String(length=64), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("hedge_cost", sa.Numeric(), nullable=False),
        sa.Column("protected_notional", sa.Numeric(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["risk_decision_id"], ["risk_decisions.risk_decision_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("risk_hedge_decision_id"),
    )
    op.create_index("ix_risk_hedge_decisions_risk_decision_id", "risk_hedge_decisions", ["risk_decision_id"], unique=False)
    op.create_index("ix_risk_hedge_decisions_ticker", "risk_hedge_decisions", ["ticker"], unique=False)
    op.create_index("ix_risk_hedge_decisions_trade_identity", "risk_hedge_decisions", ["trade_identity"], unique=False)
    op.create_index("ix_risk_hedge_decisions_action", "risk_hedge_decisions", ["action"], unique=False)
    op.create_index("ix_risk_hedge_decisions_option_strategy_type", "risk_hedge_decisions", ["option_strategy_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_risk_hedge_decisions_option_strategy_type", table_name="risk_hedge_decisions")
    op.drop_index("ix_risk_hedge_decisions_action", table_name="risk_hedge_decisions")
    op.drop_index("ix_risk_hedge_decisions_trade_identity", table_name="risk_hedge_decisions")
    op.drop_index("ix_risk_hedge_decisions_ticker", table_name="risk_hedge_decisions")
    op.drop_index("ix_risk_hedge_decisions_risk_decision_id", table_name="risk_hedge_decisions")
    op.drop_table("risk_hedge_decisions")

    op.drop_index("ix_option_risk_snapshots_risk_status", table_name="option_risk_snapshots")
    op.drop_index("ix_option_risk_snapshots_option_strategy_type", table_name="option_risk_snapshots")
    op.drop_index("ix_option_risk_snapshots_trade_identity", table_name="option_risk_snapshots")
    op.drop_index("ix_option_risk_snapshots_ticker", table_name="option_risk_snapshots")
    op.drop_table("option_risk_snapshots")

    op.drop_index("ix_paper_option_positions_expiry", table_name="paper_option_positions")
    op.drop_index("ix_paper_option_positions_status", table_name="paper_option_positions")
    op.drop_index("ix_paper_option_positions_opened_at", table_name="paper_option_positions")
    op.drop_index("ix_paper_option_positions_trade_identity", table_name="paper_option_positions")
    op.drop_index("ix_paper_option_positions_option_strategy_type", table_name="paper_option_positions")
    op.drop_index("ix_paper_option_positions_strategy_id", table_name="paper_option_positions")
    op.drop_index("ix_paper_option_positions_ticker", table_name="paper_option_positions")
    op.drop_index("ix_paper_option_positions_option_strategy_decision_id", table_name="paper_option_positions")
    op.drop_table("paper_option_positions")

    op.drop_index("ix_paper_option_executions_executed_at", table_name="paper_option_executions")
    op.drop_index("ix_paper_option_executions_trade_date", table_name="paper_option_executions")
    op.drop_index("ix_paper_option_executions_ticker", table_name="paper_option_executions")
    op.drop_index("ix_paper_option_executions_paper_option_order_id", table_name="paper_option_executions")
    op.drop_table("paper_option_executions")

    op.drop_index("ix_paper_option_orders_status", table_name="paper_option_orders")
    op.drop_index("ix_paper_option_orders_trade_date", table_name="paper_option_orders")
    op.drop_index("ix_paper_option_orders_trade_identity", table_name="paper_option_orders")
    op.drop_index("ix_paper_option_orders_action", table_name="paper_option_orders")
    op.drop_index("ix_paper_option_orders_option_strategy_type", table_name="paper_option_orders")
    op.drop_index("ix_paper_option_orders_strategy_id", table_name="paper_option_orders")
    op.drop_index("ix_paper_option_orders_ticker", table_name="paper_option_orders")
    op.drop_index("ix_paper_option_orders_option_strategy_decision_id", table_name="paper_option_orders")
    op.drop_index("ix_paper_option_orders_risk_decision_id", table_name="paper_option_orders")
    op.drop_index("ix_paper_option_orders_trading_decision_id", table_name="paper_option_orders")
    op.drop_table("paper_option_orders")

    op.drop_index("ix_option_strategy_legs_expiry", table_name="option_strategy_legs")
    op.drop_index("ix_option_strategy_legs_ticker", table_name="option_strategy_legs")
    op.drop_index("ix_option_strategy_legs_option_strategy_decision_id", table_name="option_strategy_legs")
    op.drop_table("option_strategy_legs")

    op.drop_index("ix_option_strategy_decisions_expiry", table_name="option_strategy_decisions")
    op.drop_index("ix_option_strategy_decisions_expression_bucket_id", table_name="option_strategy_decisions")
    op.drop_index("ix_option_strategy_decisions_strategy_id", table_name="option_strategy_decisions")
    op.drop_index("ix_option_strategy_decisions_status", table_name="option_strategy_decisions")
    op.drop_index("ix_option_strategy_decisions_option_strategy_type", table_name="option_strategy_decisions")
    op.drop_index("ix_option_strategy_decisions_decision_action", table_name="option_strategy_decisions")
    op.drop_index("ix_option_strategy_decisions_trade_identity", table_name="option_strategy_decisions")
    op.drop_index("ix_option_strategy_decisions_ticker", table_name="option_strategy_decisions")
    op.drop_index("ix_option_strategy_decisions_trading_decision_id", table_name="option_strategy_decisions")
    op.drop_table("option_strategy_decisions")
