"""Canonical event-calendar contracts."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class CalendarEventRecord:
    """Normalized future macro, company, and market-structure events."""

    calendar_event_id: str
    event_key: str
    event_type: str
    ticker: str | None
    event_time: datetime
    published_at: datetime | None
    available_for_decision_at: datetime
    title: str
    severity_hint: str
    source: str
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.ticker is not None:
            object.__setattr__(self, "ticker", self.ticker.strip().upper())
        if self.published_at is not None and self.available_for_decision_at < self.published_at:
            raise ValueError("available_for_decision_at cannot be earlier than published_at")


class CalendarEventPipeline:
    """Normalize earnings, macro, option expiry, and readthrough events."""

    def __init__(self, *, now: callable | None = None) -> None:
        self.now = now or (lambda: datetime.now(timezone.utc))

    def build_events(
        self,
        *,
        ticker: str,
        decision_time: datetime,
        earnings_in_days: int | None = None,
        macro_events: tuple[dict[str, Any], ...] = (),
        option_expiry_dates: tuple[date, ...] = (),
        company_event_payloads: tuple[dict[str, Any], ...] = (),
        readthrough_events: tuple[object, ...] = (),
    ) -> tuple[CalendarEventRecord, ...]:
        symbol = ticker.strip().upper()
        events: list[CalendarEventRecord] = []
        for payload in company_event_payloads:
            published_at = payload.get("published_at") or decision_time
            event_key = f"company:{symbol}:{payload['event_type']}:{published_at.isoformat()}"
            events.append(
                CalendarEventRecord(
                    calendar_event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, event_key)),
                    event_key=event_key,
                    event_type="company_specific",
                    ticker=symbol,
                    event_time=published_at,
                    published_at=published_at,
                    available_for_decision_at=published_at,
                    title=str(payload.get("title") or payload["event_type"]),
                    severity_hint=str(payload.get("severity_hint") or "medium"),
                    source=str(payload.get("source") or "company_event"),
                    metadata_json={"raw_event_type": payload["event_type"]},
                )
            )
        for readthrough in readthrough_events:
            events.append(
                CalendarEventRecord(
                    calendar_event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, str(getattr(readthrough, "event_key", "")))),
                    event_key=str(getattr(readthrough, "event_key")),
                    event_type="readthrough",
                    ticker=getattr(readthrough, "affected_ticker", None),
                    event_time=getattr(readthrough, "event_time"),
                    published_at=getattr(readthrough, "published_at"),
                    available_for_decision_at=getattr(readthrough, "available_for_decision_at"),
                    title=str(getattr(readthrough, "title")),
                    severity_hint="medium",
                    source=str(getattr(readthrough, "source")),
                    metadata_json=dict(getattr(readthrough, "metadata_json", {}) or {}),
                )
            )
        if earnings_in_days is not None and earnings_in_days >= 0:
            event_date = decision_time.date() + timedelta(days=earnings_in_days)
            event_time = datetime.combine(event_date, time(20, 0), tzinfo=timezone.utc)
            event_key = f"earnings:{symbol}:{event_date.isoformat()}"
            events.append(
                CalendarEventRecord(
                    calendar_event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, event_key)),
                    event_key=event_key,
                    event_type="earnings",
                    ticker=symbol,
                    event_time=event_time,
                    published_at=decision_time,
                    available_for_decision_at=decision_time,
                    title=f"{symbol} earnings",
                    severity_hint="high",
                    source="fundamental_context",
                    metadata_json={},
                )
            )
        for payload in macro_events:
            event_time = payload["event_time"]
            event_code = str(payload["event_code"]).lower()
            event_key = f"macro:{event_code}:{event_time.date().isoformat()}"
            events.append(
                CalendarEventRecord(
                    calendar_event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, event_key)),
                    event_key=event_key,
                    event_type="macro",
                    ticker=None,
                    event_time=event_time,
                    published_at=decision_time,
                    available_for_decision_at=decision_time,
                    title=str(payload["title"]),
                    severity_hint=str(payload.get("severity_hint") or "medium"),
                    source=str(payload.get("source") or "macro_calendar"),
                    metadata_json={"event_code": event_code},
                )
            )
        for expiry_date in option_expiry_dates:
            event_key = f"option_expiry:{symbol}:{expiry_date.isoformat()}"
            events.append(
                CalendarEventRecord(
                    calendar_event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, event_key)),
                    event_key=event_key,
                    event_type="option_expiry",
                    ticker=symbol,
                    event_time=datetime.combine(expiry_date, time(20, 0), tzinfo=timezone.utc),
                    published_at=decision_time,
                    available_for_decision_at=decision_time,
                    title=f"{symbol} option expiry",
                    severity_hint="medium",
                    source="options_calendar",
                    metadata_json={},
                )
            )
        deduped = {event.event_key: event for event in events}
        priority = {
            "company_specific": 0,
            "readthrough": 1,
            "earnings": 2,
            "macro": 3,
            "option_expiry": 4,
        }
        return tuple(
            sorted(
                deduped.values(),
                key=lambda item: (priority.get(item.event_type, 99), item.event_time, item.event_key),
            )
        )
