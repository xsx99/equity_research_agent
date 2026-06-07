"""Alpaca-backed news provider (final fallback)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from src.providers.news_data.helpers import _normalized_news_item
from src.providers.news_data.types import NewsItem


class AlpacaNewsProvider:
    """Alpaca-backed news provider (final fallback)."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        data_base_url: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")
        self.data_base_url = (
            data_base_url or os.getenv("ALPACA_DATA_BASE_URL") or "https://data.alpaca.markets"
        ).rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def _auth_headers(self) -> dict[str, str]:
        if not self.api_key or not self.secret_key:
            raise RuntimeError("missing_alpaca_credentials")
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

    def fetch_recent(self, ticker: str, limit: int) -> list[NewsItem]:
        today = datetime.now(timezone.utc).date()
        response = self._client.get(
            f"{self.data_base_url}/v1beta1/news",
            params={
                "symbols": ticker.upper(),
                "limit": limit,
                "start": (today - timedelta(days=7)).isoformat(),
                "end": today.isoformat(),
                "sort": "desc",
            },
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("news", [])
        if not isinstance(rows, list):
            raise ValueError("unexpected_alpaca_news_payload")

        items: list[NewsItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            published_at: Optional[str] = None
            raw_date = row.get("created_at")
            if isinstance(raw_date, str) and raw_date:
                published_at = raw_date
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
