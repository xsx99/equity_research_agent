"""Tests for the ticker-first today workspace presenter."""
from __future__ import annotations

from src.web.presenters.today_workspace import build_ticker_workspace


def test_build_ticker_workspace_groups_attention_buckets():
    rows = [
        {
            "ticker": "nvda",
            "decision": "enter_long",
            "confidence": 0.82,
            "risk_status": "approved",
            "order_status": "pending",
            "material_signal_change": True,
        },
        {
            "ticker": "aapl",
            "decision": "no_trade",
            "confidence": 0.31,
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
        },
    ]

    workspace = build_ticker_workspace(
        trade_rows=rows,
        selected_ticker=None,
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert [item["ticker"] for item in workspace["buckets"]["action_now"]] == ["NVDA"]
    assert [item["ticker"] for item in workspace["buckets"]["watch"]] == ["AAPL"]
    assert workspace["selected_ticker"] == "NVDA"


def test_build_ticker_workspace_prefers_action_now_then_in_position_then_watch():
    rows = [
        {
            "ticker": "msft",
            "decision": "no_trade",
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
        },
        {
            "ticker": "tsla",
            "decision": "no_trade",
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
        },
    ]

    workspace = build_ticker_workspace(
        trade_rows=rows,
        selected_ticker=None,
        positions_by_ticker={"tsla": {"quantity": 5}},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert [item["ticker"] for item in workspace["buckets"]["action_now"]] == []
    assert [item["ticker"] for item in workspace["buckets"]["in_position"]] == ["TSLA"]
    assert [item["ticker"] for item in workspace["buckets"]["watch"]] == ["MSFT"]
    assert workspace["selected_ticker"] == "TSLA"


def test_build_ticker_workspace_does_not_promote_directional_decision_without_actionable_state():
    rows = [
        {
            "ticker": "amd",
            "decision": "enter_long",
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
        },
    ]

    workspace = build_ticker_workspace(
        trade_rows=rows,
        selected_ticker=None,
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert [item["ticker"] for item in workspace["buckets"]["action_now"]] == []
    assert [item["ticker"] for item in workspace["buckets"]["watch"]] == ["AMD"]
    assert workspace["selected_ticker"] == "AMD"


def test_build_ticker_workspace_defaults_to_first_watch_ticker():
    rows = [
        {
            "ticker": "amzn",
            "decision": "no_trade",
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
        },
        {
            "ticker": "meta",
            "decision": "no_trade",
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
        },
    ]

    workspace = build_ticker_workspace(
        trade_rows=rows,
        selected_ticker=None,
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert [item["ticker"] for item in workspace["buckets"]["action_now"]] == []
    assert [item["ticker"] for item in workspace["buckets"]["in_position"]] == []
    assert [item["ticker"] for item in workspace["buckets"]["watch"]] == ["AMZN", "META"]
    assert workspace["selected_ticker"] == "AMZN"


def test_build_ticker_workspace_aggregates_repeated_rows_by_ticker():
    rows = [
        {
            "ticker": "nvda",
            "decision": "no_trade",
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
        },
        {
            "ticker": "NVDA",
            "decision": "enter_long",
            "risk_status": "approved",
            "order_status": "pending",
            "material_signal_change": True,
        },
        {
            "ticker": "msft",
            "decision": "no_trade",
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
        },
    ]

    workspace = build_ticker_workspace(
        trade_rows=rows,
        selected_ticker=None,
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert [item["ticker"] for item in workspace["buckets"]["action_now"]] == ["NVDA"]
    assert [item["ticker"] for item in workspace["buckets"]["watch"]] == ["MSFT"]
    assert workspace["selected_ticker"] == "NVDA"


def test_build_ticker_workspace_falls_back_when_selected_ticker_is_missing():
    rows = [
        {
            "ticker": "tsla",
            "decision": "no_trade",
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
        },
        {
            "ticker": "aapl",
            "decision": "enter_long",
            "risk_status": "approved",
            "order_status": "pending",
            "material_signal_change": False,
        },
    ]

    workspace = build_ticker_workspace(
        trade_rows=rows,
        selected_ticker="missing",
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert [item["ticker"] for item in workspace["buckets"]["action_now"]] == ["AAPL"]
    assert [item["ticker"] for item in workspace["buckets"]["watch"]] == ["TSLA"]
    assert workspace["selected_ticker"] == "AAPL"
