from __future__ import annotations

from datetime import date, datetime, timezone

from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.signals.source_ingestion import SourceIngestionService
from src.trading.signals.sources import InMemorySignalSourceRepository, MarketDailyBarRecord
from src.trading.workflows.market_daily_bars import MarketDailyBarsBatch


AS_OF = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def _bars(ticker: str, first: float, second: float) -> tuple[MarketDailyBarRecord, ...]:
    return (
        MarketDailyBarRecord(
            ticker=ticker,
            trade_date=date(2026, 10, 1),
            open_raw=first,
            high_raw=first + 1,
            low_raw=first - 1,
            close_raw=first,
            adj_close=first,
            volume_raw=1_000,
            dividend=0.0,
            stock_split=0.0,
            provider="yahoo",
            ingested_at=AS_OF,
            available_for_decision_at=AS_OF,
        ),
        MarketDailyBarRecord(
            ticker=ticker,
            trade_date=date(2026, 10, 2),
            open_raw=second,
            high_raw=second + 1,
            low_raw=second - 1,
            close_raw=second,
            adj_close=second,
            volume_raw=2_000,
            dividend=0.0,
            stock_split=0.0,
            provider="yahoo",
            ingested_at=AS_OF,
            available_for_decision_at=AS_OF,
        ),
    )


class _DailyBarRepository(InMemorySignalSourceRepository):
    def __init__(self, bars_by_ticker):
        super().__init__()
        self.bars_by_ticker = bars_by_ticker
        self.load_calls = []

    def load_market_daily_bars_for_symbols(self, tickers, decision_time, limit_per_ticker):
        self.load_calls.append((tuple(tickers), decision_time, limit_per_ticker))
        return {
            ticker: bars
            for ticker, bars in self.bars_by_ticker.items()
            if ticker in tickers
        }


class _NoHistoricalProvider:
    def __init__(self) -> None:
        self.daily_bar_calls = []

    def fetch_daily_bars(self, ticker, lookback_days):
        self.daily_bar_calls.append((ticker, lookback_days))
        raise AssertionError("historical daily bars must come from the database")


class _BatchPremarketProvider(_NoHistoricalProvider):
    def __init__(self, prices=None, error=None) -> None:
        super().__init__()
        self.prices = prices or {}
        self.error = error
        self.premarket_calls = []
        self.intraday_calls = []
        self.option_chain_calls = []

    def fetch_premarket_prices_for_symbols(self, symbols, as_of):
        self.premarket_calls.append((tuple(symbols), as_of))
        if self.error is not None:
            raise self.error
        return dict(self.prices)

    def fetch_premarket_price(self, ticker, as_of):
        del ticker, as_of
        raise AssertionError("batch premarket path must not call single-symbol fallback")

    def fetch_intraday_bars(self, ticker, as_of):
        self.intraday_calls.append((ticker, as_of))
        return []

    def fetch_option_chain(self, ticker):
        self.option_chain_calls.append(ticker)
        return []


class _SingleOnlyPremarketProvider(_NoHistoricalProvider):
    def __init__(self) -> None:
        super().__init__()
        self.single_premarket_calls = []

    def fetch_premarket_price(self, ticker, as_of):
        self.single_premarket_calls.append((ticker, as_of))
        return 106.0


def _split_bars(ticker: str) -> tuple[MarketDailyBarRecord, ...]:
    return (
        MarketDailyBarRecord(
            ticker=ticker,
            trade_date=date(2026, 10, 1),
            open_raw=99.0,
            high_raw=101.0,
            low_raw=98.0,
            close_raw=100.0,
            adj_close=100.0,
            volume_raw=1_000,
            dividend=0.0,
            stock_split=0.0,
            provider="yahoo",
            ingested_at=AS_OF,
            available_for_decision_at=AS_OF,
        ),
        MarketDailyBarRecord(
            ticker=ticker,
            trade_date=date(2026, 10, 2),
            open_raw=49.0,
            high_raw=51.0,
            low_raw=48.0,
            close_raw=50.0,
            adj_close=50.0,
            volume_raw=2_000,
            dividend=0.0,
            stock_split=2.0,
            provider="yahoo",
            ingested_at=AS_OF,
            available_for_decision_at=AS_OF,
        ),
    )


