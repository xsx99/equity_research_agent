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


def test_build_ticker_workspace_keeps_closed_ticker_visible_in_closed_today_bucket():
    workspace = build_ticker_workspace(
        trade_rows=[
            {"ticker": "NVDA", "decision": "exit", "order_status": "filled", "created_at": "2026-06-05T19:58:00Z"},
            {"ticker": "AAPL", "decision": "enter_long", "order_status": "filled", "created_at": "2026-06-05T14:31:00Z"},
        ],
        selected_ticker=None,
        positions_by_ticker={"AAPL": {"status": "open"}},
        closed_positions_by_ticker={"NVDA": {"status": "closed", "closed_at": "2026-06-05T20:05:00Z"}},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert [item["ticker"] for item in workspace["buckets"]["closed_today"]] == ["NVDA"]
    assert workspace["selected_ticker"] == "AAPL"


def test_build_ticker_workspace_assigns_primary_lifecycle_state_and_attention_flags():
    workspace = build_ticker_workspace(
        trade_rows=[{"ticker": "MSFT", "decision": "no_trade", "risk_status": "approved", "material_signal_change": True}],
        selected_ticker="MSFT",
        positions_by_ticker={},
        closed_positions_by_ticker={},
        risk_by_ticker={"MSFT": {"status": "approved", "reason": "within_limits"}},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    item = workspace["buckets"]["reviewing"][0]

    assert item["primary_state"] == "reviewing"
    assert item["attention_flags"] == ["material_change"]


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


def test_build_ticker_workspace_includes_position_only_ticker():
    workspace = build_ticker_workspace(
        trade_rows=[],
        selected_ticker=None,
        positions_by_ticker={"tsla": {"quantity": 5, "order_status": "accepted"}},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert [item["ticker"] for item in workspace["buckets"]["action_now"]] == []
    assert [item["ticker"] for item in workspace["buckets"]["in_position"]] == ["TSLA"]
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


def test_build_ticker_workspace_uses_newer_row_when_duplicate_priorities_tie():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "nvda",
                "decision": "no_trade",
                "risk_status": "approved",
                "order_status": None,
                "material_signal_change": False,
                "confidence": 0.21,
                "created_at": "2026-06-03T14:20:00Z",
            },
            {
                "ticker": "NVDA",
                "decision": "no_trade",
                "risk_status": "approved",
                "order_status": None,
                "material_signal_change": False,
                "confidence": 0.67,
                "created_at": "2026-06-03T14:35:00Z",
            },
        ],
        selected_ticker=None,
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert workspace["buckets"]["watch"] == [
        {
            "ticker": "NVDA",
            "decision": "no_trade",
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
            "confidence": 0.67,
            "created_at": "2026-06-03T14:35:00Z",
            "primary_state": "watch",
            "attention_flags": [],
        }
    ]


def test_build_ticker_workspace_uses_latest_row_for_current_bucket_state():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "risk_status": "approved",
                "order_status": "pending",
                "material_signal_change": True,
                "confidence": 0.82,
                "created_at": "2026-06-03T14:20:00Z",
            },
            {
                "ticker": "NVDA",
                "decision": "no_trade",
                "risk_status": "approved",
                "order_status": None,
                "material_signal_change": False,
                "confidence": 0.33,
                "created_at": "2026-06-03T14:35:00Z",
            },
        ],
        selected_ticker=None,
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert [item["ticker"] for item in workspace["buckets"]["action_now"]] == []
    assert workspace["buckets"]["watch"] == [
        {
            "ticker": "NVDA",
            "decision": "no_trade",
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
            "confidence": 0.33,
            "created_at": "2026-06-03T14:35:00Z",
            "primary_state": "watch",
            "attention_flags": [],
        }
    ]
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


