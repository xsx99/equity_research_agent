from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from src.db.models.trading import EventNewsItem, FundamentalSnapshot, ProviderRequestRun, SourceIngestionRun
from src.trading.repositories.source_sqlalchemy import SQLAlchemySignalSourceRepository
from src.trading.signals.sources import EventNewsItemRecord, FundamentalSnapshotRecord, SourceIngestionRunRecord
from src.trading.data_sources.provider_resilience import ProviderRequestRunRecord


class _FakeQuery:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def filter_by(self, **kwargs: object) -> "_FakeQuery":
        filtered = [
            row
            for row in self._rows
            if all(getattr(row, key) == value for key, value in kwargs.items())
        ]
        return _FakeQuery(filtered)

    def all(self) -> list[object]:
        return list(self._rows)

    def one_or_none(self) -> object | None:
        if not self._rows:
            return None
        if len(self._rows) > 1:
            raise AssertionError("expected at most one row")
        return self._rows[0]


class _FakeSession:
    def __init__(self) -> None:
        self.rows_by_type: dict[type, list[object]] = {}
        self.flush_calls = 0

    def add(self, row: object) -> None:
        self.rows_by_type.setdefault(type(row), []).append(row)

    def query(self, model: type) -> _FakeQuery:
        return _FakeQuery(self.rows_by_type.get(model, []))

    def flush(self) -> None:
        self.flush_calls += 1


def test_sqlalchemy_signal_source_repository_persists_source_artifacts():
    session = _FakeSession()
    repository = SQLAlchemySignalSourceRepository(session)
    now = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    ingestion = SourceIngestionRunRecord(
        source_ingestion_run_id="ingestion-1",
        source_family="all",
        run_type="pre_open",
        scope_json={"tickers": ["NVDA"]},
        provider="alpaca",
        as_of=now,
        started_at=now,
        completed_at=now,
        status="succeeded",
        coverage_json={"source_records": 2},
    )
    request = ProviderRequestRunRecord(
        provider="alpaca",
        endpoint="market_context",
        source_family="fundamental",
        scope="NVDA",
        cache_status="miss",
        request_count=1,
        budget_remaining=99,
        retry_count=0,
        backoff_ms=0,
        latency_ms=120,
        status="succeeded",
        error_code=None,
        circuit_state="closed",
        degraded_mode=False,
        started_at=now,
        completed_at=now,
        source_ingestion_run_id="ingestion-1",
    )
    snapshot = FundamentalSnapshotRecord(
        fundamental_snapshot_id="fundamental-1",
        ticker="NVDA",
        fiscal_period="2026Q2",
        as_of_date=date(2026, 6, 2),
        provider="alpaca",
        source_refs_json=[],
        event_time=now,
        published_at=now,
        ingested_at=now,
        available_for_decision_at=now,
        raw_payload_ref=None,
        normalized_metrics_json={"market_cap": 1_000_000_000},
    )
    item = EventNewsItemRecord(
        event_news_item_id="event-1",
        ticker="NVDA",
        source_ticker=None,
        event_type="earnings_beat_raise",
        direction="positive",
        sentiment="positive",
        importance="high",
        headline="Beat and raise",
        summary="Strong print",
        provider="alpaca",
        source_refs_json=[],
        dedupe_key="NVDA|beat_raise|2026-06-03",
        event_time=now,
        published_at=now,
        ingested_at=now,
        available_for_decision_at=now,
        raw_payload_ref=None,
        metadata_json={},
    )

    repository.record_source_ingestion_run(ingestion)
    repository.record_provider_request(request)
    repository.save_fundamental_snapshot(snapshot)
    repository.save_event_news_item(item)

    assert session.query(SourceIngestionRun).one_or_none() is not None
    assert session.query(ProviderRequestRun).one_or_none() is not None
    assert session.query(FundamentalSnapshot).one_or_none() is not None
    assert session.query(EventNewsItem).one_or_none() is not None


def test_sqlalchemy_signal_source_repository_reconstructs_point_in_time_records():
    session = _FakeSession()
    repository = SQLAlchemySignalSourceRepository(session)
    decision_time = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    earlier = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    later = datetime(2026, 6, 3, 13, 0, tzinfo=timezone.utc)
    session.add(
        FundamentalSnapshot(
            fundamental_snapshot_id=uuid.uuid4(),
            ticker="NVDA",
            fiscal_period="2026Q2",
            as_of_date=date(2026, 6, 2),
            provider="alpaca",
            source_refs_json=[],
            event_time=earlier,
            published_at=earlier,
            ingested_at=earlier,
            available_for_decision_at=earlier,
            raw_payload_ref=None,
            normalized_metrics_json={"market_cap": 1_000_000_000},
        )
    )
    session.add(
        EventNewsItem(
            event_news_item_id=uuid.uuid4(),
            ticker="NVDA",
            source_ticker=None,
            event_type="earnings_beat_raise",
            direction="positive",
            sentiment="positive",
            importance="high",
            headline="Beat and raise",
            summary="Strong print",
            provider="alpaca",
            source_refs_json=[],
            dedupe_key="nvda-beat-raise",
            event_time=later,
            published_at=later,
            ingested_at=later,
            available_for_decision_at=later,
            raw_payload_ref=None,
            metadata_json={},
        )
    )

    records = repository.available_records("NVDA", decision_time)

    assert len(records) == 1
    assert records[0].ticker == "NVDA"
    assert records[0].source_family == "fundamental"
