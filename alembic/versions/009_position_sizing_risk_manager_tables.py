"""Add position sizing and risk manager tables.

Revision ID: 009
Revises: 008
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_trade_classifications_trade_identity", "trade_classifications", type_="check")
    op.create_check_constraint(
        "ck_trade_classifications_trade_identity",
        "trade_classifications",
        "trade_identity IN ('core_holding', 'tactical_stock_trade', 'tactical_option_trade', 'risk_hedge_overlay', 'watch_only')",
    )
    op.drop_constraint("ck_candidate_outcome_evaluations_trade_identity", "candidate_outcome_evaluations", type_="check")
    op.create_check_constraint(
        "ck_candidate_outcome_evaluations_trade_identity",
        "candidate_outcome_evaluations",
        "trade_identity IN ('core_holding', 'tactical_stock_trade', 'tactical_option_trade', 'risk_hedge_overlay', 'watch_only')",
    )

    op.create_table(
        "position_sizing_decisions",
        sa.Column("position_sizing_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_score_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trade_classification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("risk_appetite", sa.String(length=32), nullable=False),
        sa.Column("base_weight", sa.Numeric(), nullable=False),
        sa.Column("volatility_adjusted_weight", sa.Numeric(), nullable=False),
        sa.Column("liquidity_capped_weight", sa.Numeric(), nullable=False),
        sa.Column("final_weight", sa.Numeric(), nullable=False),
        sa.Column("final_notional", sa.Numeric(), nullable=False),
        sa.Column("applied_caps_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("binding_constraint", sa.String(length=128), nullable=True),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "risk_appetite IN ('conservative', 'balanced', 'aggressive')",
            name="ck_position_sizing_decisions_risk_appetite",
        ),
        sa.CheckConstraint(
            "base_weight >= 0 AND base_weight <= 1 "
            "AND volatility_adjusted_weight >= 0 AND volatility_adjusted_weight <= 1 "
            "AND liquidity_capped_weight >= 0 AND liquidity_capped_weight <= 1 "
            "AND final_weight >= 0 AND final_weight <= 1",
            name="ck_position_sizing_decisions_weight_range",
        ),
        sa.ForeignKeyConstraint(["candidate_score_id"], ["candidate_scores.candidate_score_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trade_classification_id"], ["trade_classifications.trade_classification_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("position_sizing_decision_id"),
    )
    op.create_index("ix_position_sizing_decisions_candidate_score_id", "position_sizing_decisions", ["candidate_score_id"], unique=False)
    op.create_index("ix_position_sizing_decisions_decision_time", "position_sizing_decisions", ["decision_time"], unique=False)
    op.create_index("ix_position_sizing_decisions_risk_appetite", "position_sizing_decisions", ["risk_appetite"], unique=False)
    op.create_index("ix_position_sizing_decisions_ticker", "position_sizing_decisions", ["ticker"], unique=False)
    op.create_index("ix_position_sizing_decisions_trade_classification_id", "position_sizing_decisions", ["trade_classification_id"], unique=False)

    op.create_table(
        "portfolio_risk_snapshots",
        sa.Column("portfolio_risk_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_appetite", sa.String(length=32), nullable=False),
        sa.Column("resolver_version", sa.String(length=64), nullable=False),
        sa.Column("margin_model_profile", sa.String(length=128), nullable=False),
        sa.Column("margin_model_version", sa.String(length=32), nullable=False),
        sa.Column("account_equity", sa.Numeric(), nullable=False),
        sa.Column("cash_balance", sa.Numeric(), nullable=False),
        sa.Column("buying_power", sa.Numeric(), nullable=False),
        sa.Column("excess_liquidity", sa.Numeric(), nullable=False),
        sa.Column("stock_margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("option_margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("total_margin_requirement", sa.Numeric(), nullable=False),
        sa.Column("initial_margin_requirement", sa.Numeric(), nullable=True),
        sa.Column("maintenance_margin_requirement", sa.Numeric(), nullable=True),
        sa.Column("margin_requirement_source", sa.String(length=64), nullable=False),
        sa.Column("net_exposure", sa.Numeric(), nullable=False),
        sa.Column("gross_exposure", sa.Numeric(), nullable=False),
        sa.Column("beta_adjusted_net_exposure", sa.Numeric(), nullable=False),
        sa.Column("concentration_flags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "risk_appetite IN ('conservative', 'balanced', 'aggressive')",
            name="ck_portfolio_risk_snapshots_risk_appetite",
        ),
        sa.PrimaryKeyConstraint("portfolio_risk_snapshot_id"),
    )
    op.create_index("ix_portfolio_risk_snapshots_decision_time", "portfolio_risk_snapshots", ["decision_time"], unique=False)
    op.create_index("ix_portfolio_risk_snapshots_risk_appetite", "portfolio_risk_snapshots", ["risk_appetite"], unique=False)

    op.create_table(
        "risk_factor_exposures",
        sa.Column("risk_factor_exposure_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("portfolio_risk_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("factor_type", sa.String(length=64), nullable=False),
        sa.Column("factor_value", sa.String(length=128), nullable=False),
        sa.Column("gross_exposure", sa.Numeric(), nullable=False),
        sa.Column("net_exposure", sa.Numeric(), nullable=False),
        sa.Column("long_exposure", sa.Numeric(), nullable=False),
        sa.Column("short_exposure", sa.Numeric(), nullable=False),
        sa.Column("position_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("position_count >= 0", name="ck_risk_factor_exposures_position_count"),
        sa.ForeignKeyConstraint(
            ["portfolio_risk_snapshot_id"],
            ["portfolio_risk_snapshots.portfolio_risk_snapshot_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("risk_factor_exposure_id"),
    )
    op.create_index("ix_risk_factor_exposures_factor_type", "risk_factor_exposures", ["factor_type"], unique=False)
    op.create_index("ix_risk_factor_exposures_factor_value", "risk_factor_exposures", ["factor_value"], unique=False)
    op.create_index("ix_risk_factor_exposures_portfolio_risk_snapshot_id", "risk_factor_exposures", ["portfolio_risk_snapshot_id"], unique=False)
    op.create_index("ix_risk_factor_exposures_type_value", "risk_factor_exposures", ["factor_type", "factor_value"], unique=False)

    op.create_table(
        "risk_decisions",
        sa.Column("risk_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_score_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trade_classification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("position_sizing_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("portfolio_risk_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("approved_weight", sa.Numeric(), nullable=False),
        sa.Column("approved_notional", sa.Numeric(), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(), nullable=False),
        sa.Column("applied_rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_hedge_action_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('approved', 'reduced', 'rejected')", name="ck_risk_decisions_status"),
        sa.CheckConstraint("approved_weight >= 0 AND approved_weight <= 1", name="ck_risk_decisions_weight_range"),
        sa.ForeignKeyConstraint(["candidate_score_id"], ["candidate_scores.candidate_score_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["portfolio_risk_snapshot_id"], ["portfolio_risk_snapshots.portfolio_risk_snapshot_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["position_sizing_decision_id"], ["position_sizing_decisions.position_sizing_decision_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trade_classification_id"], ["trade_classifications.trade_classification_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("risk_decision_id"),
    )
    op.create_index("ix_risk_decisions_candidate_score_id", "risk_decisions", ["candidate_score_id"], unique=False)
    op.create_index("ix_risk_decisions_decision_time", "risk_decisions", ["decision_time"], unique=False)
    op.create_index("ix_risk_decisions_portfolio_risk_snapshot_id", "risk_decisions", ["portfolio_risk_snapshot_id"], unique=False)
    op.create_index("ix_risk_decisions_position_sizing_decision_id", "risk_decisions", ["position_sizing_decision_id"], unique=False)
    op.create_index("ix_risk_decisions_reason_code", "risk_decisions", ["reason_code"], unique=False)
    op.create_index("ix_risk_decisions_status", "risk_decisions", ["status"], unique=False)
    op.create_index("ix_risk_decisions_ticker", "risk_decisions", ["ticker"], unique=False)
    op.create_index("ix_risk_decisions_trade_classification_id", "risk_decisions", ["trade_classification_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_risk_decisions_trade_classification_id", table_name="risk_decisions")
    op.drop_index("ix_risk_decisions_ticker", table_name="risk_decisions")
    op.drop_index("ix_risk_decisions_status", table_name="risk_decisions")
    op.drop_index("ix_risk_decisions_reason_code", table_name="risk_decisions")
    op.drop_index("ix_risk_decisions_position_sizing_decision_id", table_name="risk_decisions")
    op.drop_index("ix_risk_decisions_portfolio_risk_snapshot_id", table_name="risk_decisions")
    op.drop_index("ix_risk_decisions_decision_time", table_name="risk_decisions")
    op.drop_index("ix_risk_decisions_candidate_score_id", table_name="risk_decisions")
    op.drop_table("risk_decisions")

    op.drop_index("ix_risk_factor_exposures_type_value", table_name="risk_factor_exposures")
    op.drop_index("ix_risk_factor_exposures_portfolio_risk_snapshot_id", table_name="risk_factor_exposures")
    op.drop_index("ix_risk_factor_exposures_factor_value", table_name="risk_factor_exposures")
    op.drop_index("ix_risk_factor_exposures_factor_type", table_name="risk_factor_exposures")
    op.drop_table("risk_factor_exposures")

    op.drop_index("ix_portfolio_risk_snapshots_risk_appetite", table_name="portfolio_risk_snapshots")
    op.drop_index("ix_portfolio_risk_snapshots_decision_time", table_name="portfolio_risk_snapshots")
    op.drop_table("portfolio_risk_snapshots")

    op.drop_index("ix_position_sizing_decisions_trade_classification_id", table_name="position_sizing_decisions")
    op.drop_index("ix_position_sizing_decisions_ticker", table_name="position_sizing_decisions")
    op.drop_index("ix_position_sizing_decisions_risk_appetite", table_name="position_sizing_decisions")
    op.drop_index("ix_position_sizing_decisions_decision_time", table_name="position_sizing_decisions")
    op.drop_index("ix_position_sizing_decisions_candidate_score_id", table_name="position_sizing_decisions")
    op.drop_table("position_sizing_decisions")

    op.drop_constraint("ck_candidate_outcome_evaluations_trade_identity", "candidate_outcome_evaluations", type_="check")
    op.create_check_constraint(
        "ck_candidate_outcome_evaluations_trade_identity",
        "candidate_outcome_evaluations",
        "trade_identity IN ('core_holding', 'tactical_stock_trade', 'tactical_option_trade', 'watch_only')",
    )
    op.drop_constraint("ck_trade_classifications_trade_identity", "trade_classifications", type_="check")
    op.create_check_constraint(
        "ck_trade_classifications_trade_identity",
        "trade_classifications",
        "trade_identity IN ('core_holding', 'tactical_stock_trade', 'tactical_option_trade', 'watch_only')",
    )
