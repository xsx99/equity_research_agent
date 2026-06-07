"""Structured event/news signal extraction for PR02."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.trading.signals.sources import SourceRecord

_NEGATIVE_CATALYST_PRECEDENCE = {
    "bankruptcy": 7,
    "fraud": 6,
    "offering": 5,
    "guidance_cut": 4,
    "regulatory_action": 3,
    "regulatory_probe": 3,
    "litigation": 2,
    "recall": 1,
}


REQUIRED_EVENT_NEWS_FIELDS = (
    "earnings_in_days",
    "known_event_date",
    "own_earnings_event_type",
    "analyst_upgrade_count",
    "analyst_downgrade_count",
    "price_target_revision_score",
    "guidance_news_flag",
    "customer_order_news_flag",
    "regulatory_news_flag",
    "high_signal_news_count_24h",
    "high_signal_news_count_7d",
    "sentiment_direction",
    "catalyst_quality_score",
    "direct_negative_catalyst_type",
)


@dataclass(frozen=True)
class EventNewsSignals:
    values: dict[str, Any]
    missing: tuple[str, ...]
    stale: tuple[str, ...] = ()


def build_event_news_signals(
    records: list[SourceRecord] | tuple[SourceRecord, ...],
    *,
    decision_time: datetime,
) -> EventNewsSignals:
    """Aggregate headline/calendar/provider-event rows into MVP event signals."""
    values: dict[str, Any] = {
        "earnings_in_days": None,
        "known_event_date": None,
        "own_earnings_event_type": None,
        "analyst_upgrade_count": 0,
        "analyst_downgrade_count": 0,
        "price_target_revision_score": 0,
        "guidance_news_flag": False,
        "customer_order_news_flag": False,
        "regulatory_news_flag": False,
        "high_signal_news_count_24h": 0,
        "high_signal_news_count_7d": 0,
        "sentiment_direction": None,
        "catalyst_quality_score": None,
        "direct_negative_catalyst_type": None,
    }
    sentiment_score = 0
    high_importance_count = 0
    negative_catalyst_type: str | None = None
    negative_catalyst_rank = -1

    for record in records:
        payload = record.payload
        event_type = str(payload.get("event_type") or "")
        sentiment = str(payload.get("sentiment") or payload.get("direction") or "")
        importance = str(payload.get("importance") or "")
        if payload.get("earnings_in_days") is not None:
            values["earnings_in_days"] = payload["earnings_in_days"]
        if payload.get("known_event_date") is not None:
            values["known_event_date"] = payload["known_event_date"]
        if event_type.startswith("own_earnings"):
            values["own_earnings_event_type"] = event_type
        if event_type == "analyst_upgrade":
            values["analyst_upgrade_count"] += 1
        if event_type == "analyst_downgrade":
            values["analyst_downgrade_count"] += 1
        if event_type == "price_target_revision":
            values["price_target_revision_score"] += float(payload.get("score", 1))
        if "guidance" in event_type:
            values["guidance_news_flag"] = True
        if event_type in {"customer_order", "customer_win", "product_launch"}:
            values["customer_order_news_flag"] = True
        if "regulatory" in event_type:
            values["regulatory_news_flag"] = True
        if importance in {"high", "critical"}:
            high_importance_count += 1
            if decision_time - record.published_at <= timedelta(hours=24):
                values["high_signal_news_count_24h"] += 1
            if decision_time - record.published_at <= timedelta(days=7):
                values["high_signal_news_count_7d"] += 1
        if sentiment == "positive":
            sentiment_score += 1
        elif sentiment == "negative":
            sentiment_score -= 1
            rank = _NEGATIVE_CATALYST_PRECEDENCE.get(event_type, 0)
            if rank > negative_catalyst_rank:
                negative_catalyst_rank = rank
                negative_catalyst_type = event_type

    if sentiment_score > 0:
        values["sentiment_direction"] = "positive"
    elif sentiment_score < 0:
        values["sentiment_direction"] = "negative"
    elif records:
        values["sentiment_direction"] = "neutral"
    if records:
        values["catalyst_quality_score"] = min(high_importance_count / max(len(records), 1), 1.0)
    values["direct_negative_catalyst_type"] = negative_catalyst_type

    missing = tuple(
        field for field in REQUIRED_EVENT_NEWS_FIELDS
        if values.get(field) is None
    )
    return EventNewsSignals(values=values, missing=missing)
