"""FRED economic release-calendar provider."""
from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable

import httpx

from src.core.logging import get_logger


logger = get_logger(__name__)

FRED_RELEASE_DATES_URL = "https://api.stlouisfed.org/fred/releases/dates"
DEFAULT_RELEASE_TIME_UTC = time(13, 30, tzinfo=timezone.utc)

_HIGH_SIGNAL_RELEASE_IDS = {
    9,  # Advance Monthly Sales for Retail and Food Services
    10,  # Consumer Price Index
    46,  # Producer Price Index
    50,  # Employment Situation
    53,  # Gross Domestic Product
}
_MEDIUM_SIGNAL_RELEASE_IDS = {
    13,  # G.17 Industrial Production and Capacity Utilization
    27,  # New Residential Construction
    323,  # Consumer Sentiment
}


class FREDEconomicCalendar:
    """Best-effort FRED release calendar adapter for forward macro events."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        horizon_days: int = 14,
        client: httpx.Client | Any | None = None,
        row_fetcher: Callable[[date, date], list[dict[str, Any]]] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.getenv("FRED_API_KEY")
        self._horizon_days = horizon_days
        self._client = client or httpx.Client(timeout=timeout)
        self._row_fetcher = row_fetcher
        self._events: list[dict[str, Any]] | None = None
        self._built_for: date | None = None

    def macro_events(self, as_of: date) -> tuple[dict[str, Any], ...]:
        """Return normalized high-signal FRED release dates for the configured horizon."""
        if self._events is not None and self._built_for == as_of:
            return tuple(self._events)

        events: list[dict[str, Any]] = []
        end_date = as_of + timedelta(days=self._horizon_days)
        if self._api_key or self._row_fetcher is not None:
            rows = self._fetch_rows(as_of, end_date)
            for row in rows:
                event_date = self._parse_date(row.get("date"))
                if event_date is None or event_date < as_of or event_date > end_date:
                    continue
                title = str(row.get("release_name") or "").strip()
                if not title:
                    continue
                severity = self._severity(row.get("release_id"))
                if severity is None:
                    continue
                event_time = datetime.combine(event_date, DEFAULT_RELEASE_TIME_UTC)
                events.append(
                    {
                        "event_code": self._slug(title),
                        "event_time": event_time,
                        "title": title,
                        "severity_hint": severity,
                        "source": "fred_release_calendar",
                    }
                )

        events.sort(key=lambda item: (item["event_time"], item["event_code"]))
        self._events = events
        self._built_for = as_of
        return tuple(events)

    def _fetch_rows(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        try:
            if self._row_fetcher is not None:
                return list(self._row_fetcher(start_date, end_date))
            response = self._client.get(
                FRED_RELEASE_DATES_URL,
                params={
                    "api_key": str(self._api_key or ""),
                    "file_type": "json",
                    "realtime_start": start_date.isoformat(),
                    "realtime_end": end_date.isoformat(),
                    "include_release_dates_with_no_data": "true",
                    "sort_order": "asc",
                    "limit": 1000,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("release_dates"), list):
                return [row for row in payload["release_dates"] if isinstance(row, dict)]
        except Exception as exc:
            logger.warning("fred_economic_calendar_fetch_failed", error=str(exc))
        return []

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        try:
            return date.fromisoformat(str(value or "").strip())
        except ValueError:
            return None

    @staticmethod
    def _severity(release_id: Any) -> str | None:
        normalized = FREDEconomicCalendar._release_id(release_id)
        if normalized in _HIGH_SIGNAL_RELEASE_IDS:
            return "high"
        if normalized in _MEDIUM_SIGNAL_RELEASE_IDS:
            return "medium"
        return None

    @staticmethod
    def _release_id(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        slug = re.sub(r"_+", "_", slug)
        return slug or "fred_release"
