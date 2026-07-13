from scripts.run_trading_universe_batch_enrichment_smoke import run_smoke


def test_universe_batch_enrichment_smoke_uses_batch_provider_and_reports_rows():
    class _Provider:
        def __init__(self) -> None:
            self.calls = []

        def fetch_daily_bars_for_symbols(self, symbols, lookback_days, batch_size):
            self.calls.append((tuple(symbols), lookback_days, batch_size))
            return {
                "TSM": [
                    {"date": "2026-07-10", "close": 230.0, "volume": 2_000_000},
                    {"date": "2026-07-11", "close": 240.0, "volume": 3_000_000},
                ]
            }

    provider = _Provider()

    report = run_smoke(
        tickers=("tsm", "missing"),
        market_provider=provider,
        lookback_days=20,
        batch_size=10,
    )

    assert provider.calls == [(("TSM", "MISSING"), 20, 10)]
    assert report["status"] == "passed"
    assert report["rows"] == [
        {
            "symbol": "TSM",
            "bar_count": 2,
            "price": 240.0,
            "avg_dollar_volume": 590_000_000.0,
            "status": "enriched",
        },
        {
            "symbol": "MISSING",
            "bar_count": 0,
            "price": None,
            "avg_dollar_volume": None,
            "status": "missing_bars",
        },
    ]
