"""News providers and tool for the research pipeline."""
from __future__ import annotations

import os
from typing import Any, Optional

from src.core.logging import get_logger
from src.tools.base import BaseTool, ToolError
from src.tools.context import ToolContext
from src.tools.news_data.alpaca import AlpacaNewsProvider
from src.tools.news_data.finnhub import FinnhubNewsProvider
from src.tools.news_data.helpers import _normalize_provider_news_item, _rank_and_filter_news_items
from src.tools.news_data.marketaux import MarketauxNewsProvider
from src.tools.news_data.types import NewsItem, NewsProvider

__all__ = [
    "AlpacaNewsProvider",
    "FinnhubNewsProvider",
    "MarketauxNewsProvider",
    "NewsDataTool",
    "NewsItem",
    "NewsProvider",
    "get_recent_news",
]

logger = get_logger(__name__)


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
                logger.warning("news_provider_failed", ticker=ticker, provider=provider_name, error=str(exc))
                continue
            for item in items:
                normalized = _normalize_provider_news_item(item)
                if normalized:
                    collected_items.append(normalized)
        return _rank_and_filter_news_items(collected_items, bounded_limit)
    finally:
        if created_default:
            for provider in provider_list:
                if hasattr(provider, "close"):
                    try:
                        provider.close()  # type: ignore[attr-defined]
                    except Exception:
                        logger.warning("news_provider_close_failed", provider=provider.__class__.__name__)


class NewsDataTool(BaseTool):
    """Fetches recent news headlines and summaries for a stock ticker.

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
                    "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. 'AAPL'"},
                    "limit": {"type": "integer", "description": "Maximum number of news items to return (1–5, default 5)", "default": 5},
                },
                "required": ["ticker"],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> list[dict[str, str]]:
        ticker = input.get("ticker")
        if not ticker:
            raise ToolError("ticker is required", tool_name=self.name)
        return get_recent_news(str(ticker).upper(), limit=int(input.get("limit", 5)))
