"""Finnhub-backed company news provider."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from src.tools.news_data.helpers import _normalized_news_item
from src.tools.news_data.types import NewsItem


class FinnhubNewsProvider:
    """Finnhub-backed company news provider."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def fetch_recent(self, ticker: str, limit: int) -> list[NewsItem]:
        if not self.api_key:
            raise RuntimeError("missing_finnhub_api_key")
        today = datetime.now(timezone.utc).date()
        response = self._client.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": ticker.upper(),
                "from": (today - timedelta(days=7)).isoformat(),
                "to": today.isoformat(),
                "token": self.api_key,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("unexpected_finnhub_payload")

        items: list[NewsItem] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            published_at: Optional[str] = None
            ts = row.get("datetime")
            if isinstance(ts, (int, float)) and ts > 0:
                published_at = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
            item = _normalized_news_item(
                row.get("headline"), row.get("summary"), published_at,
                source=row.get("source"), url=row.get("url"),
            )
            if item:
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