def test_build_ticker_workspace_shapes_latest_conclusion_and_evidence():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "trim",
                "selected_strategy_id": "valuation_repair_quality_software_v1",
                "expression_bucket_id": "long_stock",
                "confidence": 0.52,
                "risk_status": "approved",
                "created_at": "2026-06-03T14:20:00Z",
            },
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "selected_strategy_id": "valuation_repair_quality_software_v1",
                "expression_bucket_id": "long_stock",
                "confidence": 0.78,
                "risk_status": "approved",
                "created_at": "2026-06-03T14:35:00Z",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={"NVDA": {"pnl": "+2.1%", "order_status": "accepted"}},
        risk_by_ticker={
            "NVDA": {
                "status": "approved",
                "reason": "within_limits",
                "history": [{"time": "2026-06-03T14:36:00Z", "status": "approved", "summary": "Within limits"}],
            }
        },
        signal_history_by_ticker={
            "NVDA": {
                "technical": [
                    {"label": "price", "points": [1, 2, 3], "summary": "Above rising support"},
                    {"label": "relative_strength", "points": [3, 4, 5], "summary": "Trend improving vs QQQ"},
                ],
                "summary": ["relative strength improving vs QQQ", "price holding above key breakout"],
                "timeline": [
                    {
                        "time": "2026-06-03T14:40:00Z",
                        "event_type": "signal",
                        "summary": "Breakout follow-through confirmed",
                    },
                    {
                        "time": "2026-06-03T14:30:00Z",
                        "event_type": "signal",
                        "summary": "Relative strength inflected higher",
                    }
                ],
            }
        },
        news_by_ticker={
            "NVDA": [
                {"title": "Late headline", "summary": "Follow-through demand", "published_at": "2026-06-03T14:50:00Z"},
                {"title": "Raised guidance", "summary": "Demand improved", "published_at": "2026-06-03T13:00:00Z"}
            ]
        },
        fundamentals_by_ticker={
            "NVDA": [{"title": "Margin outlook", "summary": "Gross margin stable", "as_of": "2026-06-02"}]
        },
    )

    detail = workspace["detail"]
    latest_conclusion = detail["latest_conclusion"]

    assert latest_conclusion["trade_decision"]["label"] == "Enter Long"
    assert latest_conclusion["trade_decision"]["strategy_id"] == "valuation_repair_quality_software_v1"
    assert latest_conclusion["trade_decision"]["strategy_label"] == "Valuation repair setup"
    assert latest_conclusion["trade_decision"]["expression_bucket_label"] == "Long Stock"
    assert latest_conclusion["signal_summary"]["summary_bullets"] == [
        "relative strength improving vs QQQ",
        "price holding above key breakout",
    ]
    assert latest_conclusion["signal_summary"]["technical_charts"] == [
        {
            "chart_type": "price / key level trend",
            "label": "price",
            "points": [1, 2, 3],
            "summary": "Above rising support",
            "empty": False,
        },
        {
            "chart_type": "relative strength trend",
            "label": "relative_strength",
            "points": [3, 4, 5],
            "summary": "Trend improving vs QQQ",
            "empty": False,
        },
    ]
    assert {item["title"] for item in latest_conclusion["signal_summary"]["news_snippets"]} == {
        "Raised guidance",
        "Late headline",
    }
    assert latest_conclusion["signal_summary"]["fundamental_snippets"][0]["title"] == "Margin outlook"
    assert latest_conclusion["risk_summary"]["status"] == "approved"
    assert latest_conclusion["risk_summary"]["status_label"] == "Approved"
    assert latest_conclusion["position_execution"]["position"]["pnl"] == "+2.1%"

    assert detail["tabs"]["timeline"] == [
        {
            "time": "2026-06-03T13:00:00Z",
            "event_type": "news",
            "summary": "Raised guidance",
            "detail_anchor": "news-2",
        },
        {
            "time": "2026-06-03T14:20:00Z",
            "event_type": "decision",
            "summary": "Trim",
            "detail_anchor": "decision-1",
        },
        {
            "time": "2026-06-03T14:30:00Z",
            "event_type": "signal",
            "summary": "Relative strength inflected higher",
            "detail_anchor": "signal-2",
        },
        {
            "time": "2026-06-03T14:35:00Z",
            "event_type": "decision",
            "summary": "Enter Long",
            "detail_anchor": "decision-2",
        },
        {
            "time": "2026-06-03T14:40:00Z",
            "event_type": "signal",
            "summary": "Breakout follow-through confirmed",
            "detail_anchor": "signal-1",
        },
        {
            "time": "2026-06-03T14:50:00Z",
            "event_type": "news",
            "summary": "Late headline",
            "detail_anchor": "news-1",
        },
    ]
    assert detail["tabs"]["trend"]["technical"][0]["chart_type"] == "price / key level trend"
    assert detail["tabs"]["decisions"] == [
        {
            "time": "2026-06-03T14:20:00Z",
            "decision": "Trim",
            "confidence": 0.52,
            "strategy_id": "valuation_repair_quality_software_v1",
            "strategy_label": "Valuation repair setup",
            "expression_bucket_id": "long_stock",
            "expression_bucket_label": "Long Stock",
            "detail_anchor": "decision-1",
        },
        {
            "time": "2026-06-03T14:35:00Z",
            "decision": "Enter Long",
            "confidence": 0.78,
            "strategy_id": "valuation_repair_quality_software_v1",
            "strategy_label": "Valuation repair setup",
            "expression_bucket_id": "long_stock",
            "expression_bucket_label": "Long Stock",
            "detail_anchor": "decision-2",
        }
    ]
    assert latest_conclusion["trade_decision"]["label"] == "Enter Long"
    assert detail["tabs"]["risk"]["history"][0]["summary"] == "Within limits"


