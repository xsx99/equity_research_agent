"""Add candidate status and watch candidates.

Revision ID: 017
Revises: 016
Create Date: 2026-06-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidate_scores",
        sa.Column("candidate_status", sa.String(length=32), nullable=True),
    )
    op.execute(
        """
        UPDATE candidate_scores
        SET candidate_status = CASE
            WHEN rejection_reason IS NULL
                AND macro_compatibility <> 'blocked'
                AND action <> 'no_trade'
                AND jsonb_array_length(COALESCE(missing_required_signals_json, '[]'::jsonb)) = 0
            THEN 'actionable'
            WHEN macro_compatibility = 'blocked'
                OR jsonb_array_length(COALESCE(unsupported_missing_signal_families_json, '[]'::jsonb)) > 0
            THEN 'blocked'
            ELSE 'watch'
        END
        """
    )
    op.alter_column("candidate_scores", "candidate_status", nullable=False)
    op.create_index("ix_candidate_scores_candidate_status", "candidate_scores", ["candidate_status"], unique=False)
    op.create_check_constraint(
        "ck_candidate_scores_candidate_status",
        "candidate_scores",
        "candidate_status IN ('actionable', 'watch', 'blocked')",
    )

    op.create_table(
        "watch_candidates",
        sa.Column("watch_candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_score_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("watch_strategy_id", sa.String(length=64), nullable=False),
        sa.Column("watch_strategy_version", sa.String(length=16), nullable=False),
        sa.Column("watch_type", sa.String(length=64), nullable=True),
        sa.Column("result_status", sa.String(length=64), nullable=False),
        sa.Column("watch_reason", sa.Text(), nullable=False),
        sa.Column("selection_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "watch_type IS NULL OR watch_type IN ('catalyst_watch', 'ordinary_watch')",
            name="ck_watch_candidates_watch_type",
        ),
        sa.ForeignKeyConstraint(["candidate_score_id"], ["candidate_scores.candidate_score_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strategy_run_id"], ["strategy_runs.strategy_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("watch_candidate_id"),
    )
    op.create_index("ix_watch_candidates_candidate_score_id", "watch_candidates", ["candidate_score_id"], unique=False)
    op.create_index("ix_watch_candidates_decision_time", "watch_candidates", ["decision_time"], unique=False)
    op.create_index("ix_watch_candidates_result_status", "watch_candidates", ["result_status"], unique=False)
    op.create_index("ix_watch_candidates_strategy_run_id", "watch_candidates", ["strategy_run_id"], unique=False)
    op.create_index("ix_watch_candidates_ticker", "watch_candidates", ["ticker"], unique=False)
    op.create_index("ix_watch_candidates_ticker_strategy", "watch_candidates", ["ticker", "watch_strategy_id"], unique=False)
    op.create_index("ix_watch_candidates_watch_strategy_id", "watch_candidates", ["watch_strategy_id"], unique=False)
    op.create_index("ix_watch_candidates_watch_type", "watch_candidates", ["watch_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_watch_candidates_watch_type", table_name="watch_candidates")
    op.drop_index("ix_watch_candidates_watch_strategy_id", table_name="watch_candidates")
    op.drop_index("ix_watch_candidates_ticker_strategy", table_name="watch_candidates")
    op.drop_index("ix_watch_candidates_ticker", table_name="watch_candidates")
    op.drop_index("ix_watch_candidates_strategy_run_id", table_name="watch_candidates")
    op.drop_index("ix_watch_candidates_result_status", table_name="watch_candidates")
    op.drop_index("ix_watch_candidates_decision_time", table_name="watch_candidates")
    op.drop_index("ix_watch_candidates_candidate_score_id", table_name="watch_candidates")
    op.drop_table("watch_candidates")

    op.drop_constraint("ck_candidate_scores_candidate_status", "candidate_scores", type_="check")
    op.drop_index("ix_candidate_scores_candidate_status", table_name="candidate_scores")
    op.drop_column("candidate_scores", "candidate_status")
