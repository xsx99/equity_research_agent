from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from src.db.connection import get_session
from src.db.models.trading import EventNewsItem, FundamentalSnapshot, ProviderRequestRun, SourceIngestionRun
from src.providers.market_data.types import DailyBar
from src.trading.repositories.source_sqlalchemy import SQLAlchemySignalSourceRepository
from src.trading.signals.source_ingestion import SourceIngestionService
from src.trading.signals.sources import (
    EventNewsItemRecord,
    FundamentalSnapshotRecord,
    SourceIngestionRunRecord,
    SourceRecord,
)
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


class _FakeMarketProvider:
    def fetch_daily_bars(self, ticker: str, lookback_days: int) -> list[DailyBar]:
        del lookback_days
        return [
            {
                "date": date(2026, 6, 2),
                "open": 198.0,
                "high": 201.0,
                "low": 197.5,
                "close": 200.5,
                "volume": 1_000_000,
            }
        ]

    def fetch_context(self, ticker: str) -> dict[str, object]:
        del ticker
        return {
            "market_cap": 1_000_000_000,
            "pe_ratio": 30.0,
            "ps_ratio": 7.0,
            "earnings_in_days": 14,
        }


class _FakeNewsProvider:
    def fetch_recent(self, *, ticker: str, limit: int) -> list[dict[str, object]]:
        del limit
        return [
            {
                "title": f"{ticker} headline",
                "summary": "Strong print",
                "source": "fixture-news",
                "published_at": "2026-06-03T12:30:00+00:00",
                "signal_type": "earnings_beat_raise",
            }
        ]


class _SharedNewsProvider:
    def fetch_recent(self, *, ticker: str, limit: int) -> list[dict[str, object]]:
        del ticker, limit
        return [
            {
                "title": "Macro headline impacting several mega-caps",
                "summary": "Shared article returned for multiple symbols.",
                "source": "fixture-news",
                "url": "https://example.com/shared-article",
                "published_at": "2026-06-03T12:30:00+00:00",
                "signal_type": "general_news",
            }
        ]


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


def test_sqlalchemy_signal_source_repository_keeps_runtime_technical_rows_available():
    session = _FakeSession()
    repository = SQLAlchemySignalSourceRepository(session)
    decision_time = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    repository.add(
        SourceRecord(
            ticker="AAPL",
            source_family="technical",
            source="fixture",
            source_table="market_bars",
            source_record_id="market-bars-aapl",
            event_time=decision_time,
            published_at=decision_time,
            ingested_at=decision_time,
            available_for_decision_at=decision_time,
            payload={
                "bars": [
                    {
                        "date": "2026-06-02",
                        "open": 198.0,
                        "high": 201.0,
                        "low": 197.5,
                        "close": 200.5,
                        "volume": 1_000_000,
                    }
                ]
            },
        )
    )

    rows = repository.latest_available_by_family("AAPL", "technical", decision_time)

    assert len(rows) == 1
    assert rows[0].source_family == "technical"
    assert rows[0].payload["bars"][0]["close"] == 200.5


def test_source_ingestion_service_persists_provider_requests_after_ingestion_run_exists():
    now = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    provider_name = f"test_provider_{uuid.uuid4().hex}"

    try:
        with get_session() as session:
            repository = SQLAlchemySignalSourceRepository(session)
            service = SourceIngestionService(
                market_provider=_FakeMarketProvider(),
                news_provider=_FakeNewsProvider(),
                source_repository=repository,
                artifact_repository=repository,
                provider_name=provider_name,
                now=lambda: now,
            )

            result = service.refresh_tickers(("AAPL",), as_of=now, run_type="pre_open")

            provider_requests = (
                session.query(ProviderRequestRun)
                .filter_by(source_ingestion_run_id=uuid.UUID(result.ingestion_run.source_ingestion_run_id))
                .all()
            )
            assert len(provider_requests) == 3
    finally:
        with get_session() as session:
            session.query(ProviderRequestRun).filter_by(provider=provider_name).delete(synchronize_session=False)
            session.query(SourceIngestionRun).filter_by(provider=provider_name).delete(synchronize_session=False)
            session.query(FundamentalSnapshot).filter_by(provider=provider_name).delete(synchronize_session=False)
            session.query(EventNewsItem).filter_by(provider=provider_name).delete(synchronize_session=False)


def test_source_ingestion_service_namespaces_shared_news_dedupe_keys_per_ticker():
    now = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    provider_name = f"test_provider_{uuid.uuid4().hex}"

    try:
        with get_session() as session:
            repository = SQLAlchemySignalSourceRepository(session)
            service = SourceIngestionService(
                market_provider=_FakeMarketProvider(),
                news_provider=_SharedNewsProvider(),
                source_repository=repository,
                artifact_repository=repository,
                provider_name=provider_name,
                now=lambda: now,
            )

            service.refresh_tickers(("AAPL", "MSFT"), as_of=now, run_type="pre_open")

            rows = session.query(EventNewsItem).filter_by(provider=provider_name).all()
            keys = {row.dedupe_key for row in rows}
            assert len(rows) == 2
            assert len(keys) == 2
            assert all(key.startswith(("AAPL|", "MSFT|")) for key in keys)
    finally:
        with get_session() as session:
            session.query(ProviderRequestRun).filter_by(provider=provider_name).delete(synchronize_session=False)
            session.query(SourceIngestionRun).filter_by(provider=provider_name).delete(synchronize_session=False)
            session.query(FundamentalSnapshot).filter_by(provider=provider_name).delete(synchronize_session=False)
            session.query(EventNewsItem).filter_by(provider=provider_name).delete(synchronize_session=False)