def test_build_ticker_workspace_surfaces_lookahead_risk_source_and_hedge_overlay_reason():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "trim",
                "selected_strategy_id": "valuation_repair_quality_software_v1",
                "expression_bucket_id": "long_stock",
                "confidence": 0.52,
                "risk_status": "approved",
                "created_at": "2026-06-03T14:20:00Z",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={"NVDA": {"summary": "Trimmed before binary event"}},
        risk_by_ticker={
            "NVDA": {
                "status": "approved",
                "reason": "own_event_force_reduce",
                "lookahead_risk_source": "own_event",
                "generated_hedge_action": {"reason_code": "macro_high_overlay"},
                "raw_json": {
                    "status": "approved",
                    "reason_code": "own_event_force_reduce",
                    "lookahead_risk_source": "own_event",
                    "generated_hedge_action": {"reason_code": "macro_high_overlay"},
                },
                "history": [{"time": "2026-06-03T14:36:00Z", "status": "approved", "summary": "Trimmed before event"}],
            }
        },
        signal_history_by_ticker={"NVDA": {"technical": [], "summary": [], "timeline": []}},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    risk_summary = workspace["detail"]["latest_conclusion"]["risk_summary"]

    assert risk_summary["lookahead_risk_source"] == "own_event"
    assert risk_summary["hedge_overlay_reason"] == "macro_high_overlay"
    assert workspace["detail"]["tabs"]["risk"]["raw_json"]["generated_hedge_action"]["reason_code"] == "macro_high_overlay"


