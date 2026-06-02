"""Agent-callable news data tool wrapper."""
from __future__ import annotations

from typing import Any

from src.providers.news_data import get_recent_news
from src.tools.base import BaseTool, ToolError
from src.tools.context import ToolContext

__all__ = ["NewsDataTool", "get_recent_news"]


class NewsDataTool(BaseTool):
    """Fetches recent news headlines and summaries for a stock ticker."""

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
                    "limit": {"type": "integer", "description": "Maximum number of news items to return (1-5, default 5)", "default": 5},
                },
                "required": ["ticker"],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> list[dict[str, str]]:
        ticker = input.get("ticker")
        if not ticker:
            raise ToolError("ticker is required", tool_name=self.name)
        return get_recent_news(str(ticker).upper(), limit=int(input.get("limit", 5)))

