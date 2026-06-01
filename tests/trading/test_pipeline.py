from datetime import date, datetime, timezone

from src.trading.manual_requests import ManualTickerRequestService
from src.trading.repository import InMemoryTradingRepository
from src.trading.pipeline import SignalPipeline, UniverseScanPipeline
from src.trading.signal_sources import InMemorySignalSourceRepository, SourceRecord
from src.trading.source_ingestion import SourceIngestionService
from src.trading.universe import UniverseAsset, UniverseFilterConfig


class _FakeUniverseProvider:
    def fetch_universe_assets(self):
        return [
            UniverseAsset("AAPL", "Apple", "common_stock", "NASDAQ", "Technology", "Hardware", 180.0, 90_000_000),
            UniverseAsset("MSFT", "Microsoft", "common_stock", "NASDAQ", "Technology", "Software", 320.0, 90_000_000),
        ]


class _FakeMarketProvider:
    def fetch_daily_bars(self, ticker, lookback_days):
        return [
            {"date": date(2026, 5, 29), "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0, "volume": 1_000_000},
            {"date": date(2026, 5, 30), "open": 100.0, "high": 104.0, "low": 99.0, "close": 103.0, "volume": 2_000_000},
        ]

    def fetch_context(self, ticker):
        return {"market_cap": 3_000_000_000_000}


class _FakeNewsProvider:
    def fetch_recent(self, ticker, limit):
        return []


def test_signal_pipeline_merges_active_manual_requests_into_snapshot_job():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    universe = UniverseScanPipeline(
        provider=_FakeUniverseProvider(),
        config=UniverseFilterConfig(manual_exclude=("MSFT",)),
        now=lambda: now,
    ).run()
    manual_service = ManualTickerRequestService(now=lambda: now)
    request = manual_service.create("MSFT", "please review", "review_only")
    sources = InMemorySignalSourceRepository()
    for ticker in ("AAPL", "MSFT"):
        sources.add(
            SourceRecord(
                ticker,
                "technical",
                "fixture",
                "market_bars",
                f"{ticker}-bars",
                now,
                now,
                now,
                now,
                {
                    "bars": [
                        {"date": date(2026, 5, 29), "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0, "volume": 1_000_000},
                        {"date": date(2026, 5, 30), "open": 100.0, "high": 104.0, "low": 99.0, "close": 103.0, "volume": 2_000_000},
                    ]
                },
            )
        )

    snapshots = SignalPipeline(
        source_repository=sources,
        manual_request_service=manual_service,
    ).build_pre_open_snapshots(
        universe_result=universe,
        decision_time=now,
    )

    assert [snapshot.ticker for snapshot in snapshots] == ["AAPL", "MSFT"]
    manual_snapshot = snapshots[1]
    assert manual_snapshot.selection_source == "manual_request"
    assert manual_snapshot.manual_request_id == request.request_id
    assert manual_service.load_active()[0].latest_result_status == "ordinary_watch"


def test_signal_pipeline_can_refresh_source_records_before_building_snapshots():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    universe = UniverseScanPipeline(
        provider=_FakeUniverseProvider(),
        config=UniverseFilterConfig(manual_exclude=("MSFT",)),
        now=lambda: now,
    ).run()
    source_repository = InMemorySignalSourceRepository()
    artifact_repository = InMemoryTradingRepository()
    ingestion_service = SourceIngestionService(
        market_provider=_FakeMarketProvider(),
        news_provider=_FakeNewsProvider(),
        source_repository=source_repository,
        artifact_repository=artifact_repository,
        provider_name="fixture",
        now=lambda: now,
        sleeper=lambda seconds: None,
    )

    snapshots = SignalPipeline(
        source_repository=source_repository,
        manual_request_service=ManualTickerRequestService(now=lambda: now),
        source_ingestion_service=ingestion_service,
    ).build_pre_open_snapshots(
        universe_result=universe,
        decision_time=now,
    )

    assert [snapshot.ticker for snapshot in snapshots] == ["AAPL"]
    assert snapshots[0].source_freshness_json["technical"] == "fresh"
    assert snapshots[0].signal_json["technical"]["return_1d"] == 0.03
    assert artifact_repository.source_ingestion_runs[0].run_type == "pre_open"
