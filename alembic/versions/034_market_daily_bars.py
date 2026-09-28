"""Add persisted provider-normalized market daily bars.

Revision ID: 034
Revises: 033
Create Date: 2026-09-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_daily_bars",
        sa.Column("market_daily_bar_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open_raw", sa.Numeric(), nullable=True),
        sa.Column("high_raw", sa.Numeric(), nullable=True),
        sa.Column("low_raw", sa.Numeric(), nullable=True),
        sa.Column("close_raw", sa.Numeric(), nullable=False),
        sa.Column("adj_close", sa.Numeric(), nullable=True),
        sa.Column("volume_raw", sa.BigInteger(), nullable=True),
        sa.Column("dividend", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("stock_split", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "quality_flags_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("market_daily_bar_id"),
        sa.UniqueConstraint(
            "ticker",
            "trade_date",
            "provider",
            name="uq_market_daily_bars_ticker_trade_date_provider",
        ),
    )
    op.create_index(
        "ix_market_daily_bars_ticker_trade_date",
        "market_daily_bars",
        ["ticker", "trade_date"],
        unique=False,
    )
    op.create_index(
        "ix_market_daily_bars_available_for_decision_at",
        "market_daily_bars",
        ["available_for_decision_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_daily_bars_available_for_decision_at",
        table_name="market_daily_bars",
    )
    op.drop_index(
        "ix_market_daily_bars_ticker_trade_date",
        table_name="market_daily_bars",
    )
    op.drop_table("market_daily_bars")
