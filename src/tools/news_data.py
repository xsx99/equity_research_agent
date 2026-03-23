"""News providers and tool for the research pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from typing import Any, Optional, Protocol, TypedDict

import httpx

from src.core.logging import get_logger
from src.tools.base import BaseTool, ToolError
from src.tools.context import ToolContext

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------


class NewsItem(TypedDict):
    """A single news headline and summary."""

    title: str
    summary: str
    published_at: Optional[str]  # ISO-8601 date string, e.g. "2026-03-21"


class NewsProvider(Protocol):
    """Contract for pluggable news providers."""

    def fetch_recent(self, ticker: str, limit: int) -> list[NewsItem]:
        """Fetch recent news for a ticker."""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _normalized_news_item(
    title: Optional[str],
    summary: Optional[str],
    published_at: Optional[str] = None,
) -> Optional[NewsItem]:
    clean_title = (title or "").strip()
    if not clean_title:
        return None
    return {"title": clean_title, "summary": (summary or "").strip(), "published_at": published_at}


# ---------------------------------------------------------------------------
# Concrete providers
# ---------------------------------------------------------------------------


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
            item = _normalized_news_item(row.get("headline"), row.get("summary"), published_at)
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
                published_at = raw_date[:10]  # keep YYYY-MM-DD portion
            item = _normalized_news_item(row.get("title"), row.get("description"), published_at)
            if item:
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


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
                published_at = raw_date[:10]
            item = _normalized_news_item(row.get("headline"), row.get("summary"), published_at)
            if item:
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


# ---------------------------------------------------------------------------
# get_recent_news helper
# ---------------------------------------------------------------------------


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
    providers: Optional[list[NewsProvider]] = None,
) -> list[NewsItem]:
    """Fetch recent news from the provider chain with resilient fallback."""
    bounded_limit = max(1, min(limit, 5))
    created_default = providers is None
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
        if created_default:
            for provider in provider_list:
                if hasattr(provider, "close"):
                    try:
                        provider.close()  # type: ignore[attr-defined]
                    except Exception:
                        logger.warning(
                            "news_provider_close_failed",
                            provider=provider.__class__.__name__,
                        )


# ---------------------------------------------------------------------------
# BaseTool implementation
# ---------------------------------------------------------------------------


class NewsDataTool(BaseTool):
    """
    Fetches recent news headlines and summaries for a stock ticker.

    Tries Finnhub → Marketaux → Alpaca with automatic fallback.
    """

    name = "get_recent_news"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Fetch recent news headlines and summaries for a stock ticker. "
                "Returns up to 5 news items, each with a title and summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol, e.g. 'AAPL'",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of news items to return (1–5, default 5)",
                        "default": 5,
                    },
                },
                "required": ["ticker"],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> list[dict[str, str]]:
        ticker = input.get("ticker")
        if not ticker:
            raise ToolError("ticker is required", tool_name=self.name)
        limit = int(input.get("limit", 5))
        return get_recent_news(str(ticker).upper(), limit=limit)