def test_build_ticker_workspace_detail_includes_entry_exit_reason_times_and_pnl():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "created_at": "2026-06-05T14:31:00Z",
                "selected_strategy_id": "breakout_v1",
                "thesis": "Momentum breakout confirmed",
            },
            {
                "ticker": "NVDA",
                "decision": "exit",
                "created_at": "2026-06-05T20:00:00Z",
                "thesis": "Target reached before close",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={},
        closed_positions_by_ticker={
            "NVDA": {
                "status": "closed",
                "opened_at": "2026-06-05T14:32:00Z",
                "closed_at": "2026-06-05T20:02:00Z",
                "realized_pnl": 1250.0,
            }
        },
        risk_by_ticker={"NVDA": {"status": "approved", "reason": "within_limits"}},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    detail = workspace["detail"]

    assert detail["lifecycle"] == {
        "state": "closed",
        "state_label": "Closed",
        "opened_at": "2026-06-05T14:32:00Z",
        "closed_at": "2026-06-05T20:02:00Z",
        "realized_pnl": 1250.0,
        "entry_summary": "Momentum breakout confirmed",
        "exit_summary": "Target reached before close",
    }
    assert detail["tabs"]["timeline"] == [
        {
            "time": "2026-06-05T14:31:00Z",
            "event_type": "entry",
            "summary": "Enter Long",
            "detail_anchor": "decision-1",
        },
        {
            "time": "2026-06-05T20:00:00Z",
            "event_type": "close",
            "summary": "Exit",
            "detail_anchor": "decision-2",
        },
    ]


def test_build_ticker_workspace_surfaces_later_undated_decision_consistently():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "trim",
                "selected_strategy_id": "older_strategy",
                "expression_bucket_id": "long_stock",
                "confidence": 0.41,
                "risk_status": "approved",
                "created_at": "2026-06-03T14:20:00Z",
            },
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "selected_strategy_id": "latest_strategy",
                "expression_bucket_id": "long_stock",
                "confidence": 0.78,
                "risk_status": "approved",
                "created_at": "2026-06-03T14:35:00Z",
            },
            {
                "ticker": "NVDA",
                "decision": "exit",
                "selected_strategy_id": "undated_strategy",
                "expression_bucket_id": "long_stock",
                "confidence": 0.12,
                "risk_status": "approved",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    detail = workspace["detail"]

    assert detail["latest_conclusion"]["trade_decision"]["label"] == "Exit"
    assert detail["latest_conclusion"]["trade_decision"]["strategy_id"] == "undated_strategy"
    assert detail["tabs"]["decisions"] == [
        {
            "time": "2026-06-03T14:20:00Z",
            "decision": "Trim",
            "confidence": 0.41,
            "strategy_id": "older_strategy",
            "strategy_label": "Older Strategy",
            "expression_bucket_id": "long_stock",
            "expression_bucket_label": "Long Stock",
            "detail_anchor": "decision-1",
        },
        {
            "time": "2026-06-03T14:35:00Z",
            "decision": "Enter Long",
            "confidence": 0.78,
            "strategy_id": "latest_strategy",
            "strategy_label": "Latest Strategy",
            "expression_bucket_id": "long_stock",
            "expression_bucket_label": "Long Stock",
            "detail_anchor": "decision-2",
        },
        {
            "time": None,
            "decision": "Exit",
            "confidence": 0.12,
            "strategy_id": "undated_strategy",
            "strategy_label": "Undated Strategy",
            "expression_bucket_id": "long_stock",
            "expression_bucket_label": "Long Stock",
            "detail_anchor": "decision-3",
        },
    ]
    assert detail["tabs"]["timeline"] == [
        {
            "time": "2026-06-03T14:20:00Z",
            "event_type": "decision",
            "summary": "Trim",
            "detail_anchor": "decision-1",
        },
        {
            "time": "2026-06-03T14:35:00Z",
            "event_type": "decision",
            "summary": "Enter Long",
            "detail_anchor": "decision-2",
        },
        {
            "time": None,
            "event_type": "decision",
            "summary": "Exit",
            "detail_anchor": "decision-3",
        },
    ]


def test_build_ticker_workspace_orders_timeline_and_decisions_by_real_datetimes():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "trim",
                "selected_strategy_id": "offset_plus_two",
                "expression_bucket_id": "long_stock",
                "confidence": 0.51,
                "risk_status": "approved",
                "created_at": "2026-06-03T10:00:00+02:00",
            },
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "selected_strategy_id": "utc_latest",
                "expression_bucket_id": "long_stock",
                "confidence": 0.82,
                "risk_status": "approved",
                "created_at": "2026-06-03T13:30:00Z",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={
            "NVDA": {
                "timeline": [
                    {
                        "time": "2026-06-03T08:30:00+01:00",
                        "event_type": "signal",
                        "summary": "Signal event should come first",
                    }
                ]
            }
        },
        news_by_ticker={
            "NVDA": [
                {
                    "title": "UTC news",
                    "summary": "Published after first decision",
                    "published_at": "2026-06-03T13:05:00Z",
                }
            ]
        },
        fundamentals_by_ticker={},
    )

    detail = workspace["detail"]

    assert detail["latest_conclusion"]["trade_decision"]["label"] == "Enter Long"
    assert detail["latest_conclusion"]["trade_decision"]["strategy_id"] == "utc_latest"
    assert detail["tabs"]["decisions"] == [
        {
            "time": "2026-06-03T10:00:00+02:00",
            "decision": "Trim",
            "confidence": 0.51,
            "strategy_id": "offset_plus_two",
            "strategy_label": "Offset Plus Two",
            "expression_bucket_id": "long_stock",
            "expression_bucket_label": "Long Stock",
            "detail_anchor": "decision-1",
        },
        {
            "time": "2026-06-03T13:30:00Z",
            "decision": "Enter Long",
            "confidence": 0.82,
            "strategy_id": "utc_latest",
            "strategy_label": "Utc Latest",
            "expression_bucket_id": "long_stock",
            "expression_bucket_label": "Long Stock",
            "detail_anchor": "decision-2",
        },
    ]
    assert detail["tabs"]["timeline"] == [
        {
            "time": "2026-06-03T08:30:00+01:00",
            "event_type": "signal",
            "summary": "Signal event should come first",
            "detail_anchor": "signal-1",
        },
        {
            "time": "2026-06-03T10:00:00+02:00",
            "event_type": "decision",
            "summary": "Trim",
            "detail_anchor": "decision-1",
        },
        {
            "time": "2026-06-03T13:05:00Z",
            "event_type": "news",
            "summary": "UTC news",
            "detail_anchor": "news-1",
        },
        {
            "time": "2026-06-03T13:30:00Z",
            "event_type": "decision",
            "summary": "Enter Long",
            "detail_anchor": "decision-2",
        },
    ]


