"""Structured social/policy signal extraction from normalized source rows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.trading.signals.sources import SourceRecord


REQUIRED_SOCIAL_MACRO_FIELDS = (
    "trump_update_count_24h",
    "official_update_count_24h",
    "geopolitical_risk_count_24h",
    "social_macro_sentiment_direction",
    "policy_headwind_flag",
    "policy_tailwind_flag",
    "explicit_ticker_mention_flag",
    "explicit_theme_mention_flag",
    "social_macro_importance_score",
    "latest_social_macro_category",
    "latest_social_macro_published_at",
)


@dataclass(frozen=True)
class SocialMacroSignals:
    values: dict[str, Any]
    missing: tuple[str, ...]
    stale: tuple[str, ...] = ()


def build_social_macro_signals(
    records: list[SourceRecord] | tuple[SourceRecord, ...],
    *,
    decision_time: datetime,
) -> SocialMacroSignals:
    """Aggregate normalized social/policy rows into deterministic trading signals."""
    if not records:
        return SocialMacroSignals(values={}, missing=REQUIRED_SOCIAL_MACRO_FIELDS)

    cutoff = decision_time - timedelta(hours=24)
    values: dict[str, Any] = {
        "trump_update_count_24h": 0,
        "official_update_count_24h": 0,
        "geopolitical_risk_count_24h": 0,
        "social_macro_sentiment_direction": None,
        "policy_headwind_flag": False,
        "policy_tailwind_flag": False,
        "explicit_ticker_mention_flag": False,
        "explicit_theme_mention_flag": False,
        "social_macro_importance_score": None,
        "latest_social_macro_category": None,
        "latest_social_macro_published_at": None,
    }
    sentiment_score = 0
    max_importance_score: float | None = None
    latest_record: SourceRecord | None = None

    for record in records:
        payload = dict(record.payload or {})
        latest_record = record if latest_record is None or record.published_at > latest_record.published_at else latest_record
        if record.published_at < cutoff:
            continue
        category = str(payload.get("category") or "")
        if category == "trump_update":
            values["trump_update_count_24h"] += 1
        elif category == "official_update":
            values["official_update_count_24h"] += 1
        elif category == "geopolitical_news":
            values["geopolitical_risk_count_24h"] += 1
        sentiment = payload.get("sentiment_direction")
        if sentiment == "positive":
            sentiment_score += 1
        elif sentiment == "negative":
            sentiment_score -= 1
        values["policy_headwind_flag"] = values["policy_headwind_flag"] or bool(payload.get("policy_headwind_flag"))
        values["policy_tailwind_flag"] = values["policy_tailwind_flag"] or bool(payload.get("policy_tailwind_flag"))
        values["explicit_ticker_mention_flag"] = values["explicit_ticker_mention_flag"] or bool(payload.get("explicit_ticker_mention_flag"))
        values["explicit_theme_mention_flag"] = values["explicit_theme_mention_flag"] or bool(payload.get("explicit_theme_mention_flag"))
        importance = payload.get("importance_score")
        if isinstance(importance, (int, float)):
            max_importance_score = float(importance) if max_importance_score is None else max(max_importance_score, float(importance))

    if sentiment_score > 0:
        values["social_macro_sentiment_direction"] = "positive"
    elif sentiment_score < 0:
        values["social_macro_sentiment_direction"] = "negative"
    elif any(values[field] > 0 for field in ("trump_update_count_24h", "official_update_count_24h", "geopolitical_risk_count_24h")):
        values["social_macro_sentiment_direction"] = "neutral"

    values["social_macro_importance_score"] = max_importance_score
    if latest_record is not None:
        latest_payload = dict(latest_record.payload or {})
        values["latest_social_macro_category"] = latest_payload.get("category")
        values["latest_social_macro_published_at"] = latest_record.published_at.isoformat()

    missing = tuple(field for field in REQUIRED_SOCIAL_MACRO_FIELDS if values.get(field) is None)
    return SocialMacroSignals(values=values, missing=missing)
