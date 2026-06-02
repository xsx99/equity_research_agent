"""Agent-callable market data tool wrapper."""
from __future__ import annotations

from typing import Any

from src.providers.market_data import get_market_snapshot
from src.tools.base import BaseTool, ToolError
from src.tools.context import ToolContext

__all__ = ["MarketDataTool", "get_market_snapshot"]


class MarketDataTool(BaseTool):
    """Fetches the latest price snapshot for a stock ticker."""

    name = "get_market_snapshot"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Fetch the latest market data snapshot for a stock ticker. "
                "Returns last_price, 1-day return, 5-day return, return since "
                "market open during the current regular session, session volume, "
                "20-day average volume, relative volume, sector, days until the "
                "next earnings announcement, basic valuation / short-interest metrics, "
                "plus replayable technical signals such as RSI and ATR-derived volatility."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. 'AAPL'"}
                },
                "required": ["ticker"],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        ticker = input.get("ticker")
        if not ticker:
            raise ToolError("ticker is required", tool_name=self.name)
        return dict(get_market_snapshot(str(ticker).upper()))

