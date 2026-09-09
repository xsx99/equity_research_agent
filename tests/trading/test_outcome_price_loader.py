from datetime import date, datetime, timezone

from src.trading.outcomes.prices import OutcomePriceLoader, OutcomePriceRequest


class _Provider:
    provider_name = "fake_alpaca"

    def __init__(self) -> None:
        self.calls = []

    def fetch_daily_bars_for_symbols_range(self, symbols, *, start, end):
        self.calls.append((tuple(symbols), start, end))
        return {
            symbol: [
                {"date": date(2026, 7, 2), "open": 100, "high": 104, "low": 99, "close": 102},
                {"date": date(2026, 7, 7), "open": 103, "high": 108, "low": 102, "close": 107},
            ]
            for symbol in symbols
            if symbol != "MISSING"
        }

    def fetch_minute_bars_for_symbols_range(self, symbols, *, start, end):
        self.calls.append(("minute", tuple(symbols), start, end))
        return {
            symbol: [
                {
                    "timestamp": datetime(2026, 7, 2, 15, 1, tzinfo=timezone.utc),
                    "open": 101,
                    "high": 102,
                    "low": 100,
                    "close": 101.5,
                }
            ]
            for symbol in symbols
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

    assert provider.calls == [
        (
            ("AAPL", "MSFT", "NVDA", "QQQ", "SPY", "XLK"),
            datetime(2026, 7, 2, 13, 30, tzinfo=timezone.utc),
            datetime(2026, 7, 7, 20, 0, tzinfo=timezone.utc),
        )
    ]
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


def test_intraday_loader_uses_first_minute_at_or_after_decision_time():
    provider = _Provider()
    loader = OutcomePriceLoader(provider=provider)
    decision_time = datetime(2026, 7, 2, 15, 0, 30, tzinfo=timezone.utc)

    result = loader.load(
        OutcomePriceRequest(
            candidate_symbol="AAPL",
            snapshot_type="intraday",
            decision_time=decision_time,
            horizon_end_at=datetime(2026, 7, 7, 20, 0, tzinfo=timezone.utc),
        )
    )

    minute_call = provider.calls[1]
    assert minute_call == (
        "minute",
        ("AAPL", "QQQ", "SPY"),
        decision_time,
        datetime(2026, 7, 2, 20, 0, tzinfo=timezone.utc),
    )
    assert result.start_prices_by_symbol["AAPL"] == 101
