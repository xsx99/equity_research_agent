"""Add Alpaca option execution contract fields.

Revision ID: 021
Revises: 020
Create Date: 2026-06-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "option_strategy_legs",
        sa.Column("contract_symbol", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "option_strategy_legs",
        sa.Column("ratio_qty", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_option_strategy_legs_contract_symbol",
        "option_strategy_legs",
        ["contract_symbol"],
        unique=False,
    )
    op.execute(
        """
        UPDATE option_strategy_legs
        SET contract_symbol = UPPER(ticker)
            || TO_CHAR(expiry, 'YYMMDD')
            || CASE WHEN option_type = 'call' THEN 'C' ELSE 'P' END
            || LPAD(CAST(ROUND(CAST(strike AS NUMERIC) * 1000) AS TEXT), 8, '0')
        WHERE contract_symbol IS NULL
        """
    )
    op.alter_column("option_strategy_legs", "contract_symbol", nullable=False)

    op.add_column(
        "paper_option_orders",
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "paper_option_orders",
        sa.Column("client_order_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "paper_option_orders",
        sa.Column("order_class", sa.String(length=16), nullable=False, server_default="simple"),
    )
    op.create_index(
        "ix_paper_option_orders_broker_order_id",
        "paper_option_orders",
        ["broker_order_id"],
        unique=False,
    )
    op.execute(
        """
        UPDATE paper_option_orders
        SET client_order_id = CAST(trade_date AS TEXT)
            || ':' || ticker
            || ':' || strategy_id
            || ':' || action
        WHERE client_order_id IS NULL
        """
    )
    op.alter_column("paper_option_orders", "client_order_id", nullable=False)
    op.create_unique_constraint(
        "uq_paper_option_orders_client_order_id",
        "paper_option_orders",
        ["client_order_id"],
    )

    op.add_column(
        "paper_option_executions",
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_paper_option_executions_broker_order_id",
        "paper_option_executions",
        ["broker_order_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_paper_option_executions_broker_order_id", table_name="paper_option_executions")
    op.drop_column("paper_option_executions", "broker_order_id")

    op.drop_constraint("uq_paper_option_orders_client_order_id", "paper_option_orders", type_="unique")
    op.drop_index("ix_paper_option_orders_broker_order_id", table_name="paper_option_orders")
    op.drop_column("paper_option_orders", "order_class")
    op.drop_column("paper_option_orders", "client_order_id")
    op.drop_column("paper_option_orders", "broker_order_id")

    op.drop_index("ix_option_strategy_legs_contract_symbol", table_name="option_strategy_legs")
    op.drop_column("option_strategy_legs", "ratio_qty")
    op.drop_column("option_strategy_legs", "contract_symbol")