def test_technical_ingestion_bulk_loads_db_bars_for_178_tickers_and_benchmarks():
    tickers = tuple(f"TICKER{index:03d}" for index in range(178))
    bars_by_ticker = {
        ticker: _bars(ticker, 100.0, 103.0)
        for ticker in tickers
    }
    bars_by_ticker["SPY"] = _bars("SPY", 400.0, 404.0)
    bars_by_ticker["QQQ"] = _bars("QQQ", 350.0, 357.0)
    source_repository = _DailyBarRepository(bars_by_ticker)
    market_provider = _BatchPremarketProvider(
        {ticker: 103.5 for ticker in tickers}
    )

    result = SourceIngestionService(
        market_provider=market_provider,
        news_provider=None,
        source_repository=source_repository,
        artifact_repository=InMemoryTradingRepository(),
        provider_name="alpaca_live",
        now=lambda: AS_OF,
    ).refresh_tickers(
        tickers,
        as_of=AS_OF,
        run_type="pre_open",
        source_families=("technical",),
    )

    technical = [record for record in result.source_records if record.source_family == "technical"]
    assert len(technical) == 178
    assert market_provider.daily_bar_calls == []
    assert market_provider.premarket_calls == [(tickers, AS_OF)]
    assert market_provider.intraday_calls == []
    assert market_provider.option_chain_calls == []
    assert result.ingestion_run.status == "succeeded"
    assert source_repository.load_calls[0][0] == tickers + ("SPY", "QQQ")
    last = next(record for record in technical if record.ticker == tickers[-1])
    assert last.payload["bars"][-1]["close"] == 103.0
    assert last.payload["benchmark_returns"] == {"SPY": 0.01, "QQQ": 0.02}


def test_last_good_db_bars_survive_nightly_yahoo_failure_before_next_pre_open():
    tickers = tuple(f"TICKER{index:03d}" for index in range(178))
    bars_by_ticker = {
        ticker: _bars(ticker, 100.0, 103.0)
        for ticker in tickers
    }
    bars_by_ticker["SPY"] = _bars("SPY", 400.0, 404.0)
    bars_by_ticker["QQQ"] = _bars("QQQ", 350.0, 357.0)
    source_repository = _DailyBarRepository(bars_by_ticker)
    source_repository.ingestion_runs = []
    source_repository.record_source_ingestion_run = source_repository.ingestion_runs.append

    def yahoo_failure(symbols, start, end):
        raise RuntimeError("yahoo unavailable")

    nightly_result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: tickers,
        yahoo_fetcher=yahoo_failure,
        repository=source_repository,
        now=lambda: AS_OF,
    ).run(as_of=AS_OF)

    market_provider = _BatchPremarketProvider(
        {ticker: 103.5 for ticker in tickers}
    )
    pre_open_result = SourceIngestionService(
        market_provider=market_provider,
        news_provider=None,
        source_repository=source_repository,
        artifact_repository=InMemoryTradingRepository(),
        provider_name="alpaca_live",
        now=lambda: AS_OF,
    ).refresh_tickers(
        tickers,
        as_of=AS_OF,
        run_type="pre_open",
        source_families=("technical",),
    )

    technical = [
        record
        for record in pre_open_result.source_records
        if record.source_family == "technical"
    ]
    assert nightly_result.ingestion_run.status == "degraded"
    assert nightly_result.tickers_succeeded == 0
    assert len(technical) == 178
    assert market_provider.daily_bar_calls == []
    assert market_provider.premarket_calls == [(tickers, AS_OF)]
    assert all(record.payload["bars"][-1]["close"] == 103.0 for record in technical)


def test_technical_ingestion_uses_one_batched_premarket_price_request_and_db_close():
    source_repository = _DailyBarRepository(
        {
            "AAPL": _bars("AAPL", 100.0, 103.0),
            "SPY": _bars("SPY", 400.0, 404.0),
            "QQQ": _bars("QQQ", 350.0, 357.0),
        }
    )
    market_provider = _BatchPremarketProvider({"AAPL": 106.09})

    result = SourceIngestionService(
        market_provider=market_provider,
        news_provider=None,
        source_repository=source_repository,
        artifact_repository=InMemoryTradingRepository(),
        provider_name="alpaca_live",
        now=lambda: AS_OF,
    ).refresh_tickers(
        ("AAPL",),
        as_of=AS_OF,
        run_type="pre_open",
        source_families=("technical",),
    )

    technical = result.source_records[0]
    assert technical.payload["premarket_gap_pct"] == (106.09 - 103.0) / 103.0
    assert market_provider.premarket_calls == [(('AAPL',), AS_OF)]
    assert result.ingestion_run.status == "succeeded"


