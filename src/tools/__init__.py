"""Tools package — context, base classes, registry, and concrete tools."""
from src.tools.context import ToolContext
from src.tools.base import BaseTool, ToolError
from src.tools.registry import ToolRegistry
from src.tools.market_data import MarketDataTool
from src.tools.news_data import NewsDataTool
from src.tools.insider_queries import (
    RecentTradesTool,
    TradesByTickerTool,
    TradesByInsiderTool,
    LargeTransactionsTool,
    ClusterActivityTool,
    SearchFilingsTool,
)


def build_research_tool_registry() -> ToolRegistry:
    """Create and return a :class:`ToolRegistry` wired for the research agent."""
    registry = ToolRegistry()
    registry.register(MarketDataTool())
    registry.register(NewsDataTool())
    registry.register(RecentTradesTool())
    registry.register(TradesByTickerTool())
    registry.register(TradesByInsiderTool())
    registry.register(LargeTransactionsTool())
    registry.register(ClusterActivityTool())
    registry.register(SearchFilingsTool())
    return registry


__all__ = [
    "ToolContext",
    "BaseTool",
    "ToolError",
    "ToolRegistry",
    "MarketDataTool",
    "NewsDataTool",
    "RecentTradesTool",
    "TradesByTickerTool",
    "TradesByInsiderTool",
    "LargeTransactionsTool",
    "ClusterActivityTool",
    "SearchFilingsTool",
    "build_research_tool_registry",
]
