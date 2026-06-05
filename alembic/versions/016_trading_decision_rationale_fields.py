"""Add rationale fields to trading decisions.

Revision ID: 016
Revises: 015
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trading_decisions",
        sa.Column(
            "key_drivers_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "trading_decisions",
        sa.Column(
            "counterarguments_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("trading_decisions", "key_drivers_json", server_default=None)
    op.alter_column("trading_decisions", "counterarguments_json", server_default=None)


def downgrade() -> None:
    op.drop_column("trading_decisions", "counterarguments_json")
    op.drop_column("trading_decisions", "key_drivers_json")
