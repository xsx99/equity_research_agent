from __future__ import annotations

from datetime import date, datetime, timezone
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


class _Alpaca:
    def __init__(self, result: dict[str, list[dict]]) -> None:
        self.result = result
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def fetch_daily_bars_for_symbols(self, symbols, lookback_days):
        self.calls.append((tuple(symbols), lookback_days))
        return self.result


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


def test_complete_yahoo_result_does_not_call_alpaca_and_records_coverage():
    repository = _Repository()
    alpaca = _Alpaca({})
    yahoo_calls = []

    def yahoo(symbols, start, end):
        yahoo_calls.append((tuple(symbols), start, end))
        return {symbol: [{"trade_date": date(2026, 10, 2), "close_raw": 100.0}] for symbol in symbols}

    result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["AAPL", "MSFT"],
        yahoo_fetcher=yahoo,
        alpaca_provider=alpaca,
        repository=repository,
        now=lambda: AS_OF,
    ).run(as_of=AS_OF)

    assert result.tickers_requested == 5
    assert result.tickers_succeeded == 5
    assert result.tickers_missing == ()
    assert result.fallback_used is False
    assert alpaca.calls == []
    assert yahoo_calls[0][0] == ("AAPL", "MSFT", "SPY", "QQQ", "GLD")
    assert repository.runs[-1].coverage_json == {
        "tickers_requested": 5,
        "tickers_succeeded": 5,
        "tickers_missing": [],
        "fallback_used": False,
    }


def test_one_yahoo_miss_sends_only_that_symbol_to_alpaca():
    repository = _Repository()
    alpaca = _Alpaca(
        {
            "XYZ": [
                {
                    "date": date(2026, 10, 2),
                    "open": 9.0,
                    "high": 11.0,
                    "low": 8.0,
                    "close": 10.0,
                    "volume": 500,
                }
            ]
        }
    )

    def yahoo(symbols, start, end):
        return {
            symbol: [{"trade_date": date(2026, 10, 2), "close_raw": 100.0}]
            for symbol in symbols
            if symbol != "XYZ"
        }

    result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["XYZ"],
        yahoo_fetcher=yahoo,
        alpaca_provider=alpaca,
        repository=repository,
        now=lambda: AS_OF,
    ).run(as_of=AS_OF)

    assert result.tickers_missing == ()
    assert result.fallback_used is True
    assert alpaca.calls == [(('XYZ',), 400)]
    assert {row.ticker for row in repository.rows} == {"GLD", "QQQ", "SPY", "XYZ"}


def test_provider_failure_does_not_delete_previous_daily_bar_rows():
    previous = _bar("AAPL", 101.0, provider="yahoo")
    repository = _Repository([previous])
    alpaca = _Alpaca({})

    def yahoo(symbols, start, end):
        raise RuntimeError("yahoo unavailable")

    result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["AAPL"],
        yahoo_fetcher=yahoo,
        alpaca_provider=alpaca,
        repository=repository,
        now=lambda: AS_OF,
    ).run(as_of=AS_OF)

    assert result.tickers_succeeded == 0
    assert set(result.tickers_missing) == {"AAPL", "GLD", "QQQ", "SPY"}
    assert repository.rows == [previous]
    assert repository.runs[-1].status == "degraded"
