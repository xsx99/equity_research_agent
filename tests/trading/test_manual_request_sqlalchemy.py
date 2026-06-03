from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.db.connection import get_session
from src.db.models.trading import ManualTickerRequest, UniverseFilterConfig
from src.trading.data_sources.universe import UniverseFilterConfig as UniverseFilterConfigRecord
from src.trading.data_sources.universe import UniverseSnapshotResult
from src.trading.manual_review.sqlalchemy import SQLAlchemyManualTickerRequestService
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
from src.trading.signals.sources import InMemorySignalSourceRepository, SourceRecord
from src.trading.workflows.signal_snapshot import SignalPipeline


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


def test_sqlalchemy_repository_loads_latest_active_universe_filter_config():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    session.add(
        UniverseFilterConfig(
            universe_filter_config_id=uuid.uuid4(),
            profile_name="default",
            version=1,
            is_active=False,
            min_price=5,
            min_avg_dollar_volume=25_000_000,
            included_sectors_json=[],
            excluded_sectors_json=["energy"],
            included_industries_json=[],
            excluded_industries_json=[],
            exchanges_json=[],
            asset_types_json=["common_stock"],
            manual_include_json=[],
            manual_exclude_json=[],
        )
    )
    session.add(
        UniverseFilterConfig(
            universe_filter_config_id=uuid.uuid4(),
            profile_name="default",
            version=3,
            is_active=True,
            min_price=8,
            min_avg_dollar_volume=50_000_000,
            included_sectors_json=["technology"],
            excluded_sectors_json=[],
            included_industries_json=[],
            excluded_industries_json=["banks"],
            exchanges_json=["NASDAQ"],
            asset_types_json=["common_stock"],
            manual_include_json=["NVDA"],
            manual_exclude_json=["GME"],
        )
    )

    config = repository.load_active_universe_filter_config()

    assert config.profile_name == "default"
    assert config.version == 3
    assert config.min_price == 8.0
    assert config.manual_include == ("NVDA",)
    assert config.manual_exclude == ("GME",)


def test_sqlalchemy_manual_request_service_loads_active_requests_and_records_evaluation():
    session = _FakeSession()
    now = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    active_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    session.add(
        ManualTickerRequest(
            manual_ticker_request_id=active_id,
            ticker="nvda",
            reason="watch earnings drift",
            mode="paper_trade_eligible",
            status="active",
            created_at=now,
        )
    )
    session.add(
        ManualTickerRequest(
            manual_ticker_request_id=uuid.uuid4(),
            ticker="aapl",
            reason="old request",
            mode="review_only",
            status="dismissed",
            created_at=now,
        )
    )
    service = SQLAlchemyManualTickerRequestService(session, now=lambda: now)

    active = service.load_active()
    updated = service.record_evaluation(
        str(active_id),
        result_status="actionable_trade",
        signal_snapshot_id=str(snapshot_id),
    )

    assert len(active) == 1
    assert active[0].ticker == "NVDA"
    assert active[0].mode == "paper_trade_eligible"
    assert updated.latest_result_status == "actionable_trade"
    assert updated.latest_signal_snapshot_id == str(snapshot_id)
    row = session.query(ManualTickerRequest).filter_by(manual_ticker_request_id=active_id).one_or_none()
    assert row is not None
    assert row.latest_result_status == "actionable_trade"
    assert str(row.latest_signal_snapshot_id) == str(snapshot_id)


def test_signal_pipeline_persists_manual_request_snapshot_before_db_evaluation_update():
    now = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    ticker = f"T{uuid.uuid4().hex[:4].upper()}"
    request_id = uuid.uuid4()

    try:
        with get_session() as session:
            session.add(
                ManualTickerRequest(
                    manual_ticker_request_id=request_id,
                    ticker=ticker,
                    reason="live runtime ordering regression",
                    mode="paper_trade_eligible",
                    status="active",
                    created_at=now,
                )
            )

        source_repository = InMemorySignalSourceRepository(
            (
                SourceRecord(
                    ticker=ticker,
                    source_family="technical",
                    source="fixture",
                    source_table="market_bars",
                    source_record_id=f"{ticker}-bars",
                    event_time=now,
                    published_at=now,
                    ingested_at=now,
                    available_for_decision_at=now,
                    payload={
                        "bars": [
                            {
                                "date": "2026-06-02",
                                "open": 99.0,
                                "high": 101.0,
                                "low": 98.0,
                                "close": 100.0,
                                "volume": 1_000_000,
                            }
                        ]
                    },
                ),
            )
        )
        universe_result = UniverseSnapshotResult(
            snapshot_id=str(uuid.uuid4()),
            snapshot_time=now,
            filter_config=UniverseFilterConfigRecord(),
            included=(),
            excluded=(),
        )

        with get_session() as session:
            pipeline = SignalPipeline(
                source_repository=source_repository,
                manual_request_service=SQLAlchemyManualTickerRequestService(session, now=lambda: now),
                snapshot_repository=SqlAlchemyTradingRepository(session),
            )

            snapshots = pipeline.build_pre_open_snapshots(
                universe_result=universe_result,
                decision_time=now,
            )

            updated = session.query(ManualTickerRequest).filter_by(manual_ticker_request_id=request_id).one_or_none()
            assert any(snapshot.ticker == ticker for snapshot in snapshots)
            assert updated is not None
            assert updated.latest_signal_snapshot_id is not None
    finally:
        with get_session() as session:
            session.query(ManualTickerRequest).filter_by(manual_ticker_request_id=request_id).delete(
                synchronize_session=False
            )
