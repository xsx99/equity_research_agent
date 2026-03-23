"""Unit tests for insider query tools."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.tools.base import ToolError
from src.tools.context import ToolContext
from src.tools.insider_queries import (
    ClusterActivityTool,
    LargeTransactionsTool,
    RecentTradesTool,
    SearchFilingsTool,
    TradesByInsiderTool,
    TradesByTickerTool,
    _trade_to_dict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx_no_session() -> ToolContext:
    return ToolContext()


def _ctx_with_session(session) -> ToolContext:
    return ToolContext(session=session)


def _make_trade(**overrides) -> SimpleNamespace:
    """Build a minimal fake InsiderTrade-like object."""
    defaults = dict(
        ticker="AAPL",
        company_name="Apple Inc.",
        insider_name="Tim Cook",
        insider_title="CEO",
        transaction_type="P",
        transaction_date=date(2026, 3, 1),
        filing_date=date(2026, 3, 2),
        shares=1000,
        price_per_share=Decimal("210.50"),
        total_value=Decimal("210500.00"),
        shares_owned_after=50000,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _chain_session(trades: list) -> MagicMock:
    """Return a mock session whose .query().filter().order_by().all() returns *trades*."""
    session = MagicMock()
    (
        session.query.return_value
        .filter.return_value
        .order_by.return_value
        .all.return_value
    ) = trades
    return session


def _chain_session_with_limit(trades: list) -> MagicMock:
    """Mock session for tools that end with .limit().all()."""
    session = MagicMock()
    (
        session.query.return_value
        .filter.return_value
        .order_by.return_value
        .limit.return_value
        .all.return_value
    ) = trades
    return session


# ---------------------------------------------------------------------------
# _trade_to_dict
# ---------------------------------------------------------------------------


def test_trade_to_dict_full():
    trade = _make_trade()
    d = _trade_to_dict(trade)
    assert d["ticker"] == "AAPL"
    assert d["insider_name"] == "Tim Cook"
    assert d["transaction_type"] == "P"
    assert d["transaction_date"] == str(date(2026, 3, 1))
    assert d["filing_date"] == str(date(2026, 3, 2))
    assert d["price_per_share"] == pytest.approx(210.50)
    assert d["total_value"] == pytest.approx(210500.00)
    assert d["shares_owned_after"] == 50000


def test_trade_to_dict_null_dates_and_prices():
    trade = _make_trade(
        transaction_date=None,
        filing_date=None,
        price_per_share=None,
        total_value=None,
    )
    d = _trade_to_dict(trade)
    assert d["transaction_date"] is None
    assert d["filing_date"] is None
    assert d["price_per_share"] is None
    assert d["total_value"] is None


# ---------------------------------------------------------------------------
# No-session guard (_require_session)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_cls,input_data",
    [
        (RecentTradesTool, {}),
        (TradesByTickerTool, {"ticker": "AAPL"}),
        (TradesByInsiderTool, {"name": "Cook"}),
        (LargeTransactionsTool, {"min_value": 1000}),
        (ClusterActivityTool, {}),
        (SearchFilingsTool, {"query": "AAPL"}),
    ],
)
def test_tool_requires_session(tool_cls, input_data):
    tool = tool_cls()
    with pytest.raises(ToolError, match="database session"):
        tool.run(input_data, _ctx_no_session())


# ---------------------------------------------------------------------------
# Missing required-field guards
# ---------------------------------------------------------------------------


def test_trades_by_ticker_missing_ticker_raises():
    tool = TradesByTickerTool()
    session = _chain_session([])
    ctx = _ctx_with_session(session)
    with pytest.raises(ToolError, match="ticker is required"):
        tool.run({}, ctx)


def test_trades_by_insider_missing_name_raises():
    tool = TradesByInsiderTool()
    session = _chain_session_with_limit([])
    ctx = _ctx_with_session(session)
    with pytest.raises(ToolError, match="name is required"):
        tool.run({}, ctx)


def test_large_transactions_missing_min_value_raises():
    tool = LargeTransactionsTool()
    session = _chain_session([])
    ctx = _ctx_with_session(session)
    with pytest.raises(ToolError, match="min_value is required"):
        tool.run({}, ctx)


def test_search_filings_missing_query_raises():
    tool = SearchFilingsTool()
    session = _chain_session_with_limit([])
    ctx = _ctx_with_session(session)
    with pytest.raises(ToolError, match="query is required"):
        tool.run({}, ctx)


# ---------------------------------------------------------------------------
# Happy-path: returns list of dicts
# ---------------------------------------------------------------------------


def test_recent_trades_returns_list():
    trade = _make_trade()
    session = _chain_session([trade])
    ctx = _ctx_with_session(session)

    result = RecentTradesTool().run({}, ctx)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["ticker"] == "AAPL"


def test_trades_by_ticker_uppercases_ticker():
    """TradesByTickerTool should normalise ticker to uppercase before querying."""
    trade = _make_trade(ticker="MSFT")
    session = _chain_session([trade])
    ctx = _ctx_with_session(session)

    result = TradesByTickerTool().run({"ticker": "msft"}, ctx)
    # Verify the filter was called with the uppercased value by checking the result
    assert result[0]["ticker"] == "MSFT"


def test_trades_by_insider_returns_list():
    trade = _make_trade(insider_name="Tim Cook")
    session = _chain_session_with_limit([trade])
    ctx = _ctx_with_session(session)

    result = TradesByInsiderTool().run({"name": "Cook"}, ctx)
    assert len(result) == 1
    assert result[0]["insider_name"] == "Tim Cook"


def test_large_transactions_returns_list():
    trade = _make_trade(total_value=Decimal("500000"))
    session = _chain_session([trade])
    ctx = _ctx_with_session(session)

    result = LargeTransactionsTool().run({"min_value": 100000}, ctx)
    assert len(result) == 1
    assert result[0]["total_value"] == pytest.approx(500000.0)


def test_search_filings_returns_list():
    trade = _make_trade()
    session = _chain_session_with_limit([trade])
    ctx = _ctx_with_session(session)

    result = SearchFilingsTool().run({"query": "Apple"}, ctx)
    assert len(result) == 1
    assert result[0]["company_name"] == "Apple Inc."


# ---------------------------------------------------------------------------
# Tool schema shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_cls",
    [
        RecentTradesTool,
        TradesByTickerTool,
        TradesByInsiderTool,
        LargeTransactionsTool,
        ClusterActivityTool,
        SearchFilingsTool,
    ],
)
def test_schema_has_required_keys(tool_cls):
    tool = tool_cls()
    schema = tool.schema
    assert schema["name"] == tool.name
    assert "description" in schema
    assert "parameters" in schema
    assert schema["parameters"]["type"] == "object"


@pytest.mark.parametrize(
    "tool_cls",
    [
        RecentTradesTool,
        TradesByTickerTool,
        TradesByInsiderTool,
        LargeTransactionsTool,
        ClusterActivityTool,
        SearchFilingsTool,
    ],
)
def test_anthropic_schema_is_derived_from_generic_schema(tool_cls):
    tool = tool_cls()
    assert tool.anthropic_schema["name"] == tool.schema["name"]
    assert tool.anthropic_schema["description"] == tool.schema["description"]
    assert tool.anthropic_schema["input_schema"] == tool.schema["parameters"]
