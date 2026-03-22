"""News providers used by the research pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from typing import Protocol, TypedDict

import httpx

from src.logging import get_logger

logger = get_logger(__name__)


class NewsItem(TypedDict):
    """Research input shape for headline and summary."""

    title: str
    summary: str


class NewsProvider(Protocol):
    """Contract for pluggable news providers."""

    def fetch_recent(self, ticker: str, limit: int) -> list[NewsItem]:
        """Fetch recent news for a ticker."""


def _normalized_news_item(title: str | None, summary: str | None) -> NewsItem | None:
    clean_title = (title or "").strip()
    if not clean_title:
        return None
    return {
        "title": clean_title,
        "summary": (summary or "").strip(),
    }


class FinnhubNewsProvider:
    """Finnhub-backed company news provider."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.Client | None = None,
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
            item = _normalized_news_item(row.get("headline"), row.get("summary"))
            if item:
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class MarketauxNewsProvider:
    """Marketaux-backed news provider."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("MARKETAUX_API_KEY")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def fetch_recent(self, ticker: str, limit: int) -> list[NewsItem]:
        if not self.api_key:
            raise RuntimeError("missing_marketaux_api_key")

        response = self._client.get(
            "https://api.marketaux.com/v1/news/all",
            params={
                "api_token": self.api_key,
                "symbols": ticker.upper(),
                "language": "en",
                "filter_entities": "true",
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
            item = _normalized_news_item(row.get("title"), row.get("description"))
            if item:
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class AlpacaNewsProvider:
    """Alpaca-backed news provider used as a final fallback."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        secret_key: str | None = None,
        data_base_url: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        self.data_base_url = (data_base_url or os.getenv("ALPACA_DATA_BASE_URL") or "https://data.alpaca.markets").rstrip(
            "/"
        )
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
        response = self._client.get(
            f"{self.data_base_url}/v1beta1/news",
            params={"symbols": ticker.upper(), "limit": limit},
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
            item = _normalized_news_item(row.get("headline"), row.get("summary"))
            if item:
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _default_news_providers() -> list[NewsProvider]:
    providers: list[NewsProvider] = []
    if os.getenv("FINNHUB_API_KEY"):
        providers.append(FinnhubNewsProvider())
    if os.getenv("MARKETAUX_API_KEY"):
        providers.append(MarketauxNewsProvider())
    if os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"):
        providers.append(AlpacaNewsProvider())
    return providers


def get_recent_news(
    ticker: str,
    limit: int = 5,
    providers: list[NewsProvider] | None = None,
) -> list[NewsItem]:
    """Fetch recent news from provider chain with resilient fallback."""
    bounded_limit = max(1, min(limit, 5))
    created_default_providers = providers is None
    provider_list = providers or _default_news_providers()

    try:
        for provider in provider_list:
            provider_name = provider.__class__.__name__
            try:
                items = provider.fetch_recent(ticker=ticker, limit=bounded_limit)
            except Exception as exc:
                logger.warning(
                    "news_provider_failed",
                    ticker=ticker,
                    provider=provider_name,
                    error=str(exc),
                )
                continue

            if items:
                return items[:bounded_limit]
        return []
    finally:
        if created_default_providers:
            for provider in provider_list:
                if hasattr(provider, "close"):
                    try:
                        provider.close()  # type: ignore[attr-defined]
                    except Exception:
                        logger.warning("news_provider_close_failed", provider=provider.__class__.__name__)

