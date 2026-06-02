from datetime import datetime, timezone

from src.trading.signals.fundamental import build_fundamental_signals
from src.trading.signals.sources import SourceRecord


def test_fundamental_signals_use_latest_available_snapshot_and_mark_missing_fields():
    available_at = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    record = SourceRecord(
        ticker="AAPL",
        source_family="fundamental",
        source="fixture",
        source_table="fundamental_snapshots",
        source_record_id="fund-1",
        event_time=available_at,
        published_at=available_at,
        ingested_at=available_at,
        available_for_decision_at=available_at,
        payload={
            "market_cap": 2_900_000_000_000,
            "revenue_growth_score": 0.7,
            "margin_trend_score": 0.4,
            "quality_score": 0.8,
            "valuation_percentile": 0.76,
        },
    )

    signals = build_fundamental_signals([record])

    assert signals.values["market_cap_bucket"] == "mega"
    assert signals.values["revenue_growth_score"] == 0.7
    assert "short_interest_bucket" in signals.missing
