"""Add universe, provider telemetry, and signal MVP tables.

Revision ID: 007
Revises: 006
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "universe_filter_configs",
        sa.Column("universe_filter_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("min_price", sa.Numeric(), nullable=False),
        sa.Column("min_avg_dollar_volume", sa.Numeric(), nullable=False),
        sa.Column("included_sectors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("excluded_sectors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("included_industries_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("excluded_industries_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("exchanges_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("asset_types_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("manual_include_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("manual_exclude_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("min_price >= 0", name="ck_universe_filter_configs_min_price"),
        sa.CheckConstraint(
            "min_avg_dollar_volume >= 0",
            name="ck_universe_filter_configs_min_avg_dollar_volume",
        ),
        sa.PrimaryKeyConstraint("universe_filter_config_id"),
        sa.UniqueConstraint("profile_name", "version", name="uq_universe_filter_configs_profile_version"),
    )
    op.create_index("ix_universe_filter_configs_is_active", "universe_filter_configs", ["is_active"], unique=False)

    op.create_table(
        "universe_snapshots",
        sa.Column("universe_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("universe_filter_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("included_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("included_count >= 0", name="ck_universe_snapshots_included_count"),
        sa.CheckConstraint("excluded_count >= 0", name="ck_universe_snapshots_excluded_count"),
        sa.ForeignKeyConstraint(
            ["universe_filter_config_id"],
            ["universe_filter_configs.universe_filter_config_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("universe_snapshot_id"),
    )
    op.create_index("ix_universe_snapshots_date_provider", "universe_snapshots", ["snapshot_date", "provider"], unique=False)
    op.create_index("ix_universe_snapshots_snapshot_date", "universe_snapshots", ["snapshot_date"], unique=False)
    op.create_index("ix_universe_snapshots_universe_filter_config_id", "universe_snapshots", ["universe_filter_config_id"], unique=False)

    op.create_table(
        "universe_symbols",
        sa.Column("universe_symbol_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("universe_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("asset_type", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("price", sa.Numeric(), nullable=True),
        sa.Column("avg_dollar_volume", sa.Numeric(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('included', 'excluded')", name="ck_universe_symbols_status"),
        sa.ForeignKeyConstraint(
            ["universe_snapshot_id"],
            ["universe_snapshots.universe_snapshot_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("universe_symbol_id"),
        sa.UniqueConstraint("universe_snapshot_id", "symbol", name="uq_universe_symbols_snapshot_symbol"),
    )
    op.create_index("ix_universe_symbols_exclusion_reason", "universe_symbols", ["exclusion_reason"], unique=False)
    op.create_index("ix_universe_symbols_status", "universe_symbols", ["status"], unique=False)
    op.create_index("ix_universe_symbols_symbol", "universe_symbols", ["symbol"], unique=False)
    op.create_index("ix_universe_symbols_universe_snapshot_id", "universe_symbols", ["universe_snapshot_id"], unique=False)

    op.create_table(
        "source_ingestion_runs",
        sa.Column("source_ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_family", sa.String(length=64), nullable=False),
        sa.Column("run_type", sa.String(length=64), nullable=False),
        sa.Column("scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("coverage_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'degraded')",
            name="ck_source_ingestion_runs_status",
        ),
        sa.PrimaryKeyConstraint("source_ingestion_run_id"),
    )
    op.create_index("ix_source_ingestion_runs_family_status", "source_ingestion_runs", ["source_family", "status"], unique=False)
    op.create_index("ix_source_ingestion_runs_source_family", "source_ingestion_runs", ["source_family"], unique=False)
    op.create_index("ix_source_ingestion_runs_status", "source_ingestion_runs", ["status"], unique=False)

    op.create_table(
        "provider_request_runs",
        sa.Column("provider_request_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.String(length=128), nullable=False),
        sa.Column("source_family", sa.String(length=64), nullable=False),
        sa.Column("scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cache_status", sa.String(length=32), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("budget_remaining", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("backoff_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("circuit_state", sa.String(length=32), nullable=False),
        sa.Column("degraded_mode", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'cache_hit', 'budget_exceeded', 'circuit_open')",
            name="ck_provider_request_runs_status",
        ),
        sa.CheckConstraint("request_count >= 0", name="ck_provider_request_runs_request_count"),
        sa.CheckConstraint("budget_remaining >= 0", name="ck_provider_request_runs_budget_remaining"),
        sa.CheckConstraint("retry_count >= 0", name="ck_provider_request_runs_retry_count"),
        sa.CheckConstraint("backoff_ms >= 0", name="ck_provider_request_runs_backoff_ms"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_provider_request_runs_latency_ms"),
        sa.ForeignKeyConstraint(
            ["source_ingestion_run_id"],
            ["source_ingestion_runs.source_ingestion_run_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("provider_request_run_id"),
    )
    op.create_index("ix_provider_request_runs_endpoint", "provider_request_runs", ["endpoint"], unique=False)
    op.create_index("ix_provider_request_runs_provider", "provider_request_runs", ["provider"], unique=False)
    op.create_index("ix_provider_request_runs_provider_endpoint_status", "provider_request_runs", ["provider", "endpoint", "status"], unique=False)
    op.create_index("ix_provider_request_runs_source_family", "provider_request_runs", ["source_family"], unique=False)
    op.create_index("ix_provider_request_runs_source_ingestion_run_id", "provider_request_runs", ["source_ingestion_run_id"], unique=False)
    op.create_index("ix_provider_request_runs_status", "provider_request_runs", ["status"], unique=False)

    op.create_table(
        "fundamental_snapshots",
        sa.Column("fundamental_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("fiscal_period", sa.String(length=32), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("source_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload_ref", sa.String(length=255), nullable=True),
        sa.Column("normalized_metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("fundamental_snapshot_id"),
    )
    op.create_index("ix_fundamental_snapshots_as_of_date", "fundamental_snapshots", ["as_of_date"], unique=False)
    op.create_index("ix_fundamental_snapshots_available_for_decision_at", "fundamental_snapshots", ["available_for_decision_at"], unique=False)
    op.create_index("ix_fundamental_snapshots_ticker", "fundamental_snapshots", ["ticker"], unique=False)
    op.create_index("ix_fundamental_snapshots_ticker_available", "fundamental_snapshots", ["ticker", "available_for_decision_at"], unique=False)

    op.create_table(
        "event_news_items",
        sa.Column("event_news_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("source_ticker", sa.String(length=16), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=True),
        sa.Column("sentiment", sa.String(length=32), nullable=True),
        sa.Column("importance", sa.String(length=32), nullable=True),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("source_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload_ref", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("event_news_item_id"),
        sa.UniqueConstraint("dedupe_key", name="uq_event_news_items_dedupe_key"),
    )
    op.create_index("ix_event_news_items_available_for_decision_at", "event_news_items", ["available_for_decision_at"], unique=False)
    op.create_index("ix_event_news_items_event_type", "event_news_items", ["event_type"], unique=False)
    op.create_index("ix_event_news_items_importance", "event_news_items", ["importance"], unique=False)
    op.create_index("ix_event_news_items_source_ticker", "event_news_items", ["source_ticker"], unique=False)
    op.create_index("ix_event_news_items_ticker", "event_news_items", ["ticker"], unique=False)
    op.create_index("ix_event_news_items_ticker_available", "event_news_items", ["ticker", "available_for_decision_at"], unique=False)

    op.create_table(
        "signal_snapshots",
        sa.Column("signal_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("snapshot_type", sa.String(length=32), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_input_available_for_decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signal_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_freshness_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("missing_signals_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stale_signals_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_record_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_available_times_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("excluded_future_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("point_in_time_passed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("selection_source", sa.String(length=32), nullable=False, server_default="scanner"),
        sa.Column("manual_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("universe_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("snapshot_type IN ('pre_open', 'intraday')", name="ck_signal_snapshots_snapshot_type"),
        sa.CheckConstraint(
            "excluded_future_source_count >= 0",
            name="ck_signal_snapshots_excluded_future_source_count",
        ),
        sa.ForeignKeyConstraint(
            ["universe_snapshot_id"],
            ["universe_snapshots.universe_snapshot_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("signal_snapshot_id"),
    )
    op.create_index("ix_signal_snapshots_decision_time", "signal_snapshots", ["decision_time"], unique=False)
    op.create_index("ix_signal_snapshots_manual_request_id", "signal_snapshots", ["manual_request_id"], unique=False)
    op.create_index("ix_signal_snapshots_snapshot_type", "signal_snapshots", ["snapshot_type"], unique=False)
    op.create_index("ix_signal_snapshots_ticker", "signal_snapshots", ["ticker"], unique=False)
    op.create_index("ix_signal_snapshots_ticker_decision_type", "signal_snapshots", ["ticker", "decision_time", "snapshot_type"], unique=False)
    op.create_index("ix_signal_snapshots_universe_snapshot_id", "signal_snapshots", ["universe_snapshot_id"], unique=False)

    op.create_table(
        "manual_ticker_requests",
        sa.Column("manual_ticker_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_result_status", sa.String(length=64), nullable=True),
        sa.Column("latest_signal_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "mode IN ('review_only', 'paper_trade_eligible')",
            name="ck_manual_ticker_requests_mode",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'dismissed', 'cancelled')",
            name="ck_manual_ticker_requests_status",
        ),
        sa.ForeignKeyConstraint(
            ["latest_signal_snapshot_id"],
            ["signal_snapshots.signal_snapshot_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("manual_ticker_request_id"),
    )
    op.create_index("ix_manual_ticker_requests_latest_signal_snapshot_id", "manual_ticker_requests", ["latest_signal_snapshot_id"], unique=False)
    op.create_index("ix_manual_ticker_requests_status", "manual_ticker_requests", ["status"], unique=False)
    op.create_index("ix_manual_ticker_requests_ticker", "manual_ticker_requests", ["ticker"], unique=False)
    op.create_index("ix_manual_ticker_requests_ticker_status", "manual_ticker_requests", ["ticker", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_manual_ticker_requests_ticker_status", table_name="manual_ticker_requests")
    op.drop_index("ix_manual_ticker_requests_ticker", table_name="manual_ticker_requests")
    op.drop_index("ix_manual_ticker_requests_status", table_name="manual_ticker_requests")
    op.drop_index("ix_manual_ticker_requests_latest_signal_snapshot_id", table_name="manual_ticker_requests")
    op.drop_table("manual_ticker_requests")

    op.drop_index("ix_signal_snapshots_universe_snapshot_id", table_name="signal_snapshots")
    op.drop_index("ix_signal_snapshots_ticker_decision_type", table_name="signal_snapshots")
    op.drop_index("ix_signal_snapshots_ticker", table_name="signal_snapshots")
    op.drop_index("ix_signal_snapshots_snapshot_type", table_name="signal_snapshots")
    op.drop_index("ix_signal_snapshots_manual_request_id", table_name="signal_snapshots")
    op.drop_index("ix_signal_snapshots_decision_time", table_name="signal_snapshots")
    op.drop_table("signal_snapshots")

    op.drop_index("ix_event_news_items_ticker_available", table_name="event_news_items")
    op.drop_index("ix_event_news_items_ticker", table_name="event_news_items")
    op.drop_index("ix_event_news_items_source_ticker", table_name="event_news_items")
    op.drop_index("ix_event_news_items_importance", table_name="event_news_items")
    op.drop_index("ix_event_news_items_event_type", table_name="event_news_items")
    op.drop_index("ix_event_news_items_available_for_decision_at", table_name="event_news_items")
    op.drop_table("event_news_items")

    op.drop_index("ix_fundamental_snapshots_ticker_available", table_name="fundamental_snapshots")
    op.drop_index("ix_fundamental_snapshots_ticker", table_name="fundamental_snapshots")
    op.drop_index("ix_fundamental_snapshots_available_for_decision_at", table_name="fundamental_snapshots")
    op.drop_index("ix_fundamental_snapshots_as_of_date", table_name="fundamental_snapshots")
    op.drop_table("fundamental_snapshots")

    op.drop_index("ix_provider_request_runs_status", table_name="provider_request_runs")
    op.drop_index("ix_provider_request_runs_source_ingestion_run_id", table_name="provider_request_runs")
    op.drop_index("ix_provider_request_runs_source_family", table_name="provider_request_runs")
    op.drop_index("ix_provider_request_runs_provider_endpoint_status", table_name="provider_request_runs")
    op.drop_index("ix_provider_request_runs_provider", table_name="provider_request_runs")
    op.drop_index("ix_provider_request_runs_endpoint", table_name="provider_request_runs")
    op.drop_table("provider_request_runs")

    op.drop_index("ix_source_ingestion_runs_status", table_name="source_ingestion_runs")
    op.drop_index("ix_source_ingestion_runs_source_family", table_name="source_ingestion_runs")
    op.drop_index("ix_source_ingestion_runs_family_status", table_name="source_ingestion_runs")
    op.drop_table("source_ingestion_runs")

    op.drop_index("ix_universe_symbols_universe_snapshot_id", table_name="universe_symbols")
    op.drop_index("ix_universe_symbols_symbol", table_name="universe_symbols")
    op.drop_index("ix_universe_symbols_status", table_name="universe_symbols")
    op.drop_index("ix_universe_symbols_exclusion_reason", table_name="universe_symbols")
    op.drop_table("universe_symbols")

    op.drop_index("ix_universe_snapshots_universe_filter_config_id", table_name="universe_snapshots")
    op.drop_index("ix_universe_snapshots_snapshot_date", table_name="universe_snapshots")
    op.drop_index("ix_universe_snapshots_date_provider", table_name="universe_snapshots")
    op.drop_table("universe_snapshots")

    op.drop_index("ix_universe_filter_configs_is_active", table_name="universe_filter_configs")
    op.drop_table("universe_filter_configs")
