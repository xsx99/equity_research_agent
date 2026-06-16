"""Add canonical macro, calendar, and event-risk contracts.

Revision ID: 022
Revises: 021
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.create_index("ix_macro_snapshots_regime", "macro_snapshots", ["regime"], unique=False)
    op.create_index("ix_macro_snapshots_snapshot_time", "macro_snapshots", ["snapshot_time"], unique=False)
    op.create_index("ix_macro_snapshots_trade_date", "macro_snapshots", ["trade_date"], unique=False)
    op.create_index(
        "ix_macro_snapshots_trade_date_snapshot_time",
        "macro_snapshots",
        ["trade_date", "snapshot_time"],
        unique=False,
    )

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
    op.create_index(
        "ix_macro_readthrough_events_available_for_decision_at",
        "macro_readthrough_events",
        ["available_for_decision_at"],
        unique=False,
    )
    op.create_index("ix_macro_readthrough_events_event_time", "macro_readthrough_events", ["event_time"], unique=False)
    op.create_index("ix_macro_readthrough_events_source_ticker", "macro_readthrough_events", ["source_ticker"], unique=False)
    op.create_index(
        "ix_macro_readthrough_events_ticker_available",
        "macro_readthrough_events",
        ["source_ticker", "available_for_decision_at"],
        unique=False,
    )

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
    op.create_index("ix_calendar_events_available_for_decision_at", "calendar_events", ["available_for_decision_at"], unique=False)
    op.create_index("ix_calendar_events_event_time", "calendar_events", ["event_time"], unique=False)
    op.create_index("ix_calendar_events_event_type", "calendar_events", ["event_type"], unique=False)
    op.create_index("ix_calendar_events_severity_hint", "calendar_events", ["severity_hint"], unique=False)
    op.create_index("ix_calendar_events_ticker", "calendar_events", ["ticker"], unique=False)
    op.create_index("ix_calendar_events_ticker_event_time", "calendar_events", ["ticker", "event_time"], unique=False)

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
    op.create_index(
        "ix_portfolio_event_risk_assessments_available_for_decision_at",
        "portfolio_event_risk_assessments",
        ["available_for_decision_at"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_event_risk_assessments_calendar_event_id",
        "portfolio_event_risk_assessments",
        ["calendar_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_event_risk_assessments_decision_time",
        "portfolio_event_risk_assessments",
        ["decision_time"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_event_risk_assessments_portfolio_risk_snapshot_id",
        "portfolio_event_risk_assessments",
        ["portfolio_risk_snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_event_risk_assessments_risk_source",
        "portfolio_event_risk_assessments",
        ["risk_source"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_event_risk_assessments_severity",
        "portfolio_event_risk_assessments",
        ["severity"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_event_risk_assessments_source_severity",
        "portfolio_event_risk_assessments",
        ["risk_source", "severity"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_event_risk_assessments_ticker",
        "portfolio_event_risk_assessments",
        ["ticker"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_event_risk_assessments_ticker_available",
        "portfolio_event_risk_assessments",
        ["ticker", "available_for_decision_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_event_risk_assessments_ticker_available",
        table_name="portfolio_event_risk_assessments",
    )
    op.drop_index("ix_portfolio_event_risk_assessments_ticker", table_name="portfolio_event_risk_assessments")
    op.drop_index(
        "ix_portfolio_event_risk_assessments_source_severity",
        table_name="portfolio_event_risk_assessments",
    )
    op.drop_index("ix_portfolio_event_risk_assessments_severity", table_name="portfolio_event_risk_assessments")
    op.drop_index("ix_portfolio_event_risk_assessments_risk_source", table_name="portfolio_event_risk_assessments")
    op.drop_index(
        "ix_portfolio_event_risk_assessments_portfolio_risk_snapshot_id",
        table_name="portfolio_event_risk_assessments",
    )
    op.drop_index("ix_portfolio_event_risk_assessments_decision_time", table_name="portfolio_event_risk_assessments")
    op.drop_index(
        "ix_portfolio_event_risk_assessments_calendar_event_id",
        table_name="portfolio_event_risk_assessments",
    )
    op.drop_index(
        "ix_portfolio_event_risk_assessments_available_for_decision_at",
        table_name="portfolio_event_risk_assessments",
    )
    op.drop_table("portfolio_event_risk_assessments")

    op.drop_index("ix_calendar_events_ticker_event_time", table_name="calendar_events")
    op.drop_index("ix_calendar_events_ticker", table_name="calendar_events")
    op.drop_index("ix_calendar_events_severity_hint", table_name="calendar_events")
    op.drop_index("ix_calendar_events_event_type", table_name="calendar_events")
    op.drop_index("ix_calendar_events_event_time", table_name="calendar_events")
    op.drop_index("ix_calendar_events_available_for_decision_at", table_name="calendar_events")
    op.drop_table("calendar_events")

    op.drop_index(
        "ix_macro_readthrough_events_ticker_available",
        table_name="macro_readthrough_events",
    )
    op.drop_index("ix_macro_readthrough_events_source_ticker", table_name="macro_readthrough_events")
    op.drop_index("ix_macro_readthrough_events_event_time", table_name="macro_readthrough_events")
    op.drop_index(
        "ix_macro_readthrough_events_available_for_decision_at",
        table_name="macro_readthrough_events",
    )
    op.drop_table("macro_readthrough_events")

    op.drop_index("ix_macro_snapshots_trade_date_snapshot_time", table_name="macro_snapshots")
    op.drop_index("ix_macro_snapshots_trade_date", table_name="macro_snapshots")
    op.drop_index("ix_macro_snapshots_snapshot_time", table_name="macro_snapshots")
    op.drop_index("ix_macro_snapshots_regime", table_name="macro_snapshots")
    op.drop_table("macro_snapshots")
