from datetime import date, datetime, timezone

from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.signals.sources import InMemorySignalSourceRepository, SourceRecord
from src.trading.signals.source_ingestion import SourceIngestionService


def test_signal_source_repository_returns_latest_decision_available_rows_by_family():
    decision_time = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    old_time = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    new_time = datetime(2026, 6, 1, 11, 0, tzinfo=timezone.utc)
    future_time = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    repo = InMemorySignalSourceRepository()
    repo.add(
        SourceRecord("AAPL", "fundamental", "fixture", "fundamental_snapshots", "old", old_time, old_time, old_time, old_time, {"score": 1}),
        SourceRecord("AAPL", "fundamental", "fixture", "fundamental_snapshots", "new", new_time, new_time, new_time, new_time, {"score": 2}),
        SourceRecord("AAPL", "fundamental", "fixture", "fundamental_snapshots", "future", future_time, future_time, future_time, future_time, {"score": 99}),
    )

    rows = repo.latest_available_by_family("AAPL", "fundamental", decision_time)

    assert [row.source_record_id for row in rows] == ["new"]


class _FakeMarketProvider:
    def __init__(self) -> None:
        self.bar_calls: list[tuple[str, int]] = []
        self.context_calls: list[str] = []

    def fetch_daily_bars(self, ticker: str, lookback_days: int):
        self.bar_calls.append((ticker, lookback_days))
        return [
            {"date": date(2026, 5, 29), "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0, "volume": 1_000_000},
            {"date": date(2026, 5, 30), "open": 100.0, "high": 104.0, "low": 99.0, "close": 103.0, "volume": 2_000_000},
        ]

    def fetch_context(self, ticker: str):
        self.context_calls.append(ticker)
        return {
            "market_cap": 3_000_000_000_000,
            "revenue_growth_score": 0.8,
            "quality_score": 0.7,
            "short_interest_pct_float": 2.4,
            "pe_ratio": 28.0,
            "earnings_in_days": 6,
        }


class _FakeNewsProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def fetch_recent(self, ticker: str, limit: int):
        self.calls.append((ticker, limit))
        return [
            {
                "title": "Apple upgraded after stronger iPhone demand",
                "summary": "Analyst raises rating and price target.",
                "published_at": "2026-06-01T10:30:00+00:00",
                "source": "fixture-news",
                "url": "https://example.test/aapl-upgrade",
                "signal_type": "analyst_rating",
            }
        ]


class _DuplicateNewsProvider:
    def fetch_recent(self, ticker: str, limit: int):
        assert ticker == "AAPL"
        assert limit == 5
        return [
            {
                "title": "Is It Too Late To Buy Apple Stock?",
                "summary": "Retail commentary without a concrete catalyst.",
                "published_at": "2026-06-01T09:00:00+00:00",
                "source": "Retail Blog",
                "url": "https://example.test/retail-opinion",
                "signal_type": "general_news",
            },
            {
                "title": "Morgan Stanley upgrades Apple to Overweight, target to $180",
                "summary": "The analyst cited stronger iPhone demand.",
                "published_at": "2026-06-01T10:00:00+00:00",
                "source": "Reuters",
                "url": "https://example.test/reuters-upgrade",
                "signal_type": "analyst_rating",
            },
            {
                "title": "Apple upgraded to Overweight at Morgan Stanley; PT raised to $180",
                "summary": "Demand checks improved and the broker lifted its target.",
                "published_at": "2026-06-01T10:05:00+00:00",
                "source": "Dow Jones",
                "url": "https://example.test/dj-upgrade",
                "signal_type": "analyst_rating",
            },
            {
                "title": "Morgan Stanley lifts Apple target to $190 and keeps Overweight",
                "summary": "The revised target reflects stronger services momentum.",
                "published_at": "2026-06-01T11:00:00+00:00",
                "source": "Reuters",
                "url": "https://example.test/reuters-upgrade-190",
                "signal_type": "analyst_rating",
            },
        ]


def test_source_ingestion_service_adapts_existing_providers_and_records_metadata():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    market_provider = _FakeMarketProvider()
    news_provider = _FakeNewsProvider()
    source_repository = InMemorySignalSourceRepository()
    artifact_repository = InMemoryTradingRepository()

    result = SourceIngestionService(
        market_provider=market_provider,
        news_provider=news_provider,
        source_repository=source_repository,
        artifact_repository=artifact_repository,
        provider_name="fixture",
        now=lambda: now,
        sleeper=lambda seconds: None,
    ).refresh_tickers(("aapl",), as_of=now, run_type="targeted")

    records = source_repository.records_for_ticker("AAPL")
    assert result.ingestion_run.status == "succeeded"
    assert result.ingestion_run.source_family == "all"
    assert result.ingestion_run.coverage_json == {
        "tickers_requested": 1,
        "source_records": 3,
        "fundamental_snapshots": 1,
        "event_news_items": 1,
    }
    assert {record.source_family for record in records} == {"technical", "fundamental", "events_news"}
    assert source_repository.latest_available_by_family("AAPL", "technical", now)[0].payload["bars"][1]["close"] == 103.0
    assert artifact_repository.fundamental_snapshots[0].normalized_metrics_json["market_cap"] == 3_000_000_000_000
    assert artifact_repository.event_news_items[0].event_type == "analyst_upgrade"
    assert artifact_repository.provider_request_runs
    assert {run.source_ingestion_run_id for run in artifact_repository.provider_request_runs} == {
        result.ingestion_run.source_ingestion_run_id
    }
    assert [run.status for run in artifact_repository.provider_request_runs] == [
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    assert market_provider.bar_calls == [("AAPL", 252)]
    assert market_provider.context_calls == ["AAPL"]
    assert news_provider.calls == [("AAPL", 5)]


def test_source_ingestion_service_condenses_news_and_records_run_metadata():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    source_repository = InMemorySignalSourceRepository()
    artifact_repository = InMemoryTradingRepository()

    result = SourceIngestionService(
        market_provider=_FakeMarketProvider(),
        news_provider=_DuplicateNewsProvider(),
        source_repository=source_repository,
        artifact_repository=artifact_repository,
        provider_name="fixture",
        now=lambda: now,
        sleeper=lambda seconds: None,
    ).refresh_tickers(("AAPL",), as_of=now, run_type="targeted", source_families=("events_news",))

    assert result.ingestion_run.coverage_json == {
        "tickers_requested": 1,
        "source_records": 2,
        "fundamental_snapshots": 0,
        "event_news_items": 2,
    }
    assert result.ingestion_run.metadata_json["news_condensation"] == {
        "raw_news_item_count": 4,
        "kept_news_item_count": 2,
        "dropped_low_signal_count": 1,
        "dropped_duplicate_count": 1,
        "dropped_irrelevant_count": 0,
    }
    assert [item.headline for item in artifact_repository.event_news_items] == [
        "Morgan Stanley upgrades Apple to Overweight, target to $180",
        "Morgan Stanley lifts Apple target to $190 and keeps Overweight",
    ]
    assert artifact_repository.event_news_items[0].metadata_json["compression_status"] == "kept"
    assert artifact_repository.event_news_items[0].metadata_json["duplicate_count"] == 2
    assert artifact_repository.event_news_items[0].metadata_json["dropped_sources"] == ["Dow Jones"]
