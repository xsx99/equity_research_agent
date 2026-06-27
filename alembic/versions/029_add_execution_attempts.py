"""Add execution attempt audit rows.

Revision ID: 029
Revises: 028
Create Date: 2026-06-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_attempts",
        sa.Column("execution_attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trading_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("paper_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("paper_option_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("trade_identity", sa.String(length=64), nullable=False),
        sa.Column("instrument_type", sa.String(length=32), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('submitted', 'skipped', 'failed')",
            name="ck_execution_attempts_outcome",
        ),
        sa.CheckConstraint(
            "phase IN ('preopen', 'intraday', 'manual_review')",
            name="ck_execution_attempts_phase",
        ),
        sa.CheckConstraint(
            "reason_code IN ("
            "'submitted', 'not_executable_action', 'instrument_mismatch', 'not_authorized', "
            "'risk_missing', 'risk_rejected', 'dry_run', 'broker_unavailable', "
            "'order_rejected', 'no_fill', 'missing_credentials', 'broker_error'"
            ")",
            name="ck_execution_attempts_reason_code",
        ),
        sa.ForeignKeyConstraint(
            ["paper_option_order_id"],
            ["paper_option_orders.paper_option_order_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["paper_order_id"],
            ["paper_orders.paper_order_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["risk_decision_id"],
            ["risk_decisions.risk_decision_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trading_decision_id"],
            ["trading_decisions.trading_decision_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("execution_attempt_id"),
    )
    op.create_index(
        "ix_execution_attempts_action",
        "execution_attempts",
        ["action"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_created_at",
        "execution_attempts",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_instrument_type",
        "execution_attempts",
        ["instrument_type"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_outcome",
        "execution_attempts",
        ["outcome"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_paper_option_order_id",
        "execution_attempts",
        ["paper_option_order_id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_paper_order_id",
        "execution_attempts",
        ["paper_order_id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_phase_created",
        "execution_attempts",
        ["phase", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_reason_code",
        "execution_attempts",
        ["reason_code"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_risk_decision_id",
        "execution_attempts",
        ["risk_decision_id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_strategy_id",
        "execution_attempts",
        ["strategy_id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_ticker",
        "execution_attempts",
        ["ticker"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_trade_identity",
        "execution_attempts",
        ["trade_identity"],
        unique=False,
    )
    op.create_index(
        "ix_execution_attempts_trading_decision_id",
        "execution_attempts",
        ["trading_decision_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("execution_attempts")
