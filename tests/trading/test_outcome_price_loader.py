from datetime import date, datetime, timezone

from src.trading.outcomes.prices import OutcomePriceLoader, OutcomePriceRequest


class _Provider:
    provider_name = "fake_alpaca"

    def __init__(self) -> None:
        self.calls = []

    def fetch_daily_bars_for_symbols(self, symbols, *, lookback_days):
        self.calls.append((tuple(symbols), lookback_days))
        return {
            symbol: [
                {"date": date(2026, 7, 2), "open": 100, "high": 104, "low": 99, "close": 102},
                {"date": date(2026, 7, 7), "open": 103, "high": 108, "low": 102, "close": 107},
            ]
            for symbol in symbols
            if symbol != "MISSING"
        }


def test_loader_batches_candidate_and_persisted_comparator_symbol_union():
    provider = _Provider()
    loader = OutcomePriceLoader(provider=provider)

    result = loader.load(
        OutcomePriceRequest(
            candidate_symbol="aapl",
            snapshot_type="pre_open",
            decision_time=datetime(2026, 7, 2, 13, 0, tzinfo=timezone.utc),
            horizon_end_at=datetime(2026, 7, 7, 20, 0, tzinfo=timezone.utc),
            sector_theme_symbols=("XLK",),
            peer_symbols=("MSFT",),
            opportunity_symbols=("NVDA",),
        )
    )

    assert provider.calls == [(("AAPL", "MSFT", "NVDA", "QQQ", "SPY", "XLK"), 30)]
    assert result.requested_symbols == ("AAPL", "MSFT", "NVDA", "QQQ", "SPY", "XLK")
    assert result.missing_symbols == ()
    assert result.metadata_json == {
        "provider": "fake_alpaca",
        "feed": "unknown",
        "adjustment": "provider_split_adjusted",
        "resolution": "1Day",
    }


def test_loader_reports_missing_symbols_without_fabricating_prices():
    provider = _Provider()
    loader = OutcomePriceLoader(provider=provider)

    result = loader.load(
        OutcomePriceRequest(
            candidate_symbol="AAPL",
            snapshot_type="pre_open",
            decision_time=datetime(2026, 7, 2, 13, 0, tzinfo=timezone.utc),
            horizon_end_at=datetime(2026, 7, 7, 20, 0, tzinfo=timezone.utc),
            peer_symbols=("MISSING",),
        )
    )

    assert result.missing_symbols == ("MISSING",)
    assert "MISSING" not in result.bars_by_symbol
