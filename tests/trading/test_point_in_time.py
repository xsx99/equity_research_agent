from datetime import datetime, timezone

from src.trading.point_in_time import filter_point_in_time_records
from src.trading.signal_sources import SourceRecord


def _record(ticker: str, family: str, record_id: str, available_at: datetime) -> SourceRecord:
    return SourceRecord(
        ticker=ticker,
        source_family=family,
        source="fixture",
        source_table=f"{family}_fixture",
        source_record_id=record_id,
        event_time=available_at,
        published_at=available_at,
        ingested_at=available_at,
        available_for_decision_at=available_at,
        payload={"value": record_id},
    )


def test_point_in_time_filter_excludes_future_market_bar_records():
    decision_time = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    available = _record("AAPL", "technical", "bar-old", datetime(2026, 6, 1, 11, 0, tzinfo=timezone.utc))
    future = _record("AAPL", "technical", "bar-future", datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc))

    audit = filter_point_in_time_records([available, future], decision_time)

    assert audit.records == (available,)
    assert audit.excluded_future_source_count == 1
    assert audit.point_in_time_passed is True
    assert audit.max_input_available_for_decision_at == available.available_for_decision_at


def test_point_in_time_filter_excludes_future_fundamental_records():
    decision_time = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    available = _record("NVDA", "fundamental", "fund-old", datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc))
    future = _record("NVDA", "fundamental", "fund-future", datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))

    audit = filter_point_in_time_records([available, future], decision_time)

    assert audit.records == (available,)
    assert audit.source_record_refs == ({"source": "fixture", "source_table": "fundamental_fixture", "source_record_id": "fund-old"},)


def test_point_in_time_filter_excludes_future_event_news_records():
    decision_time = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    available = _record("MSFT", "events_news", "news-old", datetime(2026, 6, 1, 11, 55, tzinfo=timezone.utc))
    future = _record("MSFT", "events_news", "news-future", datetime(2026, 6, 1, 12, 5, tzinfo=timezone.utc))

    audit = filter_point_in_time_records([available, future], decision_time)

    assert audit.records == (available,)
    assert audit.excluded_future_source_count == 1
    assert audit.source_available_times == {"news-old": available.available_for_decision_at.isoformat()}