def test_build_ticker_workspace_keeps_all_undated_decisions_consistent():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "trim",
                "selected_strategy_id": "first_strategy",
                "expression_bucket_id": "long_stock",
                "confidence": 0.41,
                "risk_status": "approved",
            },
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "selected_strategy_id": "latest_strategy",
                "expression_bucket_id": "long_stock",
                "confidence": 0.78,
                "risk_status": "approved",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    detail = workspace["detail"]

    assert detail["latest_conclusion"]["trade_decision"]["label"] == "Enter Long"
    assert detail["latest_conclusion"]["trade_decision"]["strategy_id"] == "latest_strategy"
    assert detail["tabs"]["decisions"] == [
        {
            "time": None,
            "decision": "Trim",
            "confidence": 0.41,
            "strategy_id": "first_strategy",
            "strategy_label": "First Strategy",
            "expression_bucket_id": "long_stock",
            "expression_bucket_label": "Long Stock",
            "detail_anchor": "decision-1",
        },
        {
            "time": None,
            "decision": "Enter Long",
            "confidence": 0.78,
            "strategy_id": "latest_strategy",
            "strategy_label": "Latest Strategy",
            "expression_bucket_id": "long_stock",
            "expression_bucket_label": "Long Stock",
            "detail_anchor": "decision-2",
        },
    ]
    assert detail["tabs"]["timeline"] == [
        {
            "time": None,
            "event_type": "decision",
            "summary": "Trim",
            "detail_anchor": "decision-1",
        },
        {
            "time": None,
            "event_type": "decision",
            "summary": "Enter Long",
            "detail_anchor": "decision-2",
        },
    ]


