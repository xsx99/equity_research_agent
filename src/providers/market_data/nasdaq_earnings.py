"""Nasdaq earnings-calendar provider."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Iterable

import httpx


RowFetcher = Callable[[date], Iterable[dict[str, Any]]]


class NasdaqEarningsCalendar:
    """Best-effort Nasdaq earnings calendar cached by run date.

    Nasdaq's calendar API is date-scoped, so this provider fetches each date in
    the configured horizon once per ``as_of`` date and serves ticker lookups
    from an in-memory ``symbol -> nearest earnings date`` map.
    """

    HEADERS = {
        "authority": "api.nasdaq.com",
        "accept": "application/json, text/plain, */*",
        "user-agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120 Safari/537.36"
        ),
        "origin": "https://www.nasdaq.com",
        "referer": "https://www.nasdaq.com/",
        "accept-language": "en-US,en;q=0.9",
    }

    def __init__(
        self,
        *,
        horizon_days: int = 45,
        client: httpx.Client | None = None,
        row_fetcher: RowFetcher | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._horizon_days = max(int(horizon_days), 0)
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        self._row_fetcher = row_fetcher
        self._map: dict[str, date] | None = None
        self._built_for: date | None = None

    def next_earnings_date(self, ticker: str, as_of: date) -> date | None:
        """Return the nearest known earnings date for ``ticker`` on/after ``as_of``."""
        symbol = str(ticker or "").strip().upper()
        if not symbol:
            return None
        self._ensure_map(as_of)
        return (self._map or {}).get(symbol)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _ensure_map(self, as_of: date) -> None:
        if self._map is not None and self._built_for == as_of:
            return

        mapping: dict[str, date] = {}
        for offset in range(self._horizon_days + 1):
            day = as_of + timedelta(days=offset)
            try:
                rows = self._fetch_rows(day)
            except Exception:
                rows = ()
            for row in rows:
                symbol = str(row.get("symbol") or "").strip().upper()
                if symbol and symbol not in mapping:
                    mapping[symbol] = day
        self._map = mapping
        self._built_for = as_of

    def _fetch_rows(self, day: date) -> tuple[dict[str, Any], ...]:
        if self._row_fetcher is not None:
            return tuple(row for row in self._row_fetcher(day) if isinstance(row, dict))

        response = self._client.get(
            "https://api.nasdaq.com/api/calendar/earnings",
            params={"date": day.isoformat()},
            headers=self.HEADERS,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return ()
        data = payload.get("data")
        if not isinstance(data, dict):
            return ()
        rows = data.get("rows")
        if not isinstance(rows, list):
            return ()
        return tuple(row for row in rows if isinstance(row, dict))
