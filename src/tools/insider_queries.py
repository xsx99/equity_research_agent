"""Insider trading query tools backed by PostgreSQL.

Each public query from the original ``InsiderTools`` class is exposed as its
own :class:`~src.tools.base.BaseTool` subclass so the LLM can reason clearly
about what each tool does.  All tools require a database session on the
:class:`~src.tools.context.ToolContext`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, desc

from src.tools.base import BaseTool, ToolError
from src.tools.context import ToolContext


def _require_session(context: ToolContext, tool_name: str):
    if context.session is None:
        raise ToolError(
            "A database session is required for this tool.",
            tool_name=tool_name,
        )
    return context.session


def _trade_to_dict(trade) -> dict:
    return {
        "ticker": trade.ticker,
        "company_name": trade.company_name,
        "insider_name": trade.insider_name,
        "insider_title": trade.insider_title,
        "transaction_type": trade.transaction_type,
        "transaction_date": str(trade.transaction_date) if trade.transaction_date else None,
        "filing_date": str(trade.filing_date) if trade.filing_date else None,
        "shares": trade.shares,
        "price_per_share": float(trade.price_per_share) if trade.price_per_share else None,
        "total_value": float(trade.total_value) if trade.total_value else None,
        "shares_owned_after": trade.shares_owned_after,
    }


class RecentTradesTool(BaseTool):
    """Query recent insider trades across all tickers."""

    name = "query_recent_trades"

    @property
    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Query recent insider trades from the database. "
                "Optionally filter by transaction type (P=purchase, S=sale) and minimum value."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 7)",
                        "default": 7,
                    },
                    "transaction_type": {
                        "type": "string",
                        "description": "Filter by type: 'P' for purchase, 'S' for sale",
                    },
                    "min_value": {
                        "type": "number",
                        "description": "Minimum transaction value in USD",
                    },
                },
                "required": [],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> list[dict]:
        from src.db.models import InsiderTrade

        session = _require_session(context, self.name)
        days = int(input.get("days", 7))
        transaction_type = input.get("transaction_type")
        min_value = input.get("min_value")

        cutoff = datetime.now().date() - timedelta(days=days)
        query = session.query(InsiderTrade).filter(InsiderTrade.filing_date >= cutoff)

        if transaction_type:
            query = query.filter(InsiderTrade.transaction_type == transaction_type)
        if min_value is not None:
            query = query.filter(InsiderTrade.total_value >= float(min_value))

        trades = query.order_by(desc(InsiderTrade.filing_date)).all()
        return [_trade_to_dict(t) for t in trades]


class TradesByTickerTool(BaseTool):
    """Query insider trades for a specific stock ticker."""

    name = "query_trades_by_ticker"

    @property
    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Query all insider trades for a specific stock ticker.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol, e.g. 'AAPL'",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 30)",
                        "default": 30,
                    },
                },
                "required": ["ticker"],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> list[dict]:
        from src.db.models import InsiderTrade

        session = _require_session(context, self.name)
        ticker = input.get("ticker")
        if not ticker:
            raise ToolError("ticker is required", tool_name=self.name)

        days = int(input.get("days", 30))
        cutoff = datetime.now().date() - timedelta(days=days)

        trades = (
            session.query(InsiderTrade)
            .filter(
                InsiderTrade.ticker == str(ticker).upper(),
                InsiderTrade.filing_date >= cutoff,
            )
            .order_by(desc(InsiderTrade.transaction_date))
            .all()
        )
        return [_trade_to_dict(t) for t in trades]


class TradesByInsiderTool(BaseTool):
    """Query trading history for a specific insider by name."""

    name = "query_trades_by_insider"

    @property
    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Query the trading history for a specific insider (partial name match).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Insider name (partial match supported)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 50)",
                        "default": 50,
                    },
                },
                "required": ["name"],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> list[dict]:
        from src.db.models import InsiderTrade

        session = _require_session(context, self.name)
        name = input.get("name")
        if not name:
            raise ToolError("name is required", tool_name=self.name)

        limit = int(input.get("limit", 50))
        trades = (
            session.query(InsiderTrade)
            .filter(InsiderTrade.insider_name.ilike(f"%{name}%"))
            .order_by(desc(InsiderTrade.transaction_date))
            .limit(limit)
            .all()
        )
        return [_trade_to_dict(t) for t in trades]


class LargeTransactionsTool(BaseTool):
    """Query large insider transactions above a dollar threshold."""

    name = "query_large_transactions"

    @property
    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Query insider transactions above a minimum dollar value.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "min_value": {
                        "type": "number",
                        "description": "Minimum transaction value in USD",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 7)",
                        "default": 7,
                    },
                },
                "required": ["min_value"],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> list[dict]:
        from src.db.models import InsiderTrade

        session = _require_session(context, self.name)
        min_value = input.get("min_value")
        if min_value is None:
            raise ToolError("min_value is required", tool_name=self.name)

        days = int(input.get("days", 7))
        cutoff = datetime.now().date() - timedelta(days=days)

        trades = (
            session.query(InsiderTrade)
            .filter(
                InsiderTrade.total_value >= float(min_value),
                InsiderTrade.filing_date >= cutoff,
            )
            .order_by(desc(InsiderTrade.total_value))
            .all()
        )
        return [_trade_to_dict(t) for t in trades]


class ClusterActivityTool(BaseTool):
    """Detect tickers where multiple insiders traded in a time window."""

    name = "query_cluster_activity"

    @property
    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Detect stocks where multiple insiders traded within a time window. "
                "Returns tickers with their insider count and individual trades."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 7)",
                        "default": 7,
                    },
                    "min_insiders": {
                        "type": "integer",
                        "description": "Minimum number of distinct insiders required (default 3)",
                        "default": 3,
                    },
                },
                "required": [],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> list[dict]:
        from src.db.models import InsiderTrade

        session = _require_session(context, self.name)
        days = int(input.get("days", 7))
        min_insiders = int(input.get("min_insiders", 3))
        cutoff = datetime.now().date() - timedelta(days=days)

        clusters = (
            session.query(
                InsiderTrade.ticker,
                func.count(func.distinct(InsiderTrade.insider_name)).label("insider_count"),
            )
            .filter(InsiderTrade.filing_date >= cutoff)
            .group_by(InsiderTrade.ticker)
            .having(func.count(func.distinct(InsiderTrade.insider_name)) >= min_insiders)
            .all()
        )

        results = []
        for ticker, count in clusters:
            trades = (
                session.query(InsiderTrade)
                .filter(InsiderTrade.ticker == ticker, InsiderTrade.filing_date >= cutoff)
                .order_by(desc(InsiderTrade.transaction_date))
                .all()
            )
            results.append(
                {
                    "ticker": ticker,
                    "insider_count": count,
                    "trades": [_trade_to_dict(t) for t in trades],
                }
            )
        return results


class SearchFilingsTool(BaseTool):
    """Full-text search across ticker, company name, and insider name."""

    name = "search_filings"

    @property
    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Search insider trading filings by ticker symbol, company name, "
                "or insider name (partial match)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to match against ticker, company, or insider name",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 50)",
                        "default": 50,
                    },
                },
                "required": ["query"],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> list[dict]:
        from src.db.models import InsiderTrade

        session = _require_session(context, self.name)
        query_str = input.get("query")
        if not query_str:
            raise ToolError("query is required", tool_name=self.name)

        limit = int(input.get("limit", 50))
        pattern = f"%{query_str}%"

        trades = (
            session.query(InsiderTrade)
            .filter(
                InsiderTrade.ticker.ilike(pattern)
                | InsiderTrade.company_name.ilike(pattern)
                | InsiderTrade.insider_name.ilike(pattern)
            )
            .order_by(desc(InsiderTrade.filing_date))
            .limit(limit)
            .all()
        )
        return [_trade_to_dict(t) for t in trades]
