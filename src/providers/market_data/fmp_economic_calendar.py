"""Financial Modeling Prep economic-calendar provider."""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import httpx

from src.core.logging import get_logger


logger = get_logger(__name__)

FMP_ECONOMIC_CALENDAR_URL = "https://financialmodelingprep.com/api/v3/economic_calendar"


class FMPEconomicCalendar:
    """Best-effort FMP calendar adapter for forward macro events."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        horizon_days: int = 14,
        client: httpx.Client | Any | None = None,
        row_fetcher: Callable[[date, date], list[dict[str, Any]]] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key or os.getenv("FMP_API_KEY")
        self._horizon_days = horizon_days
        self._client = client or httpx.Client(timeout=timeout)
        self._row_fetcher = row_fetcher
        self._events: list[dict[str, Any]] | None = None
        self._built_for: date | None = None

    def macro_events(self, as_of: date) -> tuple[dict[str, Any], ...]:
        """Return normalized US high/medium macro events for the configured horizon."""
        if self._events is not None and self._built_for == as_of:
            return tuple(self._events)
        events: list[dict[str, Any]] = []
        if self._api_key or self._row_fetcher is not None:
            end_date = as_of + timedelta(days=self._horizon_days)
            rows = self._fetch_rows(as_of, end_date)
            for row in rows:
                if not self._is_us(row):
                    continue
                impact = str(row.get("impact") or "").strip().lower()
                if impact not in {"high", "medium"}:
                    continue
                event_time = self._parse_utc(row.get("date"))
                title = str(row.get("event") or "").strip()
                if event_time is None or not title:
                    continue
                events.append(
                    {
                        "event_code": self._slug(title),
                        "event_time": event_time,
                        "title": title,
                        "severity_hint": impact,
                        "source": "fmp_economic_calendar",
                    }
                )
        self._events = events
        self._built_for = as_of
        return tuple(events)

    def _fetch_rows(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        try:
            if self._row_fetcher is not None:
                return list(self._row_fetcher(start_date, end_date))
            response = self._client.get(
                FMP_ECONOMIC_CALENDAR_URL,
                params={
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                    "apikey": str(self._api_key or ""),
                },
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                return [row for row in payload if isinstance(row, dict)]
            if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                return [row for row in payload["data"] if isinstance(row, dict)]
        except Exception as exc:
            logger.warning("fmp_economic_calendar_fetch_failed", error=str(exc))
        return []

    @staticmethod
    def _is_us(row: dict[str, Any]) -> bool:
        country = str(row.get("country") or "").strip().lower()
        currency = str(row.get("currency") or "").strip().upper()
        return country in {"us", "usa", "united states", "united states of america"} or currency == "USD"

    @staticmethod
    def _parse_utc(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        text = str(value or "").strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            try:
                parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        slug = re.sub(r"_+", "_", slug)
        return slug or "macro_event"
