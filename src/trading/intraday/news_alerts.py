"""Normalized intraday news alerts for PR8."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.trading.signals.sources import EventNewsItemRecord


@dataclass(frozen=True)
class NewsAlertRecord:
    """Normalized alert artifact derived from event/news items."""

    news_alert_id: str
    ticker: str
    source_ticker: str | None
    alert_type: str
    sentiment: str | None
    severity: str
    source: str
    published_at: datetime
    headline: str | None
    summary: str | None
    strategy_relevance: tuple[str, ...]
    affected_positions: tuple[str, ...]
    affected_candidates: tuple[str, ...]
    affected_themes: tuple[str, ...]
    readthrough_source_ticker: str | None
    action_required: bool
    dedupe_key: str
    event_news_item_id: str
    metadata_json: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class NewsAlertService:
    """Convert scoped event/news rows into deduped intraday alerts."""

    def build_alerts(
        self,
        *,
        event_items: tuple[EventNewsItemRecord, ...] | list[EventNewsItemRecord],
        existing_dedupe_keys: frozenset[str],
        affected_positions_by_ticker: dict[str, tuple[str, ...]],
        affected_candidates_by_ticker: dict[str, tuple[str, ...]],
        affected_themes_by_ticker: dict[str, tuple[str, ...]],
    ) -> tuple[NewsAlertRecord, ...]:
        alerts: list[NewsAlertRecord] = []
        seen = set(existing_dedupe_keys)
        for item in sorted(event_items, key=lambda current: (current.published_at, current.event_news_item_id)):
            if item.dedupe_key in seen:
                continue
            seen.add(item.dedupe_key)
            ticker = item.ticker.strip().upper()
            strategy_relevance = tuple(item.metadata_json.get("strategy_relevance", ()))
            affected_positions = tuple(affected_positions_by_ticker.get(ticker, ()))
            affected_candidates = tuple(affected_candidates_by_ticker.get(ticker, ()))
            affected_themes = tuple(affected_themes_by_ticker.get(ticker, ()))
            severity = _classify_severity(item)
            alerts.append(
                NewsAlertRecord(
                    news_alert_id=str(uuid.uuid4()),
                    ticker=ticker,
                    source_ticker=item.source_ticker,
                    alert_type=item.event_type,
                    sentiment=item.sentiment,
                    severity=severity,
                    source=item.provider,
                    published_at=item.published_at,
                    headline=item.headline,
                    summary=item.summary,
                    strategy_relevance=strategy_relevance,
                    affected_positions=affected_positions,
                    affected_candidates=affected_candidates,
                    affected_themes=affected_themes,
                    readthrough_source_ticker=item.source_ticker if item.source_ticker != ticker else None,
                    action_required=severity in {"critical", "high"},
                    dedupe_key=item.dedupe_key,
                    event_news_item_id=item.event_news_item_id,
                    metadata_json=dict(item.metadata_json),
                    created_at=item.available_for_decision_at,
                )
            )
        return tuple(alerts)


def _classify_severity(item: EventNewsItemRecord) -> str:
    importance = str(item.importance or "").lower()
    event_type = str(item.event_type or "").lower()
    if importance == "critical" or "bankruptcy" in event_type:
        return "critical"
    if importance == "high":
        return "high"
    if importance == "medium":
        return "medium"
    return "low"
