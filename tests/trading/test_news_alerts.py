from __future__ import annotations

from datetime import datetime, timezone

from src.trading.intraday.news_alerts import AlertSourceItem, NewsAlertService


def _alert_item(
    *,
    alert_item_id: str,
    source_family: str,
    alert_type: str,
    headline: str,
    published_at: datetime,
    dedupe_key: str,
    sentiment: str = "positive",
    importance: str = "high",
    importance_score: float | None = None,
) -> AlertSourceItem:
    return AlertSourceItem(
        alert_item_id=alert_item_id,
        ticker="NVDA",
        source_ticker="NVDA",
        source_family=source_family,
        alert_type=alert_type,
        direction="bullish",
        sentiment=sentiment,
        importance=importance,
        importance_score=importance_score,
        headline=headline,
        summary="Beat and raise guidance.",
        provider="fixture",
        dedupe_key=dedupe_key,
        published_at=published_at,
        available_for_decision_at=published_at,
        metadata_json={
            "strategy_relevance": ["earnings_drift_v1", "gap_and_go_v1"],
            "source_record_id": alert_item_id,
        },
    )


def test_news_alert_service_normalizes_and_dedupes_repeated_headlines():
    now = datetime(2026, 6, 2, 15, 0, tzinfo=timezone.utc)
    service = NewsAlertService()

    first = _alert_item(
        alert_item_id="event-1",
        source_family="events_news",
        alert_type="earnings_beat_raise",
        headline="NVDA rises after earnings beat and raised guidance",
        published_at=now,
        dedupe_key="NVDA|earnings_beat_raise|2026-06-02T15:00:00+00:00",
    )
    duplicate = _alert_item(
        alert_item_id="event-2",
        source_family="events_news",
        alert_type="earnings_beat_raise",
        headline="NVDA rises after earnings beat and raised guidance",
        published_at=now,
        dedupe_key="NVDA|earnings_beat_raise|2026-06-02T15:00:00+00:00",
    )

    alerts = service.build_alerts(
        source_items=(first, duplicate),
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
    assert alert.metadata_json["source_family"] == "events_news"
    assert alert.event_news_item_id == "event-1"


def test_news_alert_service_keeps_distinct_alerts_for_new_fact_rewrites():
    now = datetime(2026, 6, 2, 15, 0, tzinfo=timezone.utc)
    service = NewsAlertService()

    first = _alert_item(
        alert_item_id="event-1",
        source_family="events_news",
        alert_type="customer_order",
        headline="NVDA wins large cloud order",
        published_at=now,
        dedupe_key="NVDA|customer_order|cloud-order|2026-06-02T12:00:00+00:00",
    )
    second = _alert_item(
        alert_item_id="event-2",
        source_family="events_news",
        alert_type="regulatory_action",
        headline="NVDA wins larger cloud order after FDA approval",
        published_at=now,
        dedupe_key="NVDA|regulatory_action|cloud-order-approved|2026-06-02T12:00:00+00:00",
    )

    alerts = service.build_alerts(
        source_items=(first, second),
        existing_dedupe_keys=frozenset(),
        affected_positions_by_ticker={"NVDA": ("position-1",)},
        affected_candidates_by_ticker={"NVDA": ("candidate-1",)},
        affected_themes_by_ticker={"NVDA": ("ai_semis",)},
    )

    assert [alert.event_news_item_id for alert in alerts] == ["event-1", "event-2"]


def test_news_alert_service_emits_social_macro_alerts_with_provenance():
    now = datetime(2026, 6, 2, 15, 0, tzinfo=timezone.utc)
    service = NewsAlertService()

    item = _alert_item(
        alert_item_id="social-1",
        source_family="social_macro",
        alert_type="trump_update",
        headline="Trump threatens new AI chip export restrictions",
        published_at=now,
        dedupe_key="NVDA|trump_update|chip-export|2026-06-02T15:00:00+00:00",
        sentiment="negative",
        importance="high",
        importance_score=0.93,
    )
    item.metadata_json["theme_tags"] = ["ai_semis"]

    alerts = service.build_alerts(
        source_items=(item,),
        existing_dedupe_keys=frozenset(),
        affected_positions_by_ticker={"NVDA": ("position-1",)},
        affected_candidates_by_ticker={"NVDA": ("candidate-1",)},
        affected_themes_by_ticker={"NVDA": ("ai_semis",)},
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.event_news_item_id is None
    assert alert.alert_type == "trump_update"
    assert alert.severity == "high"
    assert alert.action_required is True
    assert alert.metadata_json["source_family"] == "social_macro"
    assert alert.metadata_json["source_record_id"] == "social-1"
    assert alert.metadata_json["importance_score"] == 0.93
    assert alert.affected_themes == ("ai_semis",)
