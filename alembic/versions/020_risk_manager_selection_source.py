"""Allow risk-manager selection source in trading constraints.

Revision ID: 020
Revises: 019
Create Date: 2026-06-14

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_candidate_scores_selection_source", "candidate_scores", type_="check")
    op.create_check_constraint(
        "ck_candidate_scores_selection_source",
        "candidate_scores",
        "selection_source IN ('scanner', 'manual_request', 'watchlist_pin', 'risk_manager')",
    )
    op.drop_constraint("ck_trading_decisions_selection_source", "trading_decisions", type_="check")
    op.create_check_constraint(
        "ck_trading_decisions_selection_source",
        "trading_decisions",
        "selection_source IN ('scanner', 'manual_request', 'watchlist_pin', 'risk_manager')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_trading_decisions_selection_source", "trading_decisions", type_="check")
    op.create_check_constraint(
        "ck_trading_decisions_selection_source",
        "trading_decisions",
        "selection_source IN ('scanner', 'manual_request', 'watchlist_pin')",
    )
    op.drop_constraint("ck_candidate_scores_selection_source", "candidate_scores", type_="check")
    op.create_check_constraint(
        "ck_candidate_scores_selection_source",
        "candidate_scores",
        "selection_source IN ('scanner', 'manual_request', 'watchlist_pin')",
    )
