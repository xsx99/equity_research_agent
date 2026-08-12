"""Add outcome-maturation identity and manual decision lineage.

Revision ID: 033
Revises: 032
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SNAPSHOT_TYPES = "snapshot_type IN ('pre_open', 'manual', 'intraday')"
_PREVIOUS_SNAPSHOT_TYPES = "snapshot_type IN ('pre_open', 'intraday')"


def upgrade() -> None:
    op.add_column(
        "historical_replay_runs",
        sa.Column("evaluation_as_of_session", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_historical_replay_runs_evaluation_as_of_session",
        "historical_replay_runs",
        ["evaluation_as_of_session"],
    )
    op.drop_constraint("ck_historical_replay_runs_snapshot_type", "historical_replay_runs", type_="check")
    op.create_check_constraint(
        "ck_historical_replay_runs_snapshot_type",
        "historical_replay_runs",
        _SNAPSHOT_TYPES,
    )
    op.drop_constraint("ck_strategy_runs_snapshot_type", "strategy_runs", type_="check")
    op.create_check_constraint(
        "ck_strategy_runs_snapshot_type",
        "strategy_runs",
        _SNAPSHOT_TYPES,
    )
    op.create_unique_constraint(
        "uq_candidate_outcomes_maturation_checkpoint",
        "candidate_outcome_evaluations",
        ["candidate_score_id", "evaluation_status", "horizon_end_at"],
    )
    op.create_index(
        "ix_candidate_outcomes_due_checkpoint",
        "candidate_outcome_evaluations",
        ["candidate_score_id", "evaluation_status", "horizon_end_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_outcomes_due_checkpoint", table_name="candidate_outcome_evaluations")
    op.drop_constraint(
        "uq_candidate_outcomes_maturation_checkpoint",
        "candidate_outcome_evaluations",
        type_="unique",
    )
    op.drop_constraint("ck_strategy_runs_snapshot_type", "strategy_runs", type_="check")
    op.create_check_constraint("ck_strategy_runs_snapshot_type", "strategy_runs", _PREVIOUS_SNAPSHOT_TYPES)
    op.drop_constraint("ck_historical_replay_runs_snapshot_type", "historical_replay_runs", type_="check")
    op.create_check_constraint(
        "ck_historical_replay_runs_snapshot_type",
        "historical_replay_runs",
        _PREVIOUS_SNAPSHOT_TYPES,
    )
    op.drop_index("ix_historical_replay_runs_evaluation_as_of_session", table_name="historical_replay_runs")
    op.drop_column("historical_replay_runs", "evaluation_as_of_session")
