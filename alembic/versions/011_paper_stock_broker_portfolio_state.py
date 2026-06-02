"""Add paper stock broker and portfolio state tables.

Revision ID: 011
Revises: 010
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paper_orders",
        sa.Column("paper_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("client_order_id", sa.String(length=255), nullable=False),
        sa.Column("trading_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("order_price", sa.Numeric(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rejection_reason", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("action IN ('enter_long', 'enter_short', 'reduce', 'exit')", name="ck_paper_orders_action"),
        sa.CheckConstraint(
            "status IN ('new', 'accepted', 'pending_new', 'partially_filled', 'filled', 'canceled', 'expired', 'rejected')",
            name="ck_paper_orders_status",
        ),
        sa.ForeignKeyConstraint(["risk_decision_id"], ["risk_decisions.risk_decision_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trading_decision_id"], ["trading_decisions.trading_decision_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("paper_order_id"),
        sa.UniqueConstraint("client_order_id", name="uq_paper_orders_client_order_id"),
    )
    op.create_index("ix_paper_orders_action", "paper_orders", ["action"], unique=False)
    op.create_index("ix_paper_orders_broker_order_id", "paper_orders", ["broker_order_id"], unique=False)
    op.create_index("ix_paper_orders_client_order_id", "paper_orders", ["client_order_id"], unique=False)
    op.create_index("ix_paper_orders_risk_decision_id", "paper_orders", ["risk_decision_id"], unique=False)
    op.create_index("ix_paper_orders_status", "paper_orders", ["status"], unique=False)
    op.create_index("ix_paper_orders_strategy_id", "paper_orders", ["strategy_id"], unique=False)
    op.create_index("ix_paper_orders_ticker", "paper_orders", ["ticker"], unique=False)
    op.create_index("ix_paper_orders_trade_date", "paper_orders", ["trade_date"], unique=False)
    op.create_index("ix_paper_orders_trading_decision_id", "paper_orders", ["trading_decision_id"], unique=False)

    op.create_table(
        "paper_executions",
        sa.Column("paper_execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("fill_price", sa.Numeric(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("net_cash_effect", sa.Numeric(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["paper_order_id"], ["paper_orders.paper_order_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_execution_id"),
    )
    op.create_index("ix_paper_executions_broker_order_id", "paper_executions", ["broker_order_id"], unique=False)
    op.create_index("ix_paper_executions_executed_at", "paper_executions", ["executed_at"], unique=False)
    op.create_index("ix_paper_executions_paper_order_id", "paper_executions", ["paper_order_id"], unique=False)
    op.create_index("ix_paper_executions_ticker", "paper_executions", ["ticker"], unique=False)
    op.create_index("ix_paper_executions_trade_date", "paper_executions", ["trade_date"], unique=False)

    op.create_table(
        "paper_positions",
        sa.Column("paper_position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=True),
        sa.Column("trade_identity", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default=sa.text("'long'")),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("average_cost", sa.Numeric(), nullable=False),
        sa.Column("market_price", sa.Numeric(), nullable=False),
        sa.Column("market_value", sa.Numeric(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "trade_identity IN ('core_holding', 'tactical_stock_trade', 'tactical_option_trade', 'risk_hedge_overlay', 'watch_only')",
            name="ck_paper_positions_trade_identity",
        ),
        sa.CheckConstraint("direction IN ('long', 'short')", name="ck_paper_positions_direction"),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_paper_positions_status"),
        sa.PrimaryKeyConstraint("paper_position_id"),
    )
    op.create_index("ix_paper_positions_direction", "paper_positions", ["direction"], unique=False)
    op.create_index("ix_paper_positions_opened_at", "paper_positions", ["opened_at"], unique=False)
    op.create_index("ix_paper_positions_status", "paper_positions", ["status"], unique=False)
    op.create_index("ix_paper_positions_strategy_id", "paper_positions", ["strategy_id"], unique=False)
    op.create_index("ix_paper_positions_ticker", "paper_positions", ["ticker"], unique=False)
    op.create_index("ix_paper_positions_trade_identity", "paper_positions", ["trade_identity"], unique=False)

    op.create_table(
        "portfolio_snapshots",
        sa.Column("portfolio_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cash_balance", sa.Numeric(), nullable=False),
        sa.Column("account_equity", sa.Numeric(), nullable=False),
        sa.Column("net_liquidation_value", sa.Numeric(), nullable=False),
        sa.Column("buying_power", sa.Numeric(), nullable=False),
        sa.Column("excess_liquidity", sa.Numeric(), nullable=False),
        sa.Column("stock_market_value", sa.Numeric(), nullable=False),
        sa.Column("option_market_value", sa.Numeric(), nullable=False),
        sa.Column("stock_margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("option_margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("total_margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("initial_margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("maintenance_margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("margin_model_profile", sa.String(length=128), nullable=False),
        sa.Column("margin_model_version", sa.String(length=32), nullable=False),
        sa.Column("margin_requirement_source", sa.String(length=64), nullable=False),
        sa.Column("day_pnl", sa.Numeric(), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("portfolio_snapshot_id"),
    )
    op.create_index("ix_portfolio_snapshots_snapshot_time", "portfolio_snapshots", ["snapshot_time"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_portfolio_snapshots_snapshot_time", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")

    op.drop_index("ix_paper_positions_direction", table_name="paper_positions")
    op.drop_index("ix_paper_positions_trade_identity", table_name="paper_positions")
    op.drop_index("ix_paper_positions_ticker", table_name="paper_positions")
    op.drop_index("ix_paper_positions_strategy_id", table_name="paper_positions")
    op.drop_index("ix_paper_positions_status", table_name="paper_positions")
    op.drop_index("ix_paper_positions_opened_at", table_name="paper_positions")
    op.drop_table("paper_positions")

    op.drop_index("ix_paper_executions_trade_date", table_name="paper_executions")
    op.drop_index("ix_paper_executions_ticker", table_name="paper_executions")
    op.drop_index("ix_paper_executions_paper_order_id", table_name="paper_executions")
    op.drop_index("ix_paper_executions_executed_at", table_name="paper_executions")
    op.drop_index("ix_paper_executions_broker_order_id", table_name="paper_executions")
    op.drop_table("paper_executions")

    op.drop_index("ix_paper_orders_client_order_id", table_name="paper_orders")
    op.drop_index("ix_paper_orders_broker_order_id", table_name="paper_orders")
    op.drop_index("ix_paper_orders_trading_decision_id", table_name="paper_orders")
    op.drop_index("ix_paper_orders_trade_date", table_name="paper_orders")
    op.drop_index("ix_paper_orders_ticker", table_name="paper_orders")
    op.drop_index("ix_paper_orders_strategy_id", table_name="paper_orders")
    op.drop_index("ix_paper_orders_status", table_name="paper_orders")
    op.drop_index("ix_paper_orders_risk_decision_id", table_name="paper_orders")
    op.drop_index("ix_paper_orders_action", table_name="paper_orders")
    op.drop_table("paper_orders")
