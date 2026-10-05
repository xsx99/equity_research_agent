from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from src.trading.signals.sources import MarketDailyBarRecord
from src.trading.workflows.market_daily_bars import (
    MarketDailyBarsBatch,
    load_active_daily_bar_tickers,
)


AS_OF = datetime(2026, 10, 2, 20, 5, tzinfo=timezone.utc)


def _bar(ticker: str, close: float, *, provider: str = "fixture") -> MarketDailyBarRecord:
    return MarketDailyBarRecord(
        ticker=ticker,
        trade_date=date(2026, 10, 2),
        open_raw=close - 1,
        high_raw=close + 1,
        low_raw=close - 2,
        close_raw=close,
        adj_close=close,
        volume_raw=1_000,
        dividend=0.0,
        stock_split=0.0,
        provider=provider,
        ingested_at=AS_OF,
        available_for_decision_at=AS_OF,
    )


class _Repository:
    def __init__(self, existing: list[MarketDailyBarRecord] | None = None) -> None:
        self.rows = list(existing or [])
        self.runs = []

    def save_market_daily_bars(self, bars) -> None:
        self.rows.extend(bars)

    def record_source_ingestion_run(self, run) -> None:
        self.runs.append(run)


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return list(self.rows)

    def filter(self, *criteria):
        del criteria
        return self


class _Session:
    def __init__(self):
        self.snapshots = [
            SimpleNamespace(
                status="succeeded",
                snapshot_date=date(2026, 10, 2),
                started_at=AS_OF,
                completed_at=AS_OF,
                universe_snapshot_id="snapshot-1",
            )
        ]
        self.symbols = [SimpleNamespace(symbol="AAPL")]

    def query(self, model):
        name = getattr(model, "__name__", "")
        return _Query(self.snapshots if name == "UniverseSnapshot" else self.symbols)


def test_active_batch_scope_unions_latest_universe_and_watchlist(monkeypatch):
    monkeypatch.setattr(
        "src.trading.workflows.market_daily_bars.get_active_tickers",
        lambda session: ["MSFT", "AAPL"],
    )

    assert load_active_daily_bar_tickers(_Session()) == ("AAPL", "MSFT")


def test_complete_yahoo_result_records_only_yahoo_coverage_and_recent_window():
    repository = _Repository()
    yahoo_calls = []

    def yahoo(symbols, start, end):
        yahoo_calls.append((tuple(symbols), start, end))
        return {symbol: [{"trade_date": date(2026, 10, 2), "close_raw": 100.0}] for symbol in symbols}

    result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["AAPL", "MSFT"],
        yahoo_fetcher=yahoo,
        repository=repository,
        now=lambda: AS_OF,
    ).run(as_of=AS_OF)

    assert result.tickers_requested == 5
    assert result.tickers_succeeded == 5
    assert result.tickers_missing == ()
    assert not hasattr(result, "fallback_used")
    assert yahoo_calls[0][0] == ("AAPL", "MSFT", "SPY", "QQQ", "GLD")
    assert yahoo_calls[0][1] == AS_OF.date() - timedelta(days=9)
    assert yahoo_calls[0][2] == AS_OF.date() + timedelta(days=1)
    assert repository.runs[-1].coverage_json == {
        "tickers_requested": 5,
        "tickers_succeeded": 5,
        "tickers_missing": [],
    }


def test_daily_batch_scope_adds_three_support_symbols_to_178_research_tickers():
    tickers = tuple(f"TICKER{index:03d}" for index in range(178))
    requested = []

    def yahoo(symbols, start, end):
        requested.append(tuple(symbols))
        return {
            symbol: [{"trade_date": date(2026, 10, 2), "close_raw": 100.0}]
            for symbol in symbols
        }

    result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: tickers,
        yahoo_fetcher=yahoo,
        repository=_Repository(),
        now=lambda: AS_OF,
    ).run(as_of=AS_OF)

    assert result.tickers_requested == 181
    assert result.tickers_succeeded == 181
    assert requested == [tickers + ("SPY", "QQQ", "GLD")]


