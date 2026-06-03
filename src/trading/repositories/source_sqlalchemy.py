"""SQL-backed source artifact persistence and point-in-time reads."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from src.db.models.trading import EventNewsItem, FundamentalSnapshot, ProviderRequestRun, SourceIngestionRun
from src.trading.data_sources.provider_resilience import ProviderRequestRunRecord
from src.trading.signals.sources import (
    EventNewsItemRecord,
    FundamentalSnapshotRecord,
    SourceIngestionRunRecord,
    SourceRecord,
    source_record_from_event_news_item,
    source_record_from_fundamental_snapshot,
)


class SQLAlchemySignalSourceRepository:
    """Persist normalized source artifacts and rebuild PIT source rows."""

    def __init__(self, session: Any) -> None:
        self.session = session

    def add(self, *records: SourceRecord) -> None:
        """SourceIngestionService compatibility hook.

        Normalized source rows are persisted through dedicated table methods below.
        The live SQL adapter does not need an extra catch-all source table.
        """

    def record_source_ingestion_run(self, run: SourceIngestionRunRecord) -> None:
        row = self.session.query(SourceIngestionRun).filter_by(
            source_ingestion_run_id=_to_uuid(run.source_ingestion_run_id)
        ).one_or_none()
        if row is None:
            row = SourceIngestionRun(source_ingestion_run_id=_to_uuid(run.source_ingestion_run_id))
            self.session.add(row)
        row.source_family = run.source_family
        row.run_type = run.run_type
        row.scope_json = dict(run.scope_json)
        row.provider = run.provider
        row.as_of = run.as_of
        row.started_at = run.started_at
        row.completed_at = run.completed_at
        row.status = run.status
        row.coverage_json = dict(run.coverage_json)
        row.error_code = run.error_code
        row.error_message = run.error_message
        row.metadata_json = dict(run.metadata_json)
        self.session.flush()

    def record_provider_request(self, run: ProviderRequestRunRecord) -> None:
        row_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{run.provider}:{run.endpoint}:{run.scope}:{run.started_at.isoformat()}",
        )
        row = self.session.query(ProviderRequestRun).filter_by(
            provider_request_run_id=row_id
        ).one_or_none()
        if row is None:
            row = ProviderRequestRun(provider_request_run_id=row_id)
            self.session.add(row)
        row.source_ingestion_run_id = _to_uuid_or_none(getattr(run, "source_ingestion_run_id", None))
        row.provider = run.provider
        row.endpoint = run.endpoint
        row.source_family = run.source_family
        row.scope_json = {"scope": run.scope}
        row.cache_status = run.cache_status
        row.request_count = int(run.request_count)
        row.budget_remaining = int(run.budget_remaining)
        row.retry_count = int(run.retry_count)
        row.backoff_ms = int(run.backoff_ms)
        row.latency_ms = int(run.latency_ms)
        row.status = run.status
        row.error_code = run.error_code
        row.circuit_state = run.circuit_state
        row.degraded_mode = bool(run.degraded_mode)
        row.started_at = run.started_at
        row.completed_at = run.completed_at
        row.metadata_json = {}
        self.session.flush()

    def save_fundamental_snapshot(self, snapshot: FundamentalSnapshotRecord) -> None:
        row = self.session.query(FundamentalSnapshot).filter_by(
            fundamental_snapshot_id=_to_uuid(snapshot.fundamental_snapshot_id)
        ).one_or_none()
        if row is None:
            row = FundamentalSnapshot(fundamental_snapshot_id=_to_uuid(snapshot.fundamental_snapshot_id))
            self.session.add(row)
        row.ticker = snapshot.ticker
        row.fiscal_period = snapshot.fiscal_period
        row.as_of_date = snapshot.as_of_date
        row.provider = snapshot.provider
        row.source_refs_json = list(snapshot.source_refs_json)
        row.event_time = snapshot.event_time
        row.published_at = snapshot.published_at
        row.ingested_at = snapshot.ingested_at
        row.available_for_decision_at = snapshot.available_for_decision_at
        row.raw_payload_ref = snapshot.raw_payload_ref
        row.normalized_metrics_json = dict(snapshot.normalized_metrics_json)
        self.session.flush()

    def save_event_news_item(self, item: EventNewsItemRecord) -> None:
        row = self.session.query(EventNewsItem).filter_by(
            event_news_item_id=_to_uuid(item.event_news_item_id)
        ).one_or_none()
        if row is None:
            row = EventNewsItem(event_news_item_id=_to_uuid(item.event_news_item_id))
            self.session.add(row)
        row.ticker = item.ticker
        row.source_ticker = item.source_ticker
        row.event_type = item.event_type
        row.direction = item.direction
        row.sentiment = item.sentiment
        row.importance = item.importance
        row.headline = item.headline
        row.summary = item.summary
        row.provider = item.provider
        row.source_refs_json = list(item.source_refs_json)
        row.dedupe_key = item.dedupe_key
        row.event_time = item.event_time
        row.published_at = item.published_at
        row.ingested_at = item.ingested_at
        row.available_for_decision_at = item.available_for_decision_at
        row.raw_payload_ref = item.raw_payload_ref
        row.metadata_json = dict(item.metadata_json)
        self.session.flush()

    def records_for_ticker(self, ticker: str) -> tuple[SourceRecord, ...]:
        symbol = ticker.strip().upper()
        records = [
            source_record_from_fundamental_snapshot(self._to_fundamental_record(row))
            for row in self.session.query(FundamentalSnapshot).filter_by(ticker=symbol).all()
        ]
        records.extend(
            source_record_from_event_news_item(self._to_event_news_record(row))
            for row in self.session.query(EventNewsItem).filter_by(ticker=symbol).all()
        )
        return tuple(sorted(records, key=lambda record: record.available_for_decision_at))

    def available_records(
        self,
        ticker: str,
        decision_time: datetime,
        *,
        source_family: str | None = None,
    ) -> tuple[SourceRecord, ...]:
        return tuple(
            record
            for record in self.records_for_ticker(ticker)
            if record.available_for_decision_at <= decision_time
            and (source_family is None or record.source_family == source_family)
        )

    def latest_available_by_family(
        self,
        ticker: str,
        source_family: str,
        decision_time: datetime,
    ) -> tuple[SourceRecord, ...]:
        records = self.available_records(ticker, decision_time, source_family=source_family)
        if not records:
            return ()
        latest = max(record.available_for_decision_at for record in records)
        return tuple(record for record in records if record.available_for_decision_at == latest)

    def _to_fundamental_record(self, row: FundamentalSnapshot) -> FundamentalSnapshotRecord:
        return FundamentalSnapshotRecord(
            fundamental_snapshot_id=str(row.fundamental_snapshot_id),
            ticker=row.ticker,
            fiscal_period=row.fiscal_period,
            as_of_date=row.as_of_date,
            provider=row.provider,
            source_refs_json=list(row.source_refs_json or []),
            event_time=row.event_time,
            published_at=row.published_at,
            ingested_at=row.ingested_at,
            available_for_decision_at=row.available_for_decision_at,
            raw_payload_ref=row.raw_payload_ref,
            normalized_metrics_json=dict(row.normalized_metrics_json or {}),
        )

    def _to_event_news_record(self, row: EventNewsItem) -> EventNewsItemRecord:
        return EventNewsItemRecord(
            event_news_item_id=str(row.event_news_item_id),
            ticker=row.ticker,
            source_ticker=row.source_ticker,
            event_type=row.event_type,
            direction=row.direction,
            sentiment=row.sentiment,
            importance=row.importance,
            headline=row.headline,
            summary=row.summary,
            provider=row.provider,
            source_refs_json=list(row.source_refs_json or []),
            dedupe_key=row.dedupe_key,
            event_time=row.event_time,
            published_at=row.published_at,
            ingested_at=row.ingested_at,
            available_for_decision_at=row.available_for_decision_at,
            raw_payload_ref=row.raw_payload_ref,
            metadata_json=dict(row.metadata_json or {}),
        )


def _to_uuid(value: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, str(value))


def _to_uuid_or_none(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    return _to_uuid(value)
