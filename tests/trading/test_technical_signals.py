from datetime import date, datetime, timezone

import pytest

from src.trading.signals.sources import SourceRecord
from src.trading.signals.technical import build_technical_signals, compute_relative_strength


def test_technical_signals_build_price_volume_and_relative_strength_fields():
    available_at = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    record = SourceRecord(
        ticker="AAPL",
        source_family="technical",
        source="fixture",
        source_table="market_bars",
        source_record_id="bars-1",
        event_time=available_at,
        published_at=available_at,
        ingested_at=available_at,
        available_for_decision_at=available_at,
        payload={
            "bars": [
                {"date": date(2026, 5, 27), "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1_000_000},
                {"date": date(2026, 5, 28), "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1_100_000},
                {"date": date(2026, 5, 29), "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 1_200_000},
                {"date": date(2026, 6, 1), "open": 102.0, "high": 106.0, "low": 101.0, "close": 105.0, "volume": 2_000_000},
            ],
            "benchmark_returns": {"SPY": 0.01, "QQQ": 0.02},
            "premarket_gap_pct": 0.015,
        },
    )

    signals = build_technical_signals([record])

    assert signals.values["last_price"] == pytest.approx(105.0)
    assert signals.values["return_1d"] == pytest.approx(3 / 102)
    assert signals.values["return_5d"] is None
    assert signals.values["rs_vs_spy_1d"] == pytest.approx((3 / 102) - 0.01)
    assert signals.values["rs_vs_qqq_1d"] == pytest.approx((3 / 102) - 0.02)
    assert signals.values["relative_volume"] == pytest.approx(2_000_000 / 1_100_000)
    assert signals.values["dollar_volume"] == pytest.approx(105.0 * 2_000_000)
    assert signals.values["premarket_gap_pct"] == pytest.approx(0.015)
    assert "return_5d" in signals.missing


def test_compute_relative_strength_subtracts_benchmark_return_from_ticker_return():
    assert compute_relative_strength(0.12, 0.05) == pytest.approx(0.07)