def test_build_ticker_workspace_sorts_risk_history_by_real_timestamp():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "risk_status": "approved",
                "created_at": "2026-06-03T14:35:00Z",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={},
        risk_by_ticker={
            "NVDA": {
                "status": "approved",
                "history": [
                    {"time": "2026-06-03T10:00:00-04:00", "status": "blocked", "summary": "Latest"},
                    {"time": "2026-06-03T09:30:00Z", "status": "approved", "summary": "Middle"},
                    {"time": "2026-06-03T10:00:00+02:00", "status": "watch", "summary": "Earliest"},
                ],
            }
        },
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert workspace["detail"]["tabs"]["risk"]["history"] == [
        {"time": "2026-06-03T10:00:00+02:00", "status": "watch", "summary": "Earliest"},
        {"time": "2026-06-03T09:30:00Z", "status": "approved", "summary": "Middle"},
        {"time": "2026-06-03T10:00:00-04:00", "status": "blocked", "summary": "Latest"},
    ]


def test_build_ticker_workspace_sorts_news_and_fundamental_snippets_by_time():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "risk_status": "approved",
                "created_at": "2026-06-03T14:35:00Z",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={
            "NVDA": [
                {"title": "Latest news", "summary": "Newest", "published_at": "2026-06-03T10:00:00-04:00"},
                {"title": "Earliest news", "summary": "Oldest", "published_at": "2026-06-03T10:00:00+02:00"},
                {"title": "Middle news", "summary": "Middle", "published_at": "2026-06-03T09:30:00Z"},
            ]
        },
        fundamentals_by_ticker={
            "NVDA": [
                {"title": "Latest fundamental", "summary": "Newest", "as_of": "2026-06-03T10:00:00-04:00"},
                {"title": "Earliest fundamental", "summary": "Oldest", "as_of": "2026-06-03T10:00:00+02:00"},
                {"title": "Middle fundamental", "summary": "Middle", "as_of": "2026-06-03T09:30:00Z"},
            ]
        },
    )

    signal_summary = workspace["detail"]["latest_conclusion"]["signal_summary"]

    assert [item["title"] for item in signal_summary["news_snippets"]] == [
        "Latest news",
        "Middle news",
        "Earliest news",
    ]
    assert [item["title"] for item in signal_summary["fundamental_snippets"]] == [
        "Latest fundamental",
        "Middle fundamental",
        "Earliest fundamental",
    ]


def test_build_ticker_workspace_uses_empty_state_markers_when_detail_inputs_are_missing():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "AAPL",
                "decision": "no_trade",
                "risk_status": "approved",
                "order_status": None,
                "material_signal_change": False,
            },
        ],
        selected_ticker="AAPL",
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    detail = workspace["detail"]
    latest_conclusion = detail["latest_conclusion"]

    assert latest_conclusion["signal_summary"]["summary_bullets"] == ["No material update"]
    assert latest_conclusion["signal_summary"]["technical_charts"] == [
        {
            "chart_type": "price / key level trend",
            "label": "No material update",
            "points": [],
            "summary": "No material update",
            "empty": True,
        },
        {
            "chart_type": "relative strength trend",
            "label": "No material update",
            "points": [],
            "summary": "No material update",
            "empty": True,
        },
    ]
    assert latest_conclusion["signal_summary"]["news_snippets"] == [
        {
            "title": "No material update",
            "summary": "No material update",
            "time": None,
            "empty": True,
        }
    ]
    assert latest_conclusion["signal_summary"]["fundamental_snippets"] == [
        {
            "title": "No material update",
            "summary": "No material update",
            "time": None,
            "empty": True,
        }
    ]
    assert latest_conclusion["risk_summary"]["status"] == "No material update"
    assert latest_conclusion["position_execution"]["position"]["summary"] == "No material update"
    assert detail["tabs"]["timeline"] == [
        {
            "time": None,
            "event_type": "decision",
            "summary": "No Trade",
            "detail_anchor": "decision-1",
        }
    ]
    assert detail["tabs"]["trend"]["news"] == [
        {
            "title": "No material update",
            "summary": "No material update",
            "time": None,
            "empty": True,
        }
    ]
    assert detail["tabs"]["trend"]["fundamental"] == [
        {
            "title": "No material update",
            "summary": "No material update",
            "time": None,
            "empty": True,
        }
    ]
    assert detail["tabs"]["decisions"] == [
        {
            "time": None,
            "decision": "No Trade",
            "confidence": None,
            "strategy_id": "No material update",
            "strategy_label": "No material update",
            "expression_bucket_id": "No material update",
            "expression_bucket_label": "No material update",
            "detail_anchor": "decision-1",
        }
    ]
    assert detail["tabs"]["risk"]["history"] == [
        {
            "time": None,
            "status": "No material update",
            "summary": "No material update",
            "empty": True,
        }
    ]