def test_one_yahoo_miss_is_degraded_without_historical_fallback():
    repository = _Repository()

    def yahoo(symbols, start, end):
        return {
            symbol: [{"trade_date": date(2026, 10, 2), "close_raw": 100.0}]
            for symbol in symbols
            if symbol != "XYZ"
        }

    result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["XYZ"],
        yahoo_fetcher=yahoo,
        repository=repository,
        now=lambda: AS_OF,
    ).run(as_of=AS_OF)

    assert result.tickers_missing == ("XYZ",)
    assert result.tickers_succeeded == 3
    assert result.ingestion_run.status == "degraded"
    assert {row.ticker for row in repository.rows} == {"GLD", "QQQ", "SPY"}


def test_provider_failure_does_not_delete_previous_daily_bar_rows():
    previous = _bar("AAPL", 101.0, provider="yahoo")
    repository = _Repository([previous])

    def yahoo(symbols, start, end):
        raise RuntimeError("yahoo unavailable")

    result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["AAPL"],
        yahoo_fetcher=yahoo,
        repository=repository,
        now=lambda: AS_OF,
    ).run(as_of=AS_OF)

    assert result.tickers_succeeded == 0
    assert set(result.tickers_missing) == {"AAPL", "GLD", "QQQ", "SPY"}
    assert repository.rows[0] == previous
    assert previous in repository.rows
    assert repository.runs[-1].status == "degraded"


def test_backfill_mode_uses_long_window_but_default_run_stays_incremental():
    calls = []

    def yahoo(symbols, start, end):
        calls.append((tuple(symbols), start, end))
        return {
            symbol: [{"trade_date": date(2026, 10, 2), "close_raw": 100.0}]
            for symbol in symbols
        }

    batch = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["AAPL"],
        yahoo_fetcher=yahoo,
        repository=_Repository(),
        now=lambda: AS_OF,
    )

    batch.run(as_of=AS_OF)
    batch.run(as_of=AS_OF, backfill=True)

    assert calls[0][1] == AS_OF.date() - timedelta(days=9)
    assert calls[1][1] == AS_OF.date() - timedelta(days=399)


def test_stale_latest_yahoo_bar_is_missing_without_deleting_existing_rows():
    previous = _bar("AAPL", 101.0, provider="yahoo")
    repository = _Repository([previous])

    def yahoo(symbols, start, end):
        return {
            symbol: [{"trade_date": date(2026, 10, 1), "close_raw": 100.0}]
            for symbol in symbols
        }

    result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["AAPL"],
        yahoo_fetcher=yahoo,
        repository=repository,
        now=lambda: AS_OF,
    ).run(as_of=AS_OF)

    assert result.tickers_missing == ("AAPL", "SPY", "QQQ", "GLD")
    assert result.tickers_succeeded == 0
    assert repository.rows[0] == previous
    assert previous in repository.rows
    assert result.ingestion_run.status == "degraded"


def test_weekend_run_uses_last_completed_xnys_session_for_coverage():
    as_of = datetime(2026, 7, 5, 15, 0, tzinfo=timezone.utc)
    repository = _Repository()

    def yahoo(symbols, start, end):
        assert start == date(2026, 6, 23)
        assert end == date(2026, 7, 3)
        return {
            symbol: [{"trade_date": date(2026, 7, 2), "close_raw": 100.0}]
            for symbol in symbols
        }

    result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["AAPL"],
        yahoo_fetcher=yahoo,
        repository=repository,
        now=lambda: as_of,
    ).run(as_of=as_of)

    assert result.tickers_missing == ()
    assert result.tickers_succeeded == 4
    assert result.ingestion_run.status == "succeeded"


def test_market_holiday_run_uses_last_completed_xnys_session_for_coverage():
    as_of = datetime(2026, 7, 6, 13, 0, tzinfo=timezone.utc)
    repository = _Repository()

    def yahoo(symbols, start, end):
        return {
            symbol: [{"trade_date": date(2026, 7, 2), "close_raw": 100.0}]
            for symbol in symbols
        }

    result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["AAPL"],
        yahoo_fetcher=yahoo,
        repository=repository,
        now=lambda: as_of,
    ).run(as_of=as_of)

    assert result.tickers_missing == ()
    assert result.tickers_succeeded == 4
    assert result.ingestion_run.status == "succeeded"
