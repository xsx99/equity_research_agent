"""Backfill canonical macro/event tables for databases upgraded before 022 was linked.

Revision ID: 025
Revises: 024
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("macro_snapshots"):
        op.create_table(
            "macro_snapshots",
            sa.Column("macro_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("trade_date", sa.Date(), nullable=False),
            sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("regime", sa.String(length=32), nullable=False),
            sa.Column("risk_budget_multiplier", sa.Numeric(), nullable=False),
            sa.Column("volatility_state", sa.String(length=32), nullable=True),
            sa.Column("rates_state", sa.String(length=32), nullable=True),
            sa.Column("liquidity_state", sa.String(length=32), nullable=True),
            sa.Column("source_set_key", sa.String(length=255), nullable=False),
            sa.Column(
                "blocked_strategy_tags_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "invalidators_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "source_freshness_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "metadata_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("macro_snapshot_id"),
            sa.UniqueConstraint(
                "trade_date",
                "snapshot_time",
                "source_set_key",
                name="uq_macro_snapshots_trade_date_snapshot_time_source_set_key",
            ),
        )
    _ensure_index("macro_snapshots", "ix_macro_snapshots_regime", ["regime"])
    _ensure_index("macro_snapshots", "ix_macro_snapshots_snapshot_time", ["snapshot_time"])
    _ensure_index("macro_snapshots", "ix_macro_snapshots_trade_date", ["trade_date"])
    _ensure_index(
        "macro_snapshots",
        "ix_macro_snapshots_trade_date_snapshot_time",
        ["trade_date", "snapshot_time"],
    )

    if not inspector.has_table("macro_readthrough_events"):
        op.create_table(
            "macro_readthrough_events",
            sa.Column("macro_readthrough_event_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("event_key", sa.String(length=255), nullable=False),
            sa.Column("source_ticker", sa.String(length=16), nullable=False),
            sa.Column("affected_ticker", sa.String(length=16), nullable=True),
            sa.Column("scope", sa.String(length=64), nullable=False),
            sa.Column("mechanism", sa.String(length=64), nullable=False),
            sa.Column("direction", sa.String(length=32), nullable=True),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "metadata_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("macro_readthrough_event_id"),
            sa.UniqueConstraint("event_key", name="uq_macro_readthrough_events_event_key"),
        )
    _ensure_index(
        "macro_readthrough_events",
        "ix_macro_readthrough_events_available_for_decision_at",
        ["available_for_decision_at"],
    )
    _ensure_index(
        "macro_readthrough_events",
        "ix_macro_readthrough_events_event_time",
        ["event_time"],
    )
    _ensure_index(
        "macro_readthrough_events",
        "ix_macro_readthrough_events_source_ticker",
        ["source_ticker"],
    )
    _ensure_index(
        "macro_readthrough_events",
        "ix_macro_readthrough_events_ticker_available",
        ["source_ticker", "available_for_decision_at"],
    )

    if not inspector.has_table("calendar_events"):
        op.create_table(
            "calendar_events",
            sa.Column("calendar_event_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("event_key", sa.String(length=255), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=True),
            sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("severity_hint", sa.String(length=32), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column(
                "metadata_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("calendar_event_id"),
            sa.UniqueConstraint("event_key", name="uq_calendar_events_event_key"),
        )
    _ensure_index(
        "calendar_events",
        "ix_calendar_events_available_for_decision_at",
        ["available_for_decision_at"],
    )
    _ensure_index("calendar_events", "ix_calendar_events_event_time", ["event_time"])
    _ensure_index("calendar_events", "ix_calendar_events_event_type", ["event_type"])
    _ensure_index("calendar_events", "ix_calendar_events_severity_hint", ["severity_hint"])
    _ensure_index("calendar_events", "ix_calendar_events_ticker", ["ticker"])
    _ensure_index("calendar_events", "ix_calendar_events_ticker_event_time", ["ticker", "event_time"])

    if not inspector.has_table("portfolio_event_risk_assessments"):
        op.create_table(
            "portfolio_event_risk_assessments",
            sa.Column("portfolio_event_risk_assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("assessment_key", sa.String(length=255), nullable=False),
            sa.Column("calendar_event_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("portfolio_risk_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("decision_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("risk_source", sa.String(length=64), nullable=False),
            sa.Column("severity", sa.String(length=32), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=True),
            sa.Column("days_until_event", sa.Integer(), nullable=True),
            sa.Column("affects_existing_position", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("affects_pending_trade", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("recommended_action", sa.String(length=64), nullable=False, server_default="monitor"),
            sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "metadata_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["calendar_event_id"], ["calendar_events.calendar_event_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["portfolio_risk_snapshot_id"],
                ["portfolio_risk_snapshots.portfolio_risk_snapshot_id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("portfolio_event_risk_assessment_id"),
            sa.UniqueConstraint("assessment_key", name="uq_portfolio_event_risk_assessments_assessment_key"),
        )
    _ensure_index(
        "portfolio_event_risk_assessments",
        "ix_portfolio_event_risk_assessments_available_for_decision_at",
        ["available_for_decision_at"],
    )
    _ensure_index(
        "portfolio_event_risk_assessments",
        "ix_portfolio_event_risk_assessments_calendar_event_id",
        ["calendar_event_id"],
    )
    _ensure_index(
        "portfolio_event_risk_assessments",
        "ix_portfolio_event_risk_assessments_decision_time",
        ["decision_time"],
    )
    _ensure_index(
        "portfolio_event_risk_assessments",
        "ix_portfolio_event_risk_assessments_portfolio_risk_snapshot_id",
        ["portfolio_risk_snapshot_id"],
    )
    _ensure_index(
        "portfolio_event_risk_assessments",
        "ix_portfolio_event_risk_assessments_risk_source",
        ["risk_source"],
    )
    _ensure_index(
        "portfolio_event_risk_assessments",
        "ix_portfolio_event_risk_assessments_severity",
        ["severity"],
    )
    _ensure_index(
        "portfolio_event_risk_assessments",
        "ix_portfolio_event_risk_assessments_source_severity",
        ["risk_source", "severity"],
    )
    _ensure_index(
        "portfolio_event_risk_assessments",
        "ix_portfolio_event_risk_assessments_ticker",
        ["ticker"],
    )
    _ensure_index(
        "portfolio_event_risk_assessments",
        "ix_portfolio_event_risk_assessments_ticker_available",
        ["ticker", "available_for_decision_at"],
    )


def downgrade() -> None:
    return None


def _ensure_index(table_name: str, index_name: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing_indexes:
        op.create_index(index_name, table_name, columns, unique=False)
