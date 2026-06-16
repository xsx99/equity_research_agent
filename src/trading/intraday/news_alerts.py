"""Normalized intraday news alerts for PR8."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

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
    event_news_item_id: str | None
    metadata_json: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class AlertSourceItem:
    """Common alert-source contract shared by event/news and social/macro rows."""

    alert_item_id: str
    ticker: str
    source_ticker: str | None
    source_family: str
    alert_type: str
    direction: str | None
    sentiment: str | None
    importance: str | None
    importance_score: float | None
    headline: str | None
    summary: str | None
    provider: str
    dedupe_key: str
    published_at: datetime
    available_for_decision_at: datetime
    metadata_json: dict[str, object] = field(default_factory=dict)


class NewsAlertService:
    """Convert scoped alert-source rows into deduped intraday alerts."""

    def build_alerts(
        self,
        *,
        source_items: tuple[AlertSourceItem, ...] | list[AlertSourceItem],
        existing_dedupe_keys: frozenset[str],
        affected_positions_by_ticker: dict[str, tuple[str, ...]],
        affected_candidates_by_ticker: dict[str, tuple[str, ...]],
        affected_themes_by_ticker: dict[str, tuple[str, ...]],
    ) -> tuple[NewsAlertRecord, ...]:
        alerts: list[NewsAlertRecord] = []
        seen = set(existing_dedupe_keys)
        for item in sorted(source_items, key=lambda current: (current.published_at, current.alert_item_id)):
            if item.dedupe_key in seen:
                continue
            seen.add(item.dedupe_key)
            ticker = item.ticker.strip().upper()
            strategy_relevance = tuple(item.metadata_json.get("strategy_relevance", ()))
            affected_positions = tuple(affected_positions_by_ticker.get(ticker, ()))
            affected_candidates = tuple(affected_candidates_by_ticker.get(ticker, ()))
            affected_themes = _merge_themes(
                affected_themes_by_ticker.get(ticker, ()),
                item.metadata_json.get("theme_tags", ()),
            )
            severity = classify_source_item_severity(item)
            metadata_json = {
                **dict(item.metadata_json),
                "source_family": item.source_family,
                "source_record_id": item.alert_item_id,
            }
            if item.importance_score is not None:
                metadata_json["importance_score"] = float(item.importance_score)
            alerts.append(
                NewsAlertRecord(
                    news_alert_id=str(uuid.uuid4()),
                    ticker=ticker,
                    source_ticker=item.source_ticker,
                    alert_type=item.alert_type,
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
                    event_news_item_id=item.alert_item_id if item.source_family == "events_news" else None,
                    metadata_json=metadata_json,
                    created_at=item.available_for_decision_at,
                )
            )
        return tuple(alerts)


def classify_source_item_severity(item: AlertSourceItem) -> str:
    importance = str(item.importance or "").lower()
    alert_type = str(item.alert_type or "").lower()
    if importance == "critical" or "bankruptcy" in alert_type:
        return "critical"
    if importance == "high":
        return "high"
    if importance == "medium":
        return "medium"
    if item.importance_score is not None and float(item.importance_score) >= 0.85:
        return "high"
    if item.importance_score is not None and float(item.importance_score) >= 0.5:
        return "medium"
    return "low"


def _merge_themes(left: object, right: object) -> tuple[str, ...]:
    merged: list[str] = []
    for collection in (left, right):
        if not isinstance(collection, (list, tuple, set)):
            continue
        for value in collection:
            normalized = str(value or "").strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
    return tuple(merged)
