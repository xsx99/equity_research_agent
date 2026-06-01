"""Point-in-time source rows and in-memory source adapters for PR02."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class SourceRecord:
    """Normalized point-in-time source row consumed by signal builders."""

    ticker: str
    source_family: str
    source: str
    source_table: str
    source_record_id: str
    event_time: datetime
    published_at: datetime
    ingested_at: datetime
    available_for_decision_at: datetime
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())

    @property
    def source_ref(self) -> dict[str, str]:
        return {
            "source": self.source,
            "source_table": self.source_table,
            "source_record_id": self.source_record_id,
        }


@dataclass(frozen=True)
class SourceIngestionRunRecord:
    """Scheduled or targeted source refresh metadata."""

    source_ingestion_run_id: str
    source_family: str
    run_type: str
    scope_json: dict[str, Any]
    provider: str | None
    as_of: datetime | None
    started_at: datetime
    completed_at: datetime | None
    status: str
    coverage_json: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FundamentalSnapshotRecord:
    """Repository-level shape matching the `fundamental_snapshots` table."""

    fundamental_snapshot_id: str
    ticker: str
    fiscal_period: str | None
    as_of_date: date | None
    provider: str
    source_refs_json: list[dict[str, str]]
    event_time: datetime
    published_at: datetime
    ingested_at: datetime
    available_for_decision_at: datetime
    raw_payload_ref: str | None
    normalized_metrics_json: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())


@dataclass(frozen=True)
class EventNewsItemRecord:
    """Repository-level shape matching the `event_news_items` table."""

    event_news_item_id: str
    ticker: str
    source_ticker: str | None
    event_type: str
    direction: str | None
    sentiment: str | None
    importance: str | None
    headline: str | None
    summary: str | None
    provider: str
    source_refs_json: list[dict[str, str]]
    dedupe_key: str
    event_time: datetime
    published_at: datetime
    ingested_at: datetime
    available_for_decision_at: datetime
    raw_payload_ref: str | None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        if self.source_ticker is not None:
            object.__setattr__(self, "source_ticker", self.source_ticker.strip().upper())


def source_record_from_fundamental_snapshot(snapshot: FundamentalSnapshotRecord) -> SourceRecord:
    """Convert a normalized fundamental row into the SignalPipeline source contract."""
    return SourceRecord(
        ticker=snapshot.ticker,
        source_family="fundamental",
        source=snapshot.provider,
        source_table="fundamental_snapshots",
        source_record_id=snapshot.fundamental_snapshot_id,
        event_time=snapshot.event_time,
        published_at=snapshot.published_at,
        ingested_at=snapshot.ingested_at,
        available_for_decision_at=snapshot.available_for_decision_at,
        payload=dict(snapshot.normalized_metrics_json),
    )


def source_record_from_event_news_item(item: EventNewsItemRecord) -> SourceRecord:
    """Convert a normalized event/news row into the SignalPipeline source contract."""
    payload = dict(item.metadata_json)
    payload.update(
        {
            "event_type": item.event_type,
            "direction": item.direction,
            "sentiment": item.sentiment,
            "importance": item.importance,
            "headline": item.headline,
            "summary": item.summary,
            "source_ticker": item.source_ticker,
        }
    )
    return SourceRecord(
        ticker=item.ticker,
        source_family="events_news",
        source=item.provider,
        source_table="event_news_items",
        source_record_id=item.event_news_item_id,
        event_time=item.event_time,
        published_at=item.published_at,
        ingested_at=item.ingested_at,
        available_for_decision_at=item.available_for_decision_at,
        payload=payload,
    )


class InMemorySignalSourceRepository:
    """Fixture-backed signal source repository."""

    def __init__(self, records: Iterable[SourceRecord] = ()) -> None:
        self._records: list[SourceRecord] = list(records)

    def add(self, *records: SourceRecord) -> None:
        self._records.extend(records)

    def records_for_ticker(self, ticker: str) -> tuple[SourceRecord, ...]:
        symbol = ticker.strip().upper()
        return tuple(record for record in self._records if record.ticker == symbol)

    def available_records(
        self,
        ticker: str,
        decision_time: datetime,
        *,
        source_family: str | None = None,
    ) -> tuple[SourceRecord, ...]:
        records = [
            record
            for record in self.records_for_ticker(ticker)
            if record.available_for_decision_at <= decision_time
            and (source_family is None or record.source_family == source_family)
        ]
        return tuple(sorted(records, key=lambda record: record.available_for_decision_at))

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
