"""Add persisted cross-sectional relative-strength ranking cohorts.

Revision ID: 032
Revises: 031
Create Date: 2026-07-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "universe_ranking_runs",
        sa.Column("universe_ranking_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("universe_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eligible_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shortlist_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'degraded', 'failed')",
            name="ck_universe_ranking_runs_status",
        ),
        sa.CheckConstraint("input_count >= 0", name="ck_universe_ranking_runs_input_count"),
        sa.CheckConstraint("eligible_count >= 0", name="ck_universe_ranking_runs_eligible_count"),
        sa.CheckConstraint("shortlist_count >= 0", name="ck_universe_ranking_runs_shortlist_count"),
        sa.CheckConstraint("eligible_count <= input_count", name="ck_universe_ranking_runs_eligible_input"),
        sa.CheckConstraint("shortlist_count <= eligible_count", name="ck_universe_ranking_runs_shortlist_eligible"),
        sa.ForeignKeyConstraint(
            ["universe_snapshot_id"],
            ["universe_snapshots.universe_snapshot_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("universe_ranking_run_id"),
    )
    op.create_index("ix_universe_ranking_runs_universe_snapshot_id", "universe_ranking_runs", ["universe_snapshot_id"])
    op.create_index("ix_universe_ranking_runs_decision_time", "universe_ranking_runs", ["decision_time"])
    op.create_index("ix_universe_ranking_runs_status", "universe_ranking_runs", ["status"])
    op.create_index("ix_universe_ranking_runs_snapshot_decision", "universe_ranking_runs", ["universe_snapshot_id", "decision_time"])

    op.create_table(
        "universe_rankings",
        sa.Column("universe_ranking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("universe_ranking_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("overall_rank", sa.Integer(), nullable=True),
        sa.Column("overall_percentile", sa.Numeric(), nullable=True),
        sa.Column("relative_strength_score", sa.Numeric(), nullable=True),
        sa.Column("data_confidence", sa.Numeric(), nullable=True),
        sa.Column("peer_group_type", sa.String(length=32), nullable=True),
        sa.Column("peer_group_id", sa.String(length=128), nullable=True),
        sa.Column("peer_group_size", sa.Integer(), nullable=True),
        sa.Column("is_automatic_shortlist", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("forced_inclusion_reasons_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("positive_contributors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("negative_contributors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("missing_inputs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('ranked', 'insufficient_data')", name="ck_universe_rankings_status"),
        sa.CheckConstraint("relative_strength_score IS NULL OR (relative_strength_score >= 0 AND relative_strength_score <= 1)", name="ck_universe_rankings_score_range"),
        sa.CheckConstraint("data_confidence IS NULL OR (data_confidence >= 0 AND data_confidence <= 1)", name="ck_universe_rankings_confidence_range"),
        sa.CheckConstraint("overall_percentile IS NULL OR (overall_percentile >= 0 AND overall_percentile <= 1)", name="ck_universe_rankings_percentile_range"),
        sa.CheckConstraint("overall_rank IS NULL OR overall_rank >= 0", name="ck_universe_rankings_rank"),
        sa.CheckConstraint("peer_group_size IS NULL OR peer_group_size >= 0", name="ck_universe_rankings_peer_size"),
        sa.ForeignKeyConstraint(["universe_ranking_run_id"], ["universe_ranking_runs.universe_ranking_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("universe_ranking_id"),
        sa.UniqueConstraint("universe_ranking_run_id", "ticker", name="uq_universe_rankings_run_ticker"),
    )
    op.create_index("ix_universe_rankings_universe_ranking_run_id", "universe_rankings", ["universe_ranking_run_id"])
    op.create_index("ix_universe_rankings_ticker", "universe_rankings", ["ticker"])
    op.create_index("ix_universe_rankings_decision_time", "universe_rankings", ["decision_time"])
    op.create_index("ix_universe_rankings_status", "universe_rankings", ["status"])
    op.create_index("ix_universe_rankings_automatic_shortlist", "universe_rankings", ["is_automatic_shortlist"])
    op.create_index("ix_universe_rankings_run_rank", "universe_rankings", ["universe_ranking_run_id", "overall_rank"])
    op.create_index("ix_universe_rankings_ticker_decision_time", "universe_rankings", ["ticker", "decision_time"])

    op.add_column("candidate_scores", sa.Column("universe_ranking_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("candidate_scores", sa.Column("universe_ranking_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_candidate_scores_universe_ranking_run", "candidate_scores", "universe_ranking_runs", ["universe_ranking_run_id"], ["universe_ranking_run_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_candidate_scores_universe_ranking", "candidate_scores", "universe_rankings", ["universe_ranking_id"], ["universe_ranking_id"], ondelete="SET NULL")
    op.create_index("ix_candidate_scores_universe_ranking_run_id", "candidate_scores", ["universe_ranking_run_id"])
    op.create_index("ix_candidate_scores_universe_ranking_id", "candidate_scores", ["universe_ranking_id"])


def downgrade() -> None:
    op.drop_index("ix_candidate_scores_universe_ranking_id", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_universe_ranking_run_id", table_name="candidate_scores")
    op.drop_constraint("fk_candidate_scores_universe_ranking", "candidate_scores", type_="foreignkey")
    op.drop_constraint("fk_candidate_scores_universe_ranking_run", "candidate_scores", type_="foreignkey")
    op.drop_column("candidate_scores", "universe_ranking_id")
    op.drop_column("candidate_scores", "universe_ranking_run_id")
    op.drop_table("universe_rankings")
    op.drop_table("universe_ranking_runs")
