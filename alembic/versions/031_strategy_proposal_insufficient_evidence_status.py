"""Add insufficient evidence strategy proposal status.

Revision ID: 031
Revises: 030
Create Date: 2026-07-18

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CURRENT_STATUS_CONSTRAINT = (
    "proposal_status IN ("
    "'accepted', 'duplicate_rejected', 'proposal_failed', "
    "'insufficient_evidence_rejected'"
    ")"
)

_PREVIOUS_STATUS_CONSTRAINT = (
    "proposal_status IN ("
    "'accepted', 'duplicate_rejected', 'proposal_failed'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_strategy_proposals_status",
        "strategy_proposals",
        type_="check",
    )
    op.create_check_constraint(
        "ck_strategy_proposals_status",
        "strategy_proposals",
        _CURRENT_STATUS_CONSTRAINT,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_strategy_proposals_status",
        "strategy_proposals",
        type_="check",
    )
    op.create_check_constraint(
        "ck_strategy_proposals_status",
        "strategy_proposals",
        _PREVIOUS_STATUS_CONSTRAINT,
    )
