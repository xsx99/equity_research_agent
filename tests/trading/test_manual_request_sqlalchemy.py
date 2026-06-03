from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.db.models.trading import ManualTickerRequest, UniverseFilterConfig
from src.trading.manual_review.sqlalchemy import SQLAlchemyManualTickerRequestService
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository


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
