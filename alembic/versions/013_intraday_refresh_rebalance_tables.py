"""Add PR8 intraday refresh, alerts, and rebalance tables.

Revision ID: 013
Revises: 012
Create Date: 2026-06-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intraday_signal_scans",
        sa.Column("intraday_signal_scan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("coverage_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("intraday_signal_scan_id"),
    )
    op.create_index("ix_intraday_signal_scans_decision_time", "intraday_signal_scans", ["decision_time"], unique=False)
    op.create_index("ix_intraday_signal_scans_status", "intraday_signal_scans", ["status"], unique=False)

    op.create_table(
        "intraday_signal_snapshots",
        sa.Column("intraday_signal_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intraday_signal_scan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_signal_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("previous_intraday_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("refreshed_signals_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("carried_forward_signals_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("delta_vs_baseline_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("delta_vs_previous_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_freshness_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["intraday_signal_scan_id"], ["intraday_signal_scans.intraday_signal_scan_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["baseline_signal_snapshot_id"], ["signal_snapshots.signal_snapshot_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["previous_intraday_snapshot_id"], ["intraday_signal_snapshots.intraday_signal_snapshot_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("intraday_signal_snapshot_id"),
    )
    op.create_index("ix_intraday_signal_snapshots_intraday_signal_scan_id", "intraday_signal_snapshots", ["intraday_signal_scan_id"], unique=False)
    op.create_index("ix_intraday_signal_snapshots_ticker", "intraday_signal_snapshots", ["ticker"], unique=False)
    op.create_index("ix_intraday_signal_snapshots_decision_time", "intraday_signal_snapshots", ["decision_time"], unique=False)
    op.create_index("ix_intraday_signal_snapshots_baseline_signal_snapshot_id", "intraday_signal_snapshots", ["baseline_signal_snapshot_id"], unique=False)
    op.create_index("ix_intraday_signal_snapshots_previous_intraday_snapshot_id", "intraday_signal_snapshots", ["previous_intraday_snapshot_id"], unique=False)

    op.create_table(
        "news_alerts",
        sa.Column("news_alert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("source_ticker", sa.String(length=16), nullable=True),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("sentiment", sa.String(length=16), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("strategy_relevance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("affected_positions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("affected_candidates_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("affected_themes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("readthrough_source_ticker", sa.String(length=16), nullable=True),
        sa.Column("action_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("event_news_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["event_news_item_id"], ["event_news_items.event_news_item_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("news_alert_id"),
        sa.UniqueConstraint("dedupe_key", name="uq_news_alerts_dedupe_key"),
    )
    op.create_index("ix_news_alerts_ticker", "news_alerts", ["ticker"], unique=False)
    op.create_index("ix_news_alerts_source_ticker", "news_alerts", ["source_ticker"], unique=False)
    op.create_index("ix_news_alerts_alert_type", "news_alerts", ["alert_type"], unique=False)
    op.create_index("ix_news_alerts_sentiment", "news_alerts", ["sentiment"], unique=False)
    op.create_index("ix_news_alerts_severity", "news_alerts", ["severity"], unique=False)
    op.create_index("ix_news_alerts_source", "news_alerts", ["source"], unique=False)
    op.create_index("ix_news_alerts_published_at", "news_alerts", ["published_at"], unique=False)
    op.create_index("ix_news_alerts_dedupe_key", "news_alerts", ["dedupe_key"], unique=True)
    op.create_index("ix_news_alerts_event_news_item_id", "news_alerts", ["event_news_item_id"], unique=False)

    op.create_table(
        "intraday_rebalance_decisions",
        sa.Column("intraday_rebalance_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("target_weight", sa.Numeric(), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("urgency", sa.String(length=16), nullable=False),
        sa.Column("rationale_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["risk_decision_id"], ["risk_decisions.risk_decision_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("intraday_rebalance_decision_id"),
    )
    op.create_index("ix_intraday_rebalance_decisions_ticker", "intraday_rebalance_decisions", ["ticker"], unique=False)
    op.create_index("ix_intraday_rebalance_decisions_action", "intraday_rebalance_decisions", ["action"], unique=False)
    op.create_index("ix_intraday_rebalance_decisions_status", "intraday_rebalance_decisions", ["status"], unique=False)
    op.create_index("ix_intraday_rebalance_decisions_reason_code", "intraday_rebalance_decisions", ["reason_code"], unique=False)
    op.create_index("ix_intraday_rebalance_decisions_urgency", "intraday_rebalance_decisions", ["urgency"], unique=False)
    op.create_index("ix_intraday_rebalance_decisions_available_for_decision_at", "intraday_rebalance_decisions", ["available_for_decision_at"], unique=False)
    op.create_index("ix_intraday_rebalance_decisions_decision_time", "intraday_rebalance_decisions", ["decision_time"], unique=False)
    op.create_index("ix_intraday_rebalance_decisions_risk_decision_id", "intraday_rebalance_decisions", ["risk_decision_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_intraday_rebalance_decisions_risk_decision_id", table_name="intraday_rebalance_decisions")
    op.drop_index("ix_intraday_rebalance_decisions_decision_time", table_name="intraday_rebalance_decisions")
    op.drop_index("ix_intraday_rebalance_decisions_available_for_decision_at", table_name="intraday_rebalance_decisions")
    op.drop_index("ix_intraday_rebalance_decisions_urgency", table_name="intraday_rebalance_decisions")
    op.drop_index("ix_intraday_rebalance_decisions_reason_code", table_name="intraday_rebalance_decisions")
    op.drop_index("ix_intraday_rebalance_decisions_status", table_name="intraday_rebalance_decisions")
    op.drop_index("ix_intraday_rebalance_decisions_action", table_name="intraday_rebalance_decisions")
    op.drop_index("ix_intraday_rebalance_decisions_ticker", table_name="intraday_rebalance_decisions")
    op.drop_table("intraday_rebalance_decisions")

    op.drop_index("ix_news_alerts_event_news_item_id", table_name="news_alerts")
    op.drop_index("ix_news_alerts_dedupe_key", table_name="news_alerts")
    op.drop_index("ix_news_alerts_published_at", table_name="news_alerts")
    op.drop_index("ix_news_alerts_source", table_name="news_alerts")
    op.drop_index("ix_news_alerts_severity", table_name="news_alerts")
    op.drop_index("ix_news_alerts_sentiment", table_name="news_alerts")
    op.drop_index("ix_news_alerts_alert_type", table_name="news_alerts")
    op.drop_index("ix_news_alerts_source_ticker", table_name="news_alerts")
    op.drop_index("ix_news_alerts_ticker", table_name="news_alerts")
    op.drop_table("news_alerts")

    op.drop_index("ix_intraday_signal_snapshots_previous_intraday_snapshot_id", table_name="intraday_signal_snapshots")
    op.drop_index("ix_intraday_signal_snapshots_baseline_signal_snapshot_id", table_name="intraday_signal_snapshots")
    op.drop_index("ix_intraday_signal_snapshots_decision_time", table_name="intraday_signal_snapshots")
    op.drop_index("ix_intraday_signal_snapshots_ticker", table_name="intraday_signal_snapshots")
    op.drop_index("ix_intraday_signal_snapshots_intraday_signal_scan_id", table_name="intraday_signal_snapshots")
    op.drop_table("intraday_signal_snapshots")

    op.drop_index("ix_intraday_signal_scans_status", table_name="intraday_signal_scans")
    op.drop_index("ix_intraday_signal_scans_decision_time", table_name="intraday_signal_scans")
    op.drop_table("intraday_signal_scans")
