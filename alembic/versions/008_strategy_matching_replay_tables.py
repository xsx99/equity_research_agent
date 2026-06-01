"""Add strategy matching and replay tables.

Revision ID: 008
Revises: 007
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategy_runs",
        sa.Column("strategy_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("snapshot_type IN ('pre_open', 'intraday')", name="ck_strategy_runs_snapshot_type"),
        sa.CheckConstraint("status IN ('succeeded', 'failed')", name="ck_strategy_runs_status"),
        sa.PrimaryKeyConstraint("strategy_run_id"),
    )
    op.create_index("ix_strategy_runs_decision_time", "strategy_runs", ["decision_time"], unique=False)
    op.create_index("ix_strategy_runs_snapshot_type", "strategy_runs", ["snapshot_type"], unique=False)
    op.create_index("ix_strategy_runs_status", "strategy_runs", ["status"], unique=False)

    op.create_table(
        "candidate_scores",
        sa.Column("candidate_score_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=16), nullable=False),
        sa.Column("strategy_definition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_score", sa.Numeric(), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("typical_horizon", sa.String(length=32), nullable=False),
        sa.Column("core_signal_evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("missing_required_signals_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unsupported_missing_signal_families_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("invalidators_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk_tags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("macro_compatibility", sa.String(length=32), nullable=False),
        sa.Column("selection_source", sa.String(length=32), nullable=False),
        sa.Column("manual_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("selection_reason", sa.Text(), nullable=False),
        sa.Column("rejection_reason", sa.String(length=128), nullable=True),
        sa.Column("benchmark_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_record_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("candidate_score >= 0 AND candidate_score <= 1", name="ck_candidate_scores_score_range"),
        sa.CheckConstraint(
            "macro_compatibility IN ('allowed', 'reduced_size', 'blocked')",
            name="ck_candidate_scores_macro_compatibility",
        ),
        sa.CheckConstraint(
            "selection_source IN ('scanner', 'manual_request', 'watchlist_pin')",
            name="ck_candidate_scores_selection_source",
        ),
        sa.ForeignKeyConstraint(["signal_snapshot_id"], ["signal_snapshots.signal_snapshot_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["strategy_definition_id"], ["strategy_definitions.strategy_definition_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["strategy_run_id"], ["strategy_runs.strategy_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("candidate_score_id"),
        sa.UniqueConstraint("strategy_run_id", "ticker", "strategy_id", name="uq_candidate_scores_run_ticker_strategy"),
    )
    op.create_index("ix_candidate_scores_available_for_decision_at", "candidate_scores", ["available_for_decision_at"], unique=False)
    op.create_index("ix_candidate_scores_decision_time", "candidate_scores", ["decision_time"], unique=False)
    op.create_index("ix_candidate_scores_direction", "candidate_scores", ["direction"], unique=False)
    op.create_index("ix_candidate_scores_macro_compatibility", "candidate_scores", ["macro_compatibility"], unique=False)
    op.create_index("ix_candidate_scores_manual_request_id", "candidate_scores", ["manual_request_id"], unique=False)
    op.create_index("ix_candidate_scores_rejection_reason", "candidate_scores", ["rejection_reason"], unique=False)
    op.create_index("ix_candidate_scores_run_score", "candidate_scores", ["strategy_run_id", "candidate_score"], unique=False)
    op.create_index("ix_candidate_scores_selection_source", "candidate_scores", ["selection_source"], unique=False)
    op.create_index("ix_candidate_scores_signal_snapshot_id", "candidate_scores", ["signal_snapshot_id"], unique=False)
    op.create_index("ix_candidate_scores_strategy_definition_id", "candidate_scores", ["strategy_definition_id"], unique=False)
    op.create_index("ix_candidate_scores_strategy_id", "candidate_scores", ["strategy_id"], unique=False)
    op.create_index("ix_candidate_scores_strategy_run_id", "candidate_scores", ["strategy_run_id"], unique=False)
    op.create_index("ix_candidate_scores_ticker", "candidate_scores", ["ticker"], unique=False)
    op.create_index("ix_candidate_scores_ticker_strategy", "candidate_scores", ["ticker", "strategy_id"], unique=False)

    op.create_table(
        "trade_classifications",
        sa.Column("trade_classification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_score_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("selected_strategy_id", sa.String(length=64), nullable=False),
        sa.Column("selected_strategy_version", sa.String(length=16), nullable=False),
        sa.Column("expression_bucket_id", sa.String(length=64), nullable=False),
        sa.Column("expression_bucket_version", sa.String(length=16), nullable=False),
        sa.Column("trade_identity", sa.String(length=64), nullable=False),
        sa.Column("watch_type", sa.String(length=64), nullable=True),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("intended_horizon", sa.String(length=32), nullable=False),
        sa.Column("exit_policy", sa.String(length=128), nullable=False),
        sa.Column("result_status", sa.String(length=64), nullable=False),
        sa.Column("classification_reason", sa.Text(), nullable=False),
        sa.Column("selected_strategy_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "trade_identity IN ('core_holding', 'tactical_stock_trade', 'tactical_option_trade', 'watch_only')",
            name="ck_trade_classifications_trade_identity",
        ),
        sa.CheckConstraint(
            "watch_type IS NULL OR watch_type IN ('catalyst_watch', 'ordinary_watch')",
            name="ck_trade_classifications_watch_type",
        ),
        sa.ForeignKeyConstraint(["candidate_score_id"], ["candidate_scores.candidate_score_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strategy_run_id"], ["strategy_runs.strategy_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("trade_classification_id"),
    )
    op.create_index("ix_trade_classifications_candidate_score_id", "trade_classifications", ["candidate_score_id"], unique=False)
    op.create_index("ix_trade_classifications_decision_time", "trade_classifications", ["decision_time"], unique=False)
    op.create_index("ix_trade_classifications_direction", "trade_classifications", ["direction"], unique=False)
    op.create_index("ix_trade_classifications_expression_bucket_id", "trade_classifications", ["expression_bucket_id"], unique=False)
    op.create_index("ix_trade_classifications_result_status", "trade_classifications", ["result_status"], unique=False)
    op.create_index("ix_trade_classifications_selected_strategy_id", "trade_classifications", ["selected_strategy_id"], unique=False)
    op.create_index("ix_trade_classifications_strategy_run_id", "trade_classifications", ["strategy_run_id"], unique=False)
    op.create_index("ix_trade_classifications_ticker", "trade_classifications", ["ticker"], unique=False)
    op.create_index("ix_trade_classifications_ticker_strategy", "trade_classifications", ["ticker", "selected_strategy_id"], unique=False)
    op.create_index("ix_trade_classifications_trade_identity", "trade_classifications", ["trade_identity"], unique=False)
    op.create_index("ix_trade_classifications_watch_type", "trade_classifications", ["watch_type"], unique=False)

    op.create_table(
        "historical_replay_runs",
        sa.Column("historical_replay_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_filter_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("outcome_horizon_policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("snapshot_type IN ('pre_open', 'intraday')", name="ck_historical_replay_runs_snapshot_type"),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="ck_historical_replay_runs_status"),
        sa.PrimaryKeyConstraint("historical_replay_run_id"),
    )
    op.create_index("ix_historical_replay_runs_decision_time", "historical_replay_runs", ["decision_time"], unique=False)
    op.create_index("ix_historical_replay_runs_snapshot_type", "historical_replay_runs", ["snapshot_type"], unique=False)
    op.create_index("ix_historical_replay_runs_status", "historical_replay_runs", ["status"], unique=False)

    op.create_table(
        "candidate_outcome_evaluations",
        sa.Column("candidate_outcome_evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("historical_replay_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_score_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trade_classification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=16), nullable=False),
        sa.Column("expression_bucket_id", sa.String(length=64), nullable=False),
        sa.Column("trade_identity", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("catalyst_type", sa.String(length=128), nullable=True),
        sa.Column("confidence_bucket", sa.String(length=255), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluation_status", sa.String(length=32), nullable=False),
        sa.Column("candidate_return", sa.Numeric(), nullable=True),
        sa.Column("benchmark_returns_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("peer_basket_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("peer_basket_return", sa.Numeric(), nullable=True),
        sa.Column("alpha", sa.Numeric(), nullable=True),
        sa.Column("max_favorable_excursion", sa.Numeric(), nullable=True),
        sa.Column("max_adverse_excursion", sa.Numeric(), nullable=True),
        sa.Column("regime", sa.String(length=64), nullable=True),
        sa.Column("sector_theme", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "trade_identity IN ('core_holding', 'tactical_stock_trade', 'tactical_option_trade', 'watch_only')",
            name="ck_candidate_outcome_evaluations_trade_identity",
        ),
        sa.CheckConstraint(
            "evaluation_status IN ('interim', 'final')",
            name="ck_candidate_outcome_evaluations_status",
        ),
        sa.CheckConstraint(
            "horizon_end_at >= horizon_start_at",
            name="ck_candidate_outcome_evaluations_horizon_window",
        ),
        sa.ForeignKeyConstraint(["candidate_score_id"], ["candidate_scores.candidate_score_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["historical_replay_run_id"], ["historical_replay_runs.historical_replay_run_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["peer_basket_id"], ["peer_baskets.peer_basket_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trade_classification_id"], ["trade_classifications.trade_classification_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("candidate_outcome_evaluation_id"),
    )
    op.create_index("ix_candidate_outcome_evaluations_candidate_score_id", "candidate_outcome_evaluations", ["candidate_score_id"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_catalyst_type", "candidate_outcome_evaluations", ["catalyst_type"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_confidence_bucket", "candidate_outcome_evaluations", ["confidence_bucket"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_decision_time", "candidate_outcome_evaluations", ["decision_time"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_direction", "candidate_outcome_evaluations", ["direction"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_evaluation_status", "candidate_outcome_evaluations", ["evaluation_status"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_expression_bucket_id", "candidate_outcome_evaluations", ["expression_bucket_id"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_historical_replay_run_id", "candidate_outcome_evaluations", ["historical_replay_run_id"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_horizon_end_at", "candidate_outcome_evaluations", ["horizon_end_at"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_peer_basket_id", "candidate_outcome_evaluations", ["peer_basket_id"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_regime", "candidate_outcome_evaluations", ["regime"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_sector_theme", "candidate_outcome_evaluations", ["sector_theme"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_strategy_id", "candidate_outcome_evaluations", ["strategy_id"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_ticker", "candidate_outcome_evaluations", ["ticker"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_trade_classification_id", "candidate_outcome_evaluations", ["trade_classification_id"], unique=False)
    op.create_index("ix_candidate_outcome_evaluations_trade_identity", "candidate_outcome_evaluations", ["trade_identity"], unique=False)
    op.create_index("ix_candidate_outcomes_strategy_bucket", "candidate_outcome_evaluations", ["strategy_id", "confidence_bucket"], unique=False)
    op.create_index("ix_candidate_outcomes_ticker_horizon", "candidate_outcome_evaluations", ["ticker", "horizon_end_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_candidate_outcomes_ticker_horizon", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcomes_strategy_bucket", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_trade_identity", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_trade_classification_id", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_ticker", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_strategy_id", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_sector_theme", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_regime", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_peer_basket_id", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_horizon_end_at", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_historical_replay_run_id", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_expression_bucket_id", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_evaluation_status", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_direction", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_decision_time", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_confidence_bucket", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_catalyst_type", table_name="candidate_outcome_evaluations")
    op.drop_index("ix_candidate_outcome_evaluations_candidate_score_id", table_name="candidate_outcome_evaluations")
    op.drop_table("candidate_outcome_evaluations")

    op.drop_index("ix_historical_replay_runs_status", table_name="historical_replay_runs")
    op.drop_index("ix_historical_replay_runs_snapshot_type", table_name="historical_replay_runs")
    op.drop_index("ix_historical_replay_runs_decision_time", table_name="historical_replay_runs")
    op.drop_table("historical_replay_runs")

    op.drop_index("ix_trade_classifications_watch_type", table_name="trade_classifications")
    op.drop_index("ix_trade_classifications_trade_identity", table_name="trade_classifications")
    op.drop_index("ix_trade_classifications_ticker_strategy", table_name="trade_classifications")
    op.drop_index("ix_trade_classifications_ticker", table_name="trade_classifications")
    op.drop_index("ix_trade_classifications_strategy_run_id", table_name="trade_classifications")
    op.drop_index("ix_trade_classifications_selected_strategy_id", table_name="trade_classifications")
    op.drop_index("ix_trade_classifications_result_status", table_name="trade_classifications")
    op.drop_index("ix_trade_classifications_expression_bucket_id", table_name="trade_classifications")
    op.drop_index("ix_trade_classifications_direction", table_name="trade_classifications")
    op.drop_index("ix_trade_classifications_decision_time", table_name="trade_classifications")
    op.drop_index("ix_trade_classifications_candidate_score_id", table_name="trade_classifications")
    op.drop_table("trade_classifications")

    op.drop_index("ix_candidate_scores_ticker_strategy", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_ticker", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_strategy_run_id", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_strategy_id", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_strategy_definition_id", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_signal_snapshot_id", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_selection_source", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_run_score", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_rejection_reason", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_manual_request_id", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_macro_compatibility", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_direction", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_decision_time", table_name="candidate_scores")
    op.drop_index("ix_candidate_scores_available_for_decision_at", table_name="candidate_scores")
    op.drop_table("candidate_scores")

    op.drop_index("ix_strategy_runs_status", table_name="strategy_runs")
    op.drop_index("ix_strategy_runs_snapshot_type", table_name="strategy_runs")
    op.drop_index("ix_strategy_runs_decision_time", table_name="strategy_runs")
    op.drop_table("strategy_runs")
