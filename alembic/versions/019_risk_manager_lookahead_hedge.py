"""Add portfolio risk intents for lookahead hedge planning.

Revision ID: 019
Revises: 018
Create Date: 2026-06-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_risk_intents",
        sa.Column("portfolio_risk_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("portfolio_risk_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_window", sa.String(length=32), nullable=False),
        sa.Column("aggregate_risk_state", sa.String(length=32), nullable=False),
        sa.Column("position_actions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hedge_actions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("binding_constraints_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["portfolio_risk_snapshot_id"],
            ["portfolio_risk_snapshots.portfolio_risk_snapshot_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("portfolio_risk_intent_id"),
    )
    op.create_index(
        "ix_portfolio_risk_intents_aggregate_risk_state",
        "portfolio_risk_intents",
        ["aggregate_risk_state"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_risk_intents_decision_time",
        "portfolio_risk_intents",
        ["decision_time"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_risk_intents_portfolio_risk_snapshot_id",
        "portfolio_risk_intents",
        ["portfolio_risk_snapshot_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_portfolio_risk_intents_portfolio_risk_snapshot_id", table_name="portfolio_risk_intents")
    op.drop_index("ix_portfolio_risk_intents_decision_time", table_name="portfolio_risk_intents")
    op.drop_index("ix_portfolio_risk_intents_aggregate_risk_state", table_name="portfolio_risk_intents")
    op.drop_table("portfolio_risk_intents")
