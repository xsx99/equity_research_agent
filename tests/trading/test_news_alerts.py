from __future__ import annotations

from datetime import datetime, timezone

from src.trading.intraday.news_alerts import NewsAlertService
from src.trading.signals.sources import EventNewsItemRecord


def _event(
    *,
    event_news_item_id: str,
    headline: str,
    published_at: datetime,
    dedupe_key: str,
) -> EventNewsItemRecord:
    return EventNewsItemRecord(
        event_news_item_id=event_news_item_id,
        ticker="NVDA",
        source_ticker="NVDA",
        event_type="earnings_beat_raise",
        direction="bullish",
        sentiment="positive",
        importance="high",
        headline=headline,
        summary="Beat and raise guidance.",
        provider="fixture",
        source_refs_json=[{"source": "fixture", "source_table": "event_news_items", "source_record_id": event_news_item_id}],
        dedupe_key=dedupe_key,
        event_time=published_at,
        published_at=published_at,
        ingested_at=published_at,
        available_for_decision_at=published_at,
        raw_payload_ref=None,
        metadata_json={"strategy_relevance": ["earnings_drift_v1", "gap_and_go_v1"]},
    )


def test_news_alert_service_normalizes_and_dedupes_repeated_headlines():
    now = datetime(2026, 6, 2, 15, 0, tzinfo=timezone.utc)
    service = NewsAlertService()

    first = _event(
        event_news_item_id="event-1",
        headline="NVDA rises after earnings beat and raised guidance",
        published_at=now,
        dedupe_key="NVDA|earnings_beat_raise|2026-06-02T15:00:00+00:00",
    )
    duplicate = _event(
        event_news_item_id="event-2",
        headline="NVDA rises after earnings beat and raised guidance",
        published_at=now,
        dedupe_key="NVDA|earnings_beat_raise|2026-06-02T15:00:00+00:00",
    )

    alerts = service.build_alerts(
        event_items=(first, duplicate),
        existing_dedupe_keys=frozenset(),
        affected_positions_by_ticker={"NVDA": ("position-1",)},
        affected_candidates_by_ticker={"NVDA": ("candidate-1",)},
        affected_themes_by_ticker={"NVDA": ("ai_semis",)},
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.ticker == "NVDA"
    assert alert.alert_type == "earnings_beat_raise"
    assert alert.sentiment == "positive"
    assert alert.severity == "high"
    assert alert.strategy_relevance == ("earnings_drift_v1", "gap_and_go_v1")
    assert alert.affected_positions == ("position-1",)
    assert alert.affected_candidates == ("candidate-1",)
    assert alert.affected_themes == ("ai_semis",)
    assert alert.action_required is True


def test_news_alert_service_keeps_distinct_alerts_for_new_fact_rewrites():
    now = datetime(2026, 6, 2, 15, 0, tzinfo=timezone.utc)
    service = NewsAlertService()

    first = _event(
        event_news_item_id="event-1",
        headline="NVDA wins large cloud order",
        published_at=now,
        dedupe_key="NVDA|customer_order|cloud-order|2026-06-02T12:00:00+00:00",
    )
    second = _event(
        event_news_item_id="event-2",
        headline="NVDA wins larger cloud order after FDA approval",
        published_at=now,
        dedupe_key="NVDA|regulatory_action|cloud-order-approved|2026-06-02T12:00:00+00:00",
    )

    alerts = service.build_alerts(
        event_items=(first, second),
        existing_dedupe_keys=frozenset(),
        affected_positions_by_ticker={"NVDA": ("position-1",)},
        affected_candidates_by_ticker={"NVDA": ("candidate-1",)},
        affected_themes_by_ticker={"NVDA": ("ai_semis",)},
    )

    assert [alert.event_news_item_id for alert in alerts] == ["event-1", "event-2"]