def test_premarket_batch_failure_keeps_db_technical_record_and_degrades_run():
    source_repository = _DailyBarRepository(
        {
            "AAPL": _bars("AAPL", 100.0, 103.0),
            "SPY": _bars("SPY", 400.0, 404.0),
            "QQQ": _bars("QQQ", 350.0, 357.0),
        }
    )
    market_provider = _BatchPremarketProvider(error=RuntimeError("premarket unavailable"))

    result = SourceIngestionService(
        market_provider=market_provider,
        news_provider=None,
        source_repository=source_repository,
        artifact_repository=InMemoryTradingRepository(),
        provider_name="alpaca_live",
        now=lambda: AS_OF,
    ).refresh_tickers(
        ("AAPL",),
        as_of=AS_OF,
        run_type="pre_open",
        source_families=("technical",),
    )

    technical = result.source_records[0]
    assert technical.payload["bars"][-1]["close"] == 103.0
    assert technical.payload["premarket_gap_pct"] is None
    assert result.ingestion_run.status == "degraded"
    assert result.ingestion_run.error_message == "premarket unavailable"


def test_pre_open_without_batch_premarket_support_does_not_call_single_symbol_fallback():
    source_repository = _DailyBarRepository(
        {
            "AAPL": _bars("AAPL", 100.0, 103.0),
            "SPY": _bars("SPY", 400.0, 404.0),
            "QQQ": _bars("QQQ", 350.0, 357.0),
        }
    )
    market_provider = _SingleOnlyPremarketProvider()

    result = SourceIngestionService(
        market_provider=market_provider,
        news_provider=None,
        source_repository=source_repository,
        artifact_repository=InMemoryTradingRepository(),
        provider_name="alpaca_live",
        now=lambda: AS_OF,
    ).refresh_tickers(
        ("AAPL",),
        as_of=AS_OF,
        run_type="pre_open",
        source_families=("technical",),
    )

    technical = result.source_records[0]
    assert technical.payload["premarket_gap_pct"] is None
    assert market_provider.single_premarket_calls == []
    assert result.ingestion_run.status == "degraded"
    assert result.ingestion_run.error_message == "premarket_batch_unavailable"
    assert result.ingestion_run.metadata_json["premarket_prices"] == {
        "tickers_requested": 1,
        "tickers_succeeded": 0,
        "tickers_missing": ["AAPL"],
    }


def test_partial_premarket_batch_is_degraded_and_marks_missing_prices():
    source_repository = _DailyBarRepository(
        {
            "AAPL": _bars("AAPL", 100.0, 103.0),
            "MSFT": _bars("MSFT", 200.0, 203.0),
            "SPY": _bars("SPY", 400.0, 404.0),
            "QQQ": _bars("QQQ", 350.0, 357.0),
        }
    )
    market_provider = _BatchPremarketProvider({"AAPL": 106.0})

    result = SourceIngestionService(
        market_provider=market_provider,
        news_provider=None,
        source_repository=source_repository,
        artifact_repository=InMemoryTradingRepository(),
        provider_name="alpaca_live",
        now=lambda: AS_OF,
    ).refresh_tickers(
        ("AAPL", "MSFT"),
        as_of=AS_OF,
        run_type="pre_open",
        source_families=("technical",),
    )

    records = {record.ticker: record for record in result.source_records}
    assert records["AAPL"].payload["premarket_gap_pct"] == (106.0 - 103.0) / 103.0
    assert records["MSFT"].payload["premarket_gap_pct"] is None
    assert result.ingestion_run.status == "degraded"
    assert result.ingestion_run.metadata_json["premarket_prices"] == {
        "tickers_requested": 2,
        "tickers_succeeded": 1,
        "tickers_missing": ["MSFT"],
    }


def test_split_safe_technical_payload_keeps_raw_premarket_baseline():
    source_repository = _DailyBarRepository(
        {
            "AAPL": _split_bars("AAPL"),
            "SPY": _bars("SPY", 400.0, 404.0),
            "QQQ": _bars("QQQ", 350.0, 357.0),
        }
    )
    market_provider = _BatchPremarketProvider({"AAPL": 50.0})

    result = SourceIngestionService(
        market_provider=market_provider,
        news_provider=None,
        source_repository=source_repository,
        artifact_repository=InMemoryTradingRepository(),
        provider_name="alpaca_live",
        now=lambda: AS_OF,
    ).refresh_tickers(
        ("AAPL",),
        as_of=AS_OF,
        run_type="pre_open",
        source_families=("technical",),
    )

    technical = result.source_records[0]
    assert [bar["close"] for bar in technical.payload["bars"]] == [50.0, 50.0]
    assert technical.payload["premarket_gap_pct"] == 0.0