def test_build_ticker_workspace_surfaces_trade_reasoning_in_latest_conclusion_and_decisions():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "UBER",
                "decision": "no_trade",
                "selected_strategy_id": "valuation_repair_quality_software_v1",
                "expression_bucket_id": "long_stock",
                "confidence": 0.35,
                "risk_status": "approved",
                "created_at": "2026-06-03T14:35:00Z",
                "thesis": "Direct negative catalyst identified; prefer to monitor instead of opening a trade.",
                "invalidators": [
                    "estimate stabilization fails",
                    "valuation repair reverses",
                ],
                "metadata_json": {
                    "selection_reason": "direct company-level negative catalyst blocks bullish candidate",
                    "classification_result_status": "no_trade",
                    "risk_checks": ["direct_negative_catalyst"],
                },
            },
        ],
        selected_ticker="UBER",
        positions_by_ticker={},
        risk_by_ticker={"UBER": {"status": "approved", "reason": "within_limits"}},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    detail = workspace["detail"]

    assert (
        detail["latest_conclusion"]["trade_decision"]["summary"]
        == "Direct negative catalyst identified; prefer to monitor instead of opening a trade."
    )
    assert detail["latest_conclusion"]["trade_decision"]["invalidators"] == [
        "estimate stabilization fails",
        "valuation repair reverses",
    ]
    assert detail["tabs"]["decisions"] == [
        {
            "time": "2026-06-03T14:35:00Z",
            "decision": "No Trade",
            "confidence": 0.35,
            "strategy_id": "valuation_repair_quality_software_v1",
            "strategy_label": "Valuation repair setup",
            "expression_bucket_id": "long_stock",
            "expression_bucket_label": "Long Stock",
            "summary": "direct company-level negative catalyst blocks bullish candidate",
            "detail_anchor": "decision-1",
        }
    ]


def test_build_ticker_workspace_deduplicates_repeated_summary_bullets():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "AAPL",
                "decision": "no_trade",
                "risk_status": "approved",
                "created_at": "2026-06-05T12:50:00Z",
            },
        ],
        selected_ticker="AAPL",
        positions_by_ticker={},
        risk_by_ticker={"AAPL": {"status": "approved", "reason": "within_limits"}},
        signal_history_by_ticker={
            "AAPL": {
                "summary": [
                    "Events/news sentiment positive.",
                    "Technical: 20d return 8.26%.",
                    "Events/news sentiment positive.",
                    "Technical: 20d return 8.26%.",
                    "Fundamental: quality 0.98.",
                ]
            }
        },
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert workspace["detail"]["latest_conclusion"]["signal_summary"]["summary_bullets"] == [
        "Events/news sentiment positive.",
        "Technical: 20d return 8.26%.",
        "Fundamental: quality 0.98.",
    ]


