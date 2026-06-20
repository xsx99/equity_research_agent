"""Link strategy proposals back to source daily reflections.

Revision ID: 026
Revises: 025
Create Date: 2026-06-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "strategy_proposals",
        sa.Column("daily_reflection_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_strategy_proposals_daily_reflection_id",
        "strategy_proposals",
        ["daily_reflection_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_strategy_proposals_daily_reflection_id",
        "strategy_proposals",
        "daily_reflections",
        ["daily_reflection_id"],
        ["daily_reflection_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_strategy_proposals_daily_reflection_id", "strategy_proposals", type_="foreignkey")
    op.drop_index("ix_strategy_proposals_daily_reflection_id", table_name="strategy_proposals")
    op.drop_column("strategy_proposals", "daily_reflection_id")
