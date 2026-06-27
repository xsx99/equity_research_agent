"""Evidence and support helpers for option strategy payload construction."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from src.trading.signals.sources import EventNewsItemRecord


def _render_news_source_text(item: EventNewsItemRecord) -> str:
    parts = [part.strip() for part in (item.headline, item.summary) if isinstance(part, str) and part.strip()]
    return "\n\n".join(parts)


_WINDOWED_EVENT_NEWS_FIELDS = (
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

_EVIDENCE_IMPORTANCE_PRIORITY = {"critical": 0, "high": 1, "medium": 2, "normal": 3, "low": 4}


def _news_evidence_limit() -> int:
    raw = os.getenv("TRADING_NEWS_EVIDENCE_LIMIT", "4").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 4


def _evidence_priority(item: EventNewsItemRecord) -> tuple[int, int, datetime, str]:
    importance_rank = _EVIDENCE_IMPORTANCE_PRIORITY.get(str(item.importance or "").casefold(), 5)
    specificity = int(item.metadata_json.get("specificity_score", 0))
    return (
        importance_rank,
        -specificity,
        item.available_for_decision_at,
        item.event_news_item_id,
    )


def _round_nested_floats(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, list):
        return [_round_nested_floats(item) for item in value]
    if isinstance(value, tuple):
        return [_round_nested_floats(item) for item in value]
    if isinstance(value, dict):
        return {key: _round_nested_floats(item) for key, item in value.items()}
    return value
