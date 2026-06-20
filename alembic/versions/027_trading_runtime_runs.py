"""Add persisted runtime-run observability rows.

Revision ID: 027
Revises: 026
Create Date: 2026-06-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trading_runtime_runs",
        sa.Column(
            "trading_runtime_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("execution_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('passed', 'failed', 'skipped')",
            name="ck_trading_runtime_runs_status",
        ),
        sa.PrimaryKeyConstraint("trading_runtime_run_id"),
    )
    op.create_index(
        "ix_trading_runtime_runs_as_of",
        "trading_runtime_runs",
        ["as_of"],
        unique=False,
    )
    op.create_index(
        "ix_trading_runtime_runs_completed_at",
        "trading_runtime_runs",
        ["completed_at"],
        unique=False,
    )
    op.create_index(
        "ix_trading_runtime_runs_phase",
        "trading_runtime_runs",
        ["phase"],
        unique=False,
    )
    op.create_index(
        "ix_trading_runtime_runs_phase_completed_at",
        "trading_runtime_runs",
        ["phase", "completed_at"],
        unique=False,
    )
    op.create_index(
        "ix_trading_runtime_runs_phase_trade_date_completed_at",
        "trading_runtime_runs",
        ["phase", "trade_date", "completed_at"],
        unique=False,
    )
    op.create_index(
        "ix_trading_runtime_runs_status",
        "trading_runtime_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_trading_runtime_runs_trade_date",
        "trading_runtime_runs",
        ["trade_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trading_runtime_runs_trade_date", table_name="trading_runtime_runs")
    op.drop_index("ix_trading_runtime_runs_status", table_name="trading_runtime_runs")
    op.drop_index(
        "ix_trading_runtime_runs_phase_trade_date_completed_at",
        table_name="trading_runtime_runs",
    )
    op.drop_index("ix_trading_runtime_runs_phase_completed_at", table_name="trading_runtime_runs")
    op.drop_index("ix_trading_runtime_runs_phase", table_name="trading_runtime_runs")
    op.drop_index("ix_trading_runtime_runs_completed_at", table_name="trading_runtime_runs")
    op.drop_index("ix_trading_runtime_runs_as_of", table_name="trading_runtime_runs")
    op.drop_table("trading_runtime_runs")