def test_build_ticker_workspace_surfaces_key_drivers_and_counterarguments():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "selected_strategy_id": "relative_strength_rotation_v1",
                "expression_bucket_id": "long_stock",
                "confidence": 0.74,
                "risk_status": "approved",
                "order_status": None,
                "material_signal_change": False,
                "thesis": "Relative strength remains intact.",
                "key_drivers": ["sector_relative_strength", "relative_volume"],
                "counterarguments": ["valuation is elevated versus peers"],
                "invalidators": ["QQQ closes below prior close"],
                "created_at": "2026-06-05T14:35:00Z",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={},
        risk_by_ticker={"NVDA": {"status": "approved", "reason": "within_limits"}},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    detail = workspace["detail"]

    assert detail["latest_conclusion"]["trade_decision"]["key_drivers"] == [
        "sector_relative_strength",
        "relative_volume",
    ]
    assert detail["latest_conclusion"]["trade_decision"]["counterarguments"] == [
        "valuation is elevated versus peers"
    ]


def test_build_ticker_workspace_computes_timeline_delta_entries_for_repeated_phase_runs():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "AAPL",
                "decision": "enter_long",
                "selected_strategy_id": "gap_continuation_v1",
                "expression_bucket_id": "long_stock",
                "confidence": 0.74,
                "created_at": "2026-06-16T13:32:00Z",
            },
        ],
        selected_ticker="AAPL",
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={
            "AAPL": {
                "summary": ["Relative strength improved vs QQQ"],
                "timeline": [
                    {
                        "time": "2026-06-16T12:45:00Z",
                        "event_type": "signal_snapshot",
                        "phase": "pre_open",
                        "summary": "Sentiment neutral, risk approved",
                        "source_refs": ["signal:1"],
                    },
                    {
                        "time": "2026-06-16T12:55:00Z",
                        "event_type": "signal_snapshot",
                        "phase": "pre_open",
                        "summary": "Sentiment negative, risk reduced",
                        "source_refs": ["signal:2"],
                    },
                    {
                        "time": "2026-06-16T12:55:00Z",
                        "event_type": "signal_snapshot",
                        "phase": "pre_open",
                        "summary": "Sentiment negative, risk reduced",
                        "source_refs": ["signal:2"],
                    },
                ],
            }
        },
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    timeline = workspace["detail"]["tabs"]["timeline"]

    assert [item["title"] for item in timeline[:2]] == ["Pre Open Baseline", "Pre Open Rerun"]
    assert timeline[0]["change_type"] == "baseline"
    assert timeline[1]["change_type"] == "delta"
    assert timeline[1]["delta_fields"] == ("sentiment neutral -> negative", "risk approved -> reduced")
    assert timeline[1]["source_refs"] == ("signal:2",)


def test_build_ticker_workspace_truncates_signal_summary_and_groups_hidden_bullets():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "created_at": "2026-06-16T13:32:00Z",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={
            "NVDA": {
                "summary": [
                    "Risk blocked by event cluster",
                    "Price broke above preopen resistance",
                    "Relative strength improved vs QQQ",
                    "Insider cluster buy count accelerated",
                    "Policy headline turned into a tailwind",
                    "Relative strength improved vs QQQ",
                    "Fresh catalyst still intact",
                    "Data quality: no stale inputs",
                ]
            }
        },
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    signal_summary = workspace["detail"]["latest_conclusion"]["signal_summary"]

    assert signal_summary["summary_bullets"] == [
        "Risk blocked by event cluster",
        "Price broke above preopen resistance",
        "Relative strength improved vs QQQ",
        "Insider cluster buy count accelerated",
        "Policy headline turned into a tailwind",
    ]
    assert signal_summary["hidden_bullet_count"] == 2
    assert [section["label"] for section in signal_summary["grouped_sections"]] == [
        "Risk blockers",
        "Trend",
        "Insider",
        "Policy / Social",
        "Evidence",
        "Data quality",
    ]
