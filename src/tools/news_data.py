"""News providers and tool for the research pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import re
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
    source: Optional[str]
    url: Optional[str]
    signal_type: Optional[str]


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
    *,
    source: Optional[str] = None,
    url: Optional[str] = None,
    signal_type: Optional[str] = None,
) -> Optional[NewsItem]:
    clean_title = (title or "").strip()
    if not clean_title:
        return None
    clean_summary = (summary or "").strip()
    normalized_signal_type = signal_type or _infer_signal_type(
        clean_title,
        clean_summary,
        source=source,
    )
    return {
        "title": clean_title,
        "summary": clean_summary,
        "published_at": published_at,
        "source": (source or "").strip() or None,
        "url": (url or "").strip() or None,
        "signal_type": normalized_signal_type,
    }


_LOW_SIGNAL_TITLE_PATTERNS = (
    re.compile(r"\bis it too late\b", flags=re.IGNORECASE),
    re.compile(r"\bshould you buy\b", flags=re.IGNORECASE),
    re.compile(r"\bto buy now\b", flags=re.IGNORECASE),
    re.compile(r"\bhere'?s why\b", flags=re.IGNORECASE),
    re.compile(r"\bwhy .* stock .* (up|down) today\b", flags=re.IGNORECASE),
    re.compile(r"\btop \d+ .* stocks?\b", flags=re.IGNORECASE),
    re.compile(r"\bbest .* stocks?\b", flags=re.IGNORECASE),
    re.compile(r"\bprediction\b", flags=re.IGNORECASE),
)


_SIGNAL_TYPE_PRIORITY = {
    "earnings_guidance": 120,
    "sec_filing": 115,
    "analyst_rating": 110,
    "earnings": 100,
    "company_update": 90,
    "general_news": 70,
}


def _looks_low_signal(title: str) -> bool:
    normalized = " ".join(title.split())
    return any(pattern.search(normalized) for pattern in _LOW_SIGNAL_TITLE_PATTERNS)


def _infer_signal_type(
    title: str,
    summary: str,
    *,
    source: Optional[str] = None,
) -> str:
    text = " ".join((title, summary, source or "")).lower()
    if any(keyword in text for keyword in ("guidance", "outlook", "forecast", "preliminary results")):
        return "earnings_guidance"
    if any(
        keyword in text
        for keyword in ("upgrade", "upgrades", "downgrade", "downgrades", "price target", "initiates coverage")
    ):
        return "analyst_rating"
    if any(keyword in text for keyword in ("sec", "form 4", "8-k", "10-q", "10-k", "filing")):
        return "sec_filing"
    if any(keyword in text for keyword in ("earnings", "revenue", "eps", "quarter", "profit warning")):
        return "earnings"
    if any(keyword in text for keyword in ("press release", "business wire", "globe newswire")):
        return "company_update"
    return "general_news"


def _normalize_provider_news_item(item: Any) -> Optional[NewsItem]:
    if not isinstance(item, dict):
        return None
    return _normalized_news_item(
        item.get("title"),
        item.get("summary"),
        item.get("published_at"),
        source=item.get("source"),
        url=item.get("url"),
        signal_type=item.get("signal_type"),
    )


def _dedupe_key(item: NewsItem) -> str:
    return (item.get("url") or item["title"]).strip().lower()


def _rank_and_filter_news_items(items: list[NewsItem], limit: int) -> list[NewsItem]:
    kept: list[NewsItem] = []
    seen: set[str] = set()
    for item in items:
        if _looks_low_signal(item["title"]):
            continue
        key = _dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)

    kept.sort(
        key=lambda item: (
            _SIGNAL_TYPE_PRIORITY.get(item.get("signal_type") or "general_news", 0),
            item.get("published_at") or "",
        ),
        reverse=True,
    )
    return kept[:limit]


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
            item = _normalized_news_item(
                row.get("headline"),
                row.get("summary"),
                published_at,
                source=row.get("source"),
                url=row.get("url"),
            )
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
            raw_source = row.get("source")
            source_name: Optional[str]
            if isinstance(raw_source, dict):
                name = raw_source.get("name")
                source_name = str(name).strip() if name else None
            else:
                source_name = str(raw_source).strip() if raw_source else None
            item = _normalized_news_item(
                row.get("title"),
                row.get("description"),
                published_at,
                source=source_name,
                url=row.get("url"),
            )
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
            item = _normalized_news_item(
                row.get("headline"),
                row.get("summary"),
                published_at,
                source=row.get("source"),
                url=row.get("url"),
            )
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
    if os.getenv("ALPACA_API_KEY") and (
        os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")
    ):
        providers.append(AlpacaNewsProvider())
    return providers


def get_recent_news(
    ticker: str,
    limit: int = 5,
    providers: Optional[list[NewsProvider]] = None,
) -> list[NewsItem]:
    """Fetch recent news from all configured providers and keep the highest-signal items."""
    bounded_limit = max(1, min(limit, 5))
    created_default = providers is None
    provider_list = providers or _default_news_providers()
    collected_items: list[NewsItem] = []

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
            if not items:
                continue
            for item in items:
                normalized_item = _normalize_provider_news_item(item)
                if normalized_item:
                    collected_items.append(normalized_item)
        return _rank_and_filter_news_items(collected_items, bounded_limit)
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
                "Fetch recent company news for a stock ticker. Aggregates the "
                "configured providers, filters out low-signal retail-sentiment "
                "headlines, and returns up to 5 higher-signal items with source, "
                "URL, and signal_type metadata when available."
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
