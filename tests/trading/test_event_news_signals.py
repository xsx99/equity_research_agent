from datetime import datetime, timedelta, timezone

from src.trading.signals.event_news import build_event_news_signals
from src.trading.signals.sources import SourceRecord


def test_event_news_signals_count_high_signal_news_and_direct_negative_catalyst():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    records = [
        SourceRecord(
            ticker="AAPL",
            source_family="events_news",
            source="fixture",
            source_table="event_news_items",
            source_record_id="positive",
            event_time=now - timedelta(hours=2),
            published_at=now - timedelta(hours=2),
            ingested_at=now - timedelta(hours=2),
            available_for_decision_at=now - timedelta(hours=2),
            payload={"event_type": "analyst_upgrade", "sentiment": "positive", "importance": "high"},
        ),
        SourceRecord(
            ticker="AAPL",
            source_family="events_news",
            source="fixture",
            source_table="event_news_items",
            source_record_id="negative",
            event_time=now - timedelta(days=3),
            published_at=now - timedelta(days=3),
            ingested_at=now - timedelta(days=3),
            available_for_decision_at=now - timedelta(days=3),
            payload={"event_type": "regulatory_probe", "sentiment": "negative", "importance": "high"},
        ),
    ]

    signals = build_event_news_signals(records, decision_time=now)

    assert signals.values["high_signal_news_count_24h"] == 1
    assert signals.values["high_signal_news_count_7d"] == 2
    assert signals.values["analyst_upgrade_count"] == 1
    assert signals.values["direct_negative_catalyst_type"] == "regulatory_probe"


def test_event_news_signals_apply_negative_catalyst_precedence():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    records = [
        SourceRecord(
            ticker="AAPL",
            source_family="events_news",
            source="fixture",
            source_table="event_news_items",
            source_record_id="guidance-cut",
            event_time=now - timedelta(hours=2),
            published_at=now - timedelta(hours=2),
            ingested_at=now - timedelta(hours=2),
            available_for_decision_at=now - timedelta(hours=2),
            payload={"event_type": "guidance_cut", "sentiment": "negative", "importance": "high"},
        ),
        SourceRecord(
            ticker="AAPL",
            source_family="events_news",
            source="fixture",
            source_table="event_news_items",
            source_record_id="bankruptcy",
            event_time=now - timedelta(hours=1),
            published_at=now - timedelta(hours=1),
            ingested_at=now - timedelta(hours=1),
            available_for_decision_at=now - timedelta(hours=1),
            payload={"event_type": "bankruptcy", "sentiment": "negative", "importance": "critical"},
        ),
        SourceRecord(
            ticker="AAPL",
            source_family="events_news",
            source="fixture",
            source_table="event_news_items",
            source_record_id="litigation",
            event_time=now - timedelta(minutes=30),
            published_at=now - timedelta(minutes=30),
            ingested_at=now - timedelta(minutes=30),
            available_for_decision_at=now - timedelta(minutes=30),
            payload={"event_type": "litigation", "sentiment": "negative", "importance": "high"},
        ),
    ]

    signals = build_event_news_signals(records, decision_time=now)

    assert signals.values["direct_negative_catalyst_type"] == "bankruptcy"


def test_event_news_signals_do_not_surface_general_news_as_direct_negative_catalyst():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    records = [
        SourceRecord(
            ticker="AAPL",
            source_family="events_news",
            source="fixture",
            source_table="event_news_items",
            source_record_id="general-news-negative",
            event_time=now - timedelta(hours=2),
            published_at=now - timedelta(hours=2),
            ingested_at=now - timedelta(hours=2),
            available_for_decision_at=now - timedelta(hours=2),
            payload={"event_type": "general_news", "sentiment": "negative", "importance": "low"},
        ),
    ]

    signals = build_event_news_signals(records, decision_time=now)

    assert signals.values["sentiment_direction"] == "negative"
    assert signals.values["direct_negative_catalyst_type"] is None
