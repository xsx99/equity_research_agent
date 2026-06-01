from datetime import date, datetime, timezone

from src.trading.signal_sources import SourceRecord
from src.trading.signals import build_signal_snapshot


def test_build_signal_snapshot_combines_three_signal_families_and_pit_audit():
    decision_time = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    future_at = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    technical = SourceRecord(
        "AAPL",
        "technical",
        "fixture",
        "market_bars",
        "bars-1",
        available_at,
        available_at,
        available_at,
        available_at,
        {
            "bars": [
                {"date": date(2026, 5, 29), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1_000_000},
                {"date": date(2026, 5, 30), "open": 100.0, "high": 104.0, "low": 99.0, "close": 103.0, "volume": 2_000_000},
            ],
            "benchmark_returns": {"SPY": 0.01},
        },
    )
    fundamental = SourceRecord(
        "AAPL",
        "fundamental",
        "fixture",
        "fundamental_snapshots",
        "fund-1",
        available_at,
        available_at,
        available_at,
        available_at,
        {"market_cap": 2_000_000_000_000, "revenue_growth_score": 0.6},
    )
    event = SourceRecord(
        "AAPL",
        "events_news",
        "fixture",
        "event_news_items",
        "event-1",
        available_at,
        available_at,
        available_at,
        available_at,
        {"event_type": "analyst_upgrade", "sentiment": "positive", "importance": "high"},
    )
    future_event = SourceRecord(
        "AAPL",
        "events_news",
        "fixture",
        "event_news_items",
        "future-event",
        future_at,
        future_at,
        future_at,
        future_at,
        {"event_type": "guidance_raise", "sentiment": "positive", "importance": "high"},
    )

    snapshot = build_signal_snapshot(
        ticker="AAPL",
        decision_time=decision_time,
        source_records=[technical, fundamental, event, future_event],
        snapshot_type="pre_open",
    )

    assert snapshot.signal_json["technical"]["return_1d"] == 0.03
    assert snapshot.signal_json["technical"]["rs_vs_spy_1d"] == 0.019999999999999997
    assert snapshot.signal_json["fundamental"]["market_cap_bucket"] == "mega"
    assert snapshot.signal_json["events_news"]["high_signal_news_count_24h"] == 1
    assert "option_chain_availability" in snapshot.missing_signals_json
    assert snapshot.excluded_future_source_count == 1
    assert snapshot.point_in_time_passed is True
    assert snapshot.max_input_available_for_decision_at == available_at
