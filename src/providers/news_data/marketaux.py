"""Marketaux-backed news provider."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from src.providers.news_data.helpers import _normalized_news_item
from src.providers.news_data.types import NewsItem


class MarketauxNewsProvider:
    """Marketaux-backed news provider."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("MARKETAUX_API_KEY")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def fetch_recent(self, ticker: str, limit: int) -> list[NewsItem]:
        if not self.api_key:
            raise RuntimeError("missing_marketaux_api_key")
        today = datetime.now(timezone.utc).date()
        response = self._client.get(
            "https://api.marketaux.com/v1/news/all",
            params={
                "api_token": self.api_key,
                "symbols": ticker.upper(),
                "language": "en",
                "filter_entities": "true",
                "published_after": (today - timedelta(days=7)).isoformat(),
                "limit": limit,
            },
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise ValueError("unexpected_marketaux_payload")

        items: list[NewsItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            published_at: Optional[str] = None
            raw_date = row.get("published_at")
            if isinstance(raw_date, str) and raw_date:
                published_at = raw_date[:10]
            raw_source = row.get("source")
            if isinstance(raw_source, dict):
                name = raw_source.get("name")
                source_name: Optional[str] = str(name).strip() if name else None
            else:
                source_name = str(raw_source).strip() if raw_source else None
            item = _normalized_news_item(
                row.get("title"), row.get("description"), published_at,
                source=source_name, url=row.get("url"),
            )
            if item:
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
