from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from src.db.models.trading import MarketDailyBar
from src.trading.repositories.source_sqlalchemy import SQLAlchemySignalSourceRepository
from src.trading.signals.sources import MarketDailyBarRecord


class _FakeQuery:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def filter_by(self, **kwargs: object) -> "_FakeQuery":
        return _FakeQuery(
            [
                row
                for row in self._rows
                if all(getattr(row, key, None) == value for key, value in kwargs.items())
            ]
        )

    def filter(self, *criteria: object) -> "_FakeQuery":
        del criteria
        return self

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


def _bar(
    ticker: str,
    trade_date: date,
    *,
    available_for_decision_at: datetime,
    close_raw: float,
) -> MarketDailyBarRecord:
    return MarketDailyBarRecord(
        ticker=ticker,
        trade_date=trade_date,
        open_raw=close_raw - 1,
        high_raw=close_raw + 1,
        low_raw=close_raw - 2,
        close_raw=close_raw,
        adj_close=close_raw - 0.5,
        volume_raw=1_000_000,
        dividend=0.0,
        stock_split=0.0,
        provider="fixture",
        ingested_at=available_for_decision_at,
        available_for_decision_at=available_for_decision_at,
        quality_flags_json=["fixture"],
    )


def test_market_daily_bar_model_exposes_requested_schema_and_indexes():
    assert {
        "ticker",
        "trade_date",
        "open_raw",
        "high_raw",
        "low_raw",
        "close_raw",
        "adj_close",
        "volume_raw",
        "dividend",
        "stock_split",
        "provider",
        "ingested_at",
        "available_for_decision_at",
        "quality_flags_json",
        "created_at",
    }.issubset(MarketDailyBar.__table__.columns.keys())

    unique = next(
        constraint
        for constraint in MarketDailyBar.__table__.constraints
        if constraint.name == "uq_market_daily_bars_ticker_trade_date_provider"
    )
    assert tuple(column.name for column in unique.columns) == (
        "ticker",
        "trade_date",
        "provider",
    )

    indexes = {
        (index.name, tuple(column.name for column in index.columns))
        for index in MarketDailyBar.__table__.indexes
    }
    assert ("ix_market_daily_bars_ticker_trade_date", ("ticker", "trade_date")) in indexes
    assert ("ix_market_daily_bars_available_for_decision_at", ("available_for_decision_at",)) in indexes


def test_market_daily_bar_migration_creates_requested_table_contract():
    migration_path = Path("alembic/versions/034_market_daily_bars.py")
    source = migration_path.read_text()

    assert 'revision: str = "034"' in source
    assert 'down_revision: Union[str, None] = "033"' in source
    assert '"market_daily_bars"' in source
    assert '"uq_market_daily_bars_ticker_trade_date_provider"' in source
    assert '"ix_market_daily_bars_ticker_trade_date"' in source
    assert '"ix_market_daily_bars_available_for_decision_at"' in source


def test_market_daily_bar_repository_upserts_and_reads_only_decision_available_rows():
    session = _FakeSession()
    repository = SQLAlchemySignalSourceRepository(session)
    decision_time = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)

    repository.save_market_daily_bars(
        [
            _bar("aapl", date(2026, 9, 24), available_for_decision_at=decision_time, close_raw=100.0),
            _bar("AAPL", date(2026, 9, 25), available_for_decision_at=decision_time, close_raw=101.0),
            _bar(
                "AAPL",
                date(2026, 9, 26),
                available_for_decision_at=datetime(2026, 9, 27, 16, 0, tzinfo=timezone.utc),
                close_raw=999.0,
            ),
        ]
    )
    repository.save_market_daily_bars(
        [_bar("AAPL", date(2026, 9, 25), available_for_decision_at=decision_time, close_raw=102.0)]
    )

    rows = repository.load_market_daily_bars("aapl", decision_time, limit=10)

    assert [row.trade_date for row in rows] == [date(2026, 9, 24), date(2026, 9, 25)]
    assert [row.close_raw for row in rows] == [100.0, 102.0]
    assert rows[-1].quality_flags_json == ["fixture"]
    assert len(session.rows_by_type[MarketDailyBar]) == 3
    assert session.flush_calls == 2


def test_market_daily_bar_repository_loads_symbol_batches_with_independent_limits():
    session = _FakeSession()
    repository = SQLAlchemySignalSourceRepository(session)
    decision_time = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)
    repository.save_market_daily_bars(
        [
            _bar("AAPL", date(2026, 9, 24), available_for_decision_at=decision_time, close_raw=100.0),
            _bar("AAPL", date(2026, 9, 25), available_for_decision_at=decision_time, close_raw=101.0),
            _bar("MSFT", date(2026, 9, 24), available_for_decision_at=decision_time, close_raw=200.0),
            _bar("MSFT", date(2026, 9, 25), available_for_decision_at=decision_time, close_raw=201.0),
            _bar(
                "MSFT",
                date(2026, 9, 26),
                available_for_decision_at=datetime(2026, 9, 27, 16, 0, tzinfo=timezone.utc),
                close_raw=999.0,
            ),
        ]
    )

    rows_by_ticker = repository.load_market_daily_bars_for_symbols(
        ["aapl", "MSFT", "MISSING"],
        decision_time,
        limit_per_ticker=1,
    )

    assert set(rows_by_ticker) == {"AAPL", "MSFT"}
    assert [row.close_raw for row in rows_by_ticker["AAPL"]] == [101.0]
    assert [row.close_raw for row in rows_by_ticker["MSFT"]] == [201.0]
