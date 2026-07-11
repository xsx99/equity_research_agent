"""Today dashboard route tests."""
from __future__ import annotations

import uuid
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with patch("src.web.init_db"):
        from src.app import app

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def _dashboard_payload() -> dict:
    manual_request_id = str(uuid.uuid4())
    universe_filter_id = str(uuid.uuid4())
    return {
        "selected_tab": "portfolio",
        "tabs": (
            {"id": "overview", "label": "Overview"},
            {"id": "trades", "label": "Trades"},
            {"id": "portfolio", "label": "Portfolio"},
            {"id": "risk-macro", "label": "Risk & Macro"},
            {"id": "candidates", "label": "Candidates"},
            {"id": "system", "label": "System"},
        ),
        "header": {
            "trade_date": date(2026, 6, 2),
            "market_phase": "Pre-open",
            "macro_regime": "neutral",
            "macro_regime_label": "Neutral",
            "risk_appetite": "balanced",
            "risk_appetite_label": "Balanced",
            "runtime_mode": "dry_run",
            "runtime_mode_label": "Dry Run",
            "live_status": "live",
            "live_status_label": "Live",
            "nav": Decimal("1000000"),
            "account_equity": Decimal("1000000"),
            "day_pnl": Decimal("1250.50"),
            "day_pnl_pct": Decimal("0.001252"),
            "realized_pnl": Decimal("430.25"),
            "unrealized_pnl": Decimal("820.25"),
            "buying_power": Decimal("2000000"),
            "cash_balance": Decimal("155000"),
            "stock_market_value": Decimal("2145.20"),
            "option_market_value": Decimal("840.75"),
            "gross_exposure": Decimal("0.42"),
            "net_exposure": Decimal("0.31"),
            "margin_util_pct": Decimal("0.06"),
            "open_alert_count": 2,
            "material_signal_change_count": 3,
            "llm_cost_estimate": Decimal("18.42"),
        },
        "job_timeline": (
            {"label": "Universe refresh", "status": "succeeded", "status_label": "Succeeded"},
            {"label": "Reflection", "status": "succeeded", "status_label": "Succeeded"},
        ),
        "overview": {
            "latest_preopen_run": {
                "status_label": "Passed",
                "as_of_label": "2026-06-02 13:49 UTC",
                "completed_at_label": "2026-06-02 13:49 UTC",
                "execution_mode_label": "Dry Run",
                "headline": "Signals built, but no candidates were selected.",
                "summary_tiles": (
                    {"label": "Signals", "value": "17"},
                    {"label": "Candidates", "value": "0"},
                    {"label": "Classifications", "value": "0"},
                    {"label": "Risk Decisions", "value": "0"},
                    {"label": "Trading Decisions", "value": "0"},
                    {"label": "Orders Submitted", "value": "0"},
                ),
                "empty_copy": None,
            },
            "command_center": {
                "needs_review": (
                    {"ticker": "NVDA", "summary": "Closed recently and ready for review"},
                ),
                "open_positions": (
                    {"ticker": "AAPL", "summary": "Open position, risk within limits"},
                ),
                "system_issues": (
                    {"label": "Macro regime unavailable", "summary": "Global macro regime feed has not published yet."},
                ),
            },
            "live_alerts": (
                {"ticker": "NVDA", "severity": "high", "headline": "Raised guidance"},
            ),
            "material_changes": (
                {"ticker": "AAPL", "summary": "Relative strength improved vs QQQ"},
            ),
            "attention_feed": (
                {
                    "ticker": "NVDA",
                    "primary_kind": "alert",
                    "facets": (
                        {"kind": "alert", "badge": "Alert", "text": "Raised guidance"},
                        {"kind": "review", "badge": "Ready for Review", "text": "Closed recently and ready for review"},
                    ),
                },
                {
                    "ticker": "AAPL",
                    "primary_kind": "signal",
                    "facets": (
                        {"kind": "signal", "badge": "Signal Change", "text": "Relative strength improved vs QQQ"},
                    ),
                },
            ),
        },
        "portfolio": {
            "kpis": {
                "account_equity": Decimal("1000000"),
                "day_pnl": Decimal("1250.50"),
                "realized_pnl": Decimal("430.25"),
                "unrealized_pnl": Decimal("820.25"),
                "gross_exposure": Decimal("0.42"),
                "net_exposure": Decimal("0.31"),
                "cash_balance": Decimal("155000"),
                "buying_power": Decimal("2000000"),
            },
            "positions": (
                {
                    "ticker": "AAPL",
                    "trade_identity": "tactical_stock_trade",
                    "trade_identity_label": "Tactical Stock Trade",
                    "strategy_id": "earnings_drift_v1",
                    "quantity": Decimal("10"),
                    "market_value": Decimal("2145.20"),
                    "unrealized_pnl": Decimal("325.10"),
                },
                {
                    "ticker": "MSFT",
                    "trade_identity": "tactical_stock_trade",
                    "trade_identity_label": "Tactical Stock Trade",
                    "strategy_id": "relative_strength_breakout_v1",
                    "quantity": Decimal("5"),
                    "market_value": Decimal("1550.80"),
                    "unrealized_pnl": Decimal("-25.10"),
                },
            ),
            "option_positions": (
                {
                    "ticker": "NVDA",
                    "option_strategy_type": "long_call",
                    "option_strategy_type_label": "Long Call",
                    "trade_identity": "tactical_option_trade",
                    "trade_identity_label": "Tactical Option Trade",
                    "market_value": Decimal("840.75"),
                    "max_loss": Decimal("420.00"),
                },
            ),
            "hedge_overlays": (
                {
                    "ticker": "SPY",
                    "option_strategy_type": "long_put",
                    "option_strategy_type_label": "Long Put",
                    "protected_notional": Decimal("25000"),
                },
            ),
            "position_summary": {
                "count": 2,
                "market_value": Decimal("3696.00"),
                "unrealized_pnl": Decimal("300.00"),
            },
            "option_position_summary": {
                "count": 1,
                "market_value": Decimal("840.75"),
                "max_loss": Decimal("420.00"),
            },
            "hedge_overlay_summary": {
                "count": 1,
                "protected_notional": Decimal("25000"),
            },
            "needs_attention": {
                "needs_review": (
                    {"ticker": "NVDA", "summary": "Closed recently and ready for review"},
                ),
                "live_alerts": (
                    {"ticker": "NVDA", "severity": "high", "headline": "Raised guidance"},
                ),
                "material_changes": (
                    {"ticker": "AAPL", "summary": "Relative strength improved vs QQQ"},
                ),
            },
        },
        "trades": {
            "rows": (),
            "selected_detail": None,
        },
        "ticker_workspace": {
            "selected_ticker": "AAPL",
            "selected_detail_tab": "timeline",
            "selected_detail_item_index": 0,
            "selected_detail_item": {
                "title": "Pre Open Baseline",
                "time_label": "2026-06-02 14:20 UTC",
                "change_type": "baseline",
                "signal_summary": ("Relative strength improved vs QQQ",),
                "trade_decision": {
                    "label": "Watch",
                    "summary": "Waiting for confirmation",
                    "thesis": "Breakout confirmation is still pending.",
                },
                "risk": {"status_label": "Approved", "summary": "Within limits"},
                "change_summary": (),
            },
            "buckets": {
                "action_now": (
                    {
                        "ticker": "AAPL",
                        "company_name": "Apple Inc.",
                        "primary_state": "action_now",
                        "attention_flags": ("pending_execution",),
                        "attention_badge": "Strong Buy",
                        "latest_decision": "Enter Long",
                        "why_now": "Breakout confirmed + risk approved",
                        "recency_label": "5m ago",
                        "position_risk_line": "Filled / risk approved",
                    },
                ),
                "open_positions": (
                    {
                        "ticker": "NVDA",
                        "company_name": "NVIDIA Corp.",
                        "primary_state": "open_position",
                        "attention_flags": (),
                        "attention_badge": "In Position",
                        "latest_decision": "No Trade",
                        "card_label": "Open Position",
                        "card_detail": "Latest decision: No Trade",
                        "why_now": "Monitoring after guidance follow-through",
                        "recency_label": "25m ago",
                        "position_risk_line": "Long 20 shares / risk approved",
                    },
                ),
                "closed_today": (
                    {
                        "ticker": "AMD",
                        "company_name": "Advanced Micro Devices",
                        "primary_state": "closed",
                        "attention_flags": (),
                        "attention_badge": "Closed",
                        "latest_decision": "Exit",
                        "why_now": "Target reached before close",
                        "recency_label": "42m ago",
                        "position_risk_line": "Realized P&L locked in",
                    },
                ),
                "reviewing": (
                    {
                        "ticker": "TSLA",
                        "company_name": "Tesla",
                        "primary_state": "reviewing",
                        "attention_flags": ("material_change",),
                        "attention_badge": "Reviewing",
                        "latest_decision": "No Trade",
                        "why_now": "Material signal change needs review",
                        "recency_label": "14m ago",
                        "position_risk_line": None,
                    },
                ),
                "in_position": (
                    {
                        "ticker": "NVDA",
                        "company_name": "NVIDIA Corp.",
                        "primary_state": "open_position",
                        "attention_flags": (),
                        "attention_badge": "In Position",
                        "latest_decision": "Hold",
                        "why_now": "Monitoring after guidance follow-through",
                        "recency_label": "25m ago",
                        "position_risk_line": "Long 20 shares / risk approved",
                    },
                ),
                "watch": (
                    {
                        "ticker": "MSFT",
                        "company_name": "Microsoft Corp.",
                        "primary_state": "watch",
                        "attention_flags": (),
                        "attention_badge": "Watch",
                        "latest_decision": "No Trade",
                        "why_now": "Relative strength improving vs QQQ",
                        "recency_label": "1h ago",
                        "position_risk_line": None,
                    },
                ),
            },
            "detail": {
                "ticker": "AAPL",
                "lifecycle": {
                    "state": "open_position",
                    "state_label": "Open Position",
                    "opened_at": "2026-06-05T14:32:00Z",
                    "closed_at": None,
                    "realized_pnl": None,
                    "entry_summary": "Breakout confirmed + risk approved",
                    "exit_summary": "No material update",
                },
                "latest_conclusion": {
                    "trade_decision": {
                        "label": "Enter Long",
                        "strategy_id": "earnings_drift_v1",
                        "strategy_label": "Earnings drift setup",
                        "expression_bucket_id": "long_stock",
                        "expression_bucket_label": "Long Stock",
                        "confidence": Decimal("0.72"),
                        "approved_weight": Decimal("0.05"),
                        "summary": "Changed from watch to Enter Long",
                    },
                    "trade_plan": {
                        "thesis": "Breakout remains valid after the catalyst.",
                        "time_horizon": "swing",
                        "target_weight": Decimal("0.08"),
                        "approved_weight": Decimal("0.05"),
                        "max_loss_pct": Decimal("0.03"),
                        "entry_plan": "Add on closing strength.",
                        "exit_plan": "Trim on failed breakout.",
                        "invalidators": ("loses VWAP",),
                    },
                    "bull_bear": {
                        "confidence": Decimal("0.82"),
                        "bull_points": ("relative strength is improving",),
                        "bear_points": ("macro could fade",),
                    },
                    "signal_groups": (
                        {"key": "technical", "label": "Technical", "bullets": ("20d return 8.26%", "relative volume 0.78")},
                        {"key": "fundamental", "label": "Fundamental", "bullets": ("quality 0.98",)},
                        {"key": "news_events", "label": "News & Events", "bullets": ("sentiment positive",)},
                        {"key": "insider", "label": "Insider", "bullets": ("officer buying",)},
                    ),
                    "signal_summary": {
                        "summary_bullets": (
                            "Relative strength improved vs QQQ",
                            "Price broke above preopen resistance",
                        ),
                        "latest_signal_time_label": "2026-06-02 14:35 UTC",
                        "primary_sections": (
                            {
                                "label": "Trend",
                                "bullets": (
                                    "Relative strength improved vs QQQ",
                                    "Price broke above preopen resistance",
                                ),
                            },
                        ),
                        "hidden_bullet_count": 0,
                        "grouped_sections": (),
                        "event_news_summary": "Raised guidance: Demand improved across core products.",
                        "technical_charts": (
                            {"chart_type": "Price / Key Level Trend", "summary": "Higher highs into the open"},
                        ),
                        "news_snippets": (
                            {
                                "title": "Raised guidance",
                                "summary": "Demand improved across core products",
                                "source_ticker": "MU",
                                "readthrough_label": "Readthrough from MU",
                            },
                        ),
                        "fundamental_snippets": (
                            {"title": "Margin outlook", "summary": "Gross margin remains stable"},
                        ),
                    },
                    "risk_summary": {
                        "status": "approved",
                        "status_label": "Approved",
                        "reason": "Within Limits",
                        "lookahead_risk_source": "own_event",
                        "hedge_overlay_reason": "macro_high_overlay",
                        "applied_rules": ("single_name_limit", "event_window_check"),
                    },
                    "position_execution": {
                        "position_label": "Long 10 shares",
                        "order_status": "filled",
                        "order_status_label": "Filled",
                        "summary": "Order filled and position established",
                    },
                },
                "tabs": {
                    "timeline": (
                        {
                            "title": "Pre Open Baseline",
                            "time_label": "2026-06-02 14:20 UTC",
                            "change_type": "baseline",
                            "signal_summary": (
                                "Relative strength improved vs QQQ",
                                "Price held above preopen resistance",
                            ),
                            "trade_decision": {
                                "label": "Watch",
                                "summary": "Waiting for confirmation",
                                "thesis": "Breakout confirmation is still pending.",
                            },
                            "risk": {"status_label": "Approved", "summary": "Within limits"},
                            "change_summary": (),
                        },
                        {
                            "title": "Pre Open Rerun",
                            "time_label": "2026-06-02 14:35 UTC",
                            "change_type": "material_change",
                            "signal_summary": (
                                "Relative strength improved vs QQQ",
                                "Price broke above preopen resistance",
                            ),
                            "trade_decision": {
                                "label": "Enter Long",
                                "summary": "The system promoted AAPL from watch to Enter Long after risk approval.",
                            },
                            "risk": {"status_label": "Approved", "summary": "Within Limits"},
                            "change_summary": ("candidate watch -> enter long",),
                        },
                    ),
                    "trend": {
                        "technical": (
                            {"title": "Relative Strength", "summary": "Improving"},
                        ),
                        "news": (
                            {"title": "Raised guidance", "summary": "Positive demand read-through"},
                        ),
                        "fundamental": (
                            {"title": "Margin outlook", "summary": "Stable"},
                        ),
                    },
                    "decisions": (
                        {"decision": "Enter Long", "summary": "Primary strategy selected"},
                    ),
                    "risk": {
                        "current_stance": {"status": "approved", "reason": "Within Limits"},
                        "position_state": {"summary": "Risk budget available"},
                        "history": (
                            {"status": "approved", "summary": "Approved at target size"},
                        ),
                        "raw_json": {"status": "approved", "reason_code": "within_limits"},
                    },
                    "raw_json": {
                        "decision": {"decision": "enter_long"},
                        "signal_snapshot": {"fresh_catalyst_type": "own_earnings_beat_raise"},
                    },
                },
            },
        },
        "risk_macro": {
            "risk_config_version": "risk_config_resolver_v1",
            "command_center": {
                "regime": "Risk Off",
                "risk_appetite_label": "Balanced",
                "exposure_usage_pct": 42.0,
                "event_risk_level": "High",
                "warning_banner": "Risk context degraded; review macro and provider availability before acting.",
                "basis_note": "Macro summary uses canonical risk + event context.",
            },
            "binding_constraints": ("theme cap near limit",),
            "summary": {
                "risk_status": "Within Limits",
                "top_risk_sources": (
                    {"label": "Technology concentration", "summary": "Theme cap near limit"},
                ),
                "availability_issues": (
                    {"label": "Macro regime unavailable", "summary": "Global macro regime data is unavailable."},
                ),
            },
            "events": (
                {
                    "calendar_event_id": "event-aapl-earnings",
                    "scheduled_at": datetime(2026, 6, 3, 18, 0, tzinfo=timezone.utc),
                    "event_type": "earnings",
                    "event_type_label": "Earnings",
                    "importance": "high",
                    "portfolio_risk_level": "high",
                    "affected_ticker": "AAPL",
                    "risk_mechanism": "direct earnings gap risk",
                },
                {
                    "calendar_event_id": "event-us-cpi",
                    "scheduled_at": datetime(2026, 6, 3, 13, 30, tzinfo=timezone.utc),
                    "event_type": "macro",
                    "event_type_label": "Macro Event",
                    "importance": "medium",
                    "portfolio_risk_level": "medium",
                    "affected_ticker": None,
                    "risk_mechanism": "US CPI",
                },
            ),
            "risk_sources": (
                {
                    "calendar_event_id": "event-aapl-earnings",
                    "ticker": "AAPL",
                    "risk_source": "own_event",
                    "risk_source_label": "Own Event",
                    "severity": "high",
                    "event_type": "earnings",
                    "days_until_event": 0,
                    "recommended_action": "block_open",
                    "recommended_action_label": "Block New Entry",
                    "rationale": "Own-event risk is inside the active trade horizon.",
                    "basis_note": "pending_trade",
                },
            ),
            "exposures": (
                {"factor_type": "sector", "factor_name": "Technology", "exposure": Decimal("5.2757000000000005")},
            ),
        },
        "candidates": {
            "active_universe_filter": {
                "universe_filter_config_id": universe_filter_id,
                "min_price": Decimal("10"),
                "min_avg_dollar_volume": Decimal("5000000"),
                "included_sectors": ("Technology",),
                "excluded_sectors": ("Utilities",),
                "included_industries": (),
                "excluded_industries": (),
                "exchanges": ("NASDAQ", "NYSE"),
                "asset_types": ("us_equity",),
                "manual_include": ("AAPL",),
                "manual_exclude": ("GME",),
            },
            "summary": {
                "action_queue": (
                    {
                        "ticker": "TSLA",
                        "label": "Pinned",
                        "summary": "Review Only because post-event review. Latest result: Still on watch.",
                    },
                    {
                        "ticker": "MSFT",
                        "label": "No clean entry, so no trade",
                        "summary": "Negative catalyst detected. No clean entry, so no trade. Watch Only.",
                    },
                ),
                "theme_count": 1,
            },
            "rows": (
                {
                    "ticker": "MSFT",
                    "selection_source": "direct_negative_catalyst",
                    "why_reviewed_label": "Negative catalyst detected",
                    "result_status": "no_trade",
                    "current_outcome_label": "No clean entry, so no trade",
                    "trade_identity": "watch_only",
                    "trade_identity_label": "Watch Only",
                    "strategy_match": "valuation_repair_quality_software_v1",
                    "strategy_label": "Valuation repair setup",
                    "operator_summary": "Negative catalyst detected. No clean entry, so no trade. Watch Only.",
                    "detail_internal_ids": {
                        "selection_source": "direct_negative_catalyst",
                        "result_status": "no_trade",
                        "trade_identity": "watch_only",
                        "strategy_match": "valuation_repair_quality_software_v1",
                    },
                },
            ),
            "manual_requests": (
                {
                    "manual_ticker_request_id": manual_request_id,
                    "ticker": "TSLA",
                    "reason": "post-event review",
                    "mode": "review_only",
                    "mode_label": "Review Only",
                    "status": "active",
                    "status_label": "Pinned",
                    "latest_result_status": "ordinary_watch",
                    "latest_result_label": "Still on watch",
                    "operator_summary": "Review Only because post-event review. Latest result: Still on watch.",
                },
            ),
            "portfolio_intents": (
                {
                    "ticker": "VOO",
                    "intent_type": "core_index",
                    "intent_type_label": "Core Index",
                    "lifecycle_status": "active",
                    "lifecycle_status_label": "Active",
                },
            ),
            "relationships": (
                {"source_ticker": "NVDA", "target_ticker": "SMCI", "relationship_type": "supplier"},
            ),
            "peer_baskets": (
                {"basket_key": "ai_largecap", "version": "v1", "member_count": 3},
            ),
            "themes": (
                {"theme_id": "ai_infra", "display_name": "AI Infrastructure"},
            ),
            "aggregate_summary": {
                "scored": 1,
                "actionable": 0,
                "watch": 1,
                "blocked": 1,
            },
        },
        "learning_strategies": {
            "reflection": {
                "status": "succeeded",
                "status_label": "Succeeded",
                "what_worked": ("Bullish catalyst continuation respected",),
            },
            "learning_summary_text": "1 active strategy tracked today. top performer: earnings_drift_v1 (+$4,200.00 total P&L). key new learning: Tighten low-volume gap entries (confidence 0.78).",
            "learning_factors": (
                {
                    "title": "Tighten low-volume gap entries",
                    "status": "active",
                    "status_label": "Active",
                    "scope": "strategy",
                    "scope_label": "Strategy",
                },
            ),
            "strategy_performance": (
                {
                    "strategy_id": "earnings_drift_v1",
                    "lifecycle_status": "active",
                    "lifecycle_status_label": "Active",
                    "win_rate": Decimal("58.0"),
                    "total_pnl": Decimal("4200"),
                    "learning_summary": "earnings_drift_v1 - active, 58.0% win rate (+$4,200.00 total P&L). Latest learning: Tighten low-volume gap entries (confidence 0.78); recommendation: tighten sizing after low-volume opens.",
                },
            ),
            "strategy_proposals": (
                {
                    "proposed_strategy_id": "semis_readthrough_v1",
                    "proposal_status": "accepted",
                    "proposal_status_label": "Accepted",
                },
            ),
            "observability": {
                "funnel": (
                    {"label": "Learning Factors Created", "count": 1},
                    {"label": "Applied Today", "count": 1},
                    {"label": "Strategy Proposals", "count": 1},
                    {"label": "New Strategy Definitions", "count": 1},
                    {"label": "Promoted", "count": 1},
                ),
                "promotion_breakdown": (
                    {"label": "Shadow", "count": 1},
                    {"label": "Experimental", "count": 0},
                    {"label": "Active", "count": 0},
                ),
                "weight_inputs": (
                    {
                        "factor_key": "lf-risk",
                        "title": "Tighten low-volume gap entries",
                        "scope_label": "Strategy",
                        "effect_summary": "increase score",
                    },
                ),
            },
        },
        "ops_cost": {
            "llm_usage": (
                {
                    "pipeline_name": "trading",
                    "provider": "openai",
                    "model": "gpt-5",
                    "estimated_cost": Decimal("12.30"),
                },
            ),
            "provider_usage": (
                {
                    "provider": "alpaca",
                    "endpoint": "market_bars",
                    "status": "succeeded",
                    "status_label": "Succeeded",
                    "cache_status": "miss",
                    "cache_status_label": "Cache Miss",
                },
            ),
        },
        "system": {
            "system_issues": (
                {"label": "Macro regime unavailable", "summary": "Global macro regime feed has not published yet."},
            ),
            "learning_strategies": {
                "reflection": {
                    "status": "succeeded",
                    "status_label": "Succeeded",
                    "what_worked": ("Bullish catalyst continuation respected",),
                },
                "learning_summary_text": "1 active strategy tracked today. top performer: earnings_drift_v1 (+$4,200.00 total P&L). key new learning: Tighten low-volume gap entries (confidence 0.78).",
                "learning_factors": (
                    {
                        "title": "Tighten low-volume gap entries",
                        "status": "active",
                        "status_label": "Active",
                        "scope": "strategy",
                        "scope_label": "Strategy",
                    },
                ),
                "strategy_performance": (
                    {
                        "strategy_id": "earnings_drift_v1",
                        "lifecycle_status": "active",
                        "lifecycle_status_label": "Active",
                        "win_rate": Decimal("58.0"),
                        "total_pnl": Decimal("4200"),
                        "learning_summary": "earnings_drift_v1 - active, 58.0% win rate (+$4,200.00 total P&L). Latest learning: Tighten low-volume gap entries (confidence 0.78); recommendation: tighten sizing after low-volume opens.",
                    },
                ),
                "strategy_proposals": (
                    {
                        "proposed_strategy_id": "semis_readthrough_v1",
                        "proposal_status": "accepted",
                        "proposal_status_label": "Accepted",
                    },
                ),
                "observability": {
                    "funnel": (
                        {"label": "Learning Factors Created", "count": 1},
                        {"label": "Applied Today", "count": 1},
                        {"label": "Strategy Proposals", "count": 1},
                        {"label": "New Strategy Definitions", "count": 1},
                        {"label": "Promoted", "count": 1},
                    ),
                    "promotion_breakdown": (
                        {"label": "Shadow", "count": 1},
                        {"label": "Experimental", "count": 0},
                        {"label": "Active", "count": 0},
                    ),
                    "weight_inputs": (
                        {
                            "factor_key": "lf-risk",
                            "title": "Tighten low-volume gap entries",
                            "scope_label": "Strategy",
                            "effect_summary": "increase score",
                        },
                    ),
                },
            },
            "ops_cost": {
                "llm_usage": (
                    {
                        "pipeline_name": "trading",
                        "provider": "openai",
                        "model": "gpt-5",
                        "estimated_cost": Decimal("12.30"),
                    },
                ),
                "provider_usage": (
                    {
                        "provider": "alpaca",
                        "endpoint": "market_bars",
                        "status": "succeeded",
                        "status_label": "Succeeded",
                        "cache_status": "miss",
                        "cache_status_label": "Cache Miss",
                    },
                ),
            },
            "risk_macro": {
                "events": (
                    {"event_type_label": "Own Company Earnings"},
                ),
                "exposures": (
                    {"factor_type": "sector", "factor_name": "Technology", "exposure": Decimal("5.2757000000000005")},
                ),
            },
            "exposure_summary": {
                "count": 1,
                "total_exposure": Decimal("5.2757000000000005"),
            },
            "event_summary": {
                "count": 1,
            },
            "llm_usage_summary": {
                "count": 1,
                "estimated_cost": Decimal("12.30"),
            },
            "llm_usage_daily": (
                {
                    "period_label": "2026-07-04",
                    "pipeline_name": "trading",
                    "provider": "openai",
                    "model": "gpt-5",
                    "event_count": 1,
                    "total_tokens": 1200,
                    "estimated_cost": Decimal("12.30"),
                    "avg_latency_ms": 800,
                    "status_label": "Succeeded",
                },
            ),
            "llm_usage_monthly": (
                {
                    "period_label": "2026-07",
                    "pipeline_name": "trading",
                    "provider": "openai",
                    "model": "gpt-5",
                    "event_count": 1,
                    "total_tokens": 1200,
                    "estimated_cost": Decimal("12.30"),
                    "avg_latency_ms": 800,
                    "status_label": "Succeeded",
                },
            ),
            "provider_usage_summary": {
                "count": 1,
            },
        },
    }


def test_build_header_converts_notional_gross_exposure_to_ratio():
    from src.web.routers.today import _build_header

    latest_risk = SimpleNamespace(
        gross_exposure=Decimal("49170.6164"),
        account_equity=Decimal("1000000"),
        risk_appetite="balanced",
        decision_time=datetime(2026, 6, 20, 13, 0, tzinfo=timezone.utc),
    )

    header = _build_header(
        latest_portfolio=None,
        latest_risk=latest_risk,
        trade_rows=[],
        latest_reflection=None,
        latest_macro_snapshot=None,
    )

    assert header["gross_exposure"] == pytest.approx(0.0491706164)


def test_build_header_uses_open_position_unrealized_pnl_when_available():
    from src.web.routers.today import _build_header

    latest_portfolio = SimpleNamespace(
        snapshot_time=datetime(2026, 7, 6, 16, 0, tzinfo=timezone.utc),
        net_liquidation_value=Decimal("100000"),
        account_equity=Decimal("100000"),
        cash_balance=Decimal("50000"),
        day_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        buying_power=Decimal("100000"),
        stock_market_value=Decimal("3025"),
        option_market_value=Decimal("0"),
        total_margin_requirement=Decimal("0"),
    )
    positions = (
        {"ticker": "CRDO", "unrealized_pnl": Decimal("25.25")},
        {"ticker": "LITE", "unrealized_pnl": Decimal("-5.00")},
    )

    header = _build_header(
        latest_portfolio=latest_portfolio,
        latest_risk=None,
        trade_rows=[],
        latest_reflection=None,
        latest_macro_snapshot=None,
        positions=positions,
    )

    assert header["unrealized_pnl"] == Decimal("20.25")


class TestTodayDashboard:
    def test_root_redirects_to_today(self, client):
        response = client.get("/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/today"

    def test_get_today_dashboard_renders_portfolio_home_header_and_tabs(self, client):
        payload = _dashboard_payload()
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=portfolio")

        assert response.status_code == 200
        assert 'href="/static/style.css?v=' in response.text
        assert "<h1>Today</h1>" in response.text
        assert "today-shell" in response.text
        assert "kpi-cards" in response.text
        assert "kpi-context" in response.text
        assert "today-global-tabs" in response.text
        assert "today-workspace" in response.text
        assert "Portfolio" in response.text
        assert "Overview" in response.text
        assert "Trades" in response.text
        assert "Candidates" in response.text
        assert "Risk &amp; Macro" in response.text
        assert "System" in response.text
        assert "Learning &amp; Strategies" not in response.text
        assert "Ops &amp; Cost" not in response.text
        assert "Account Equity" in response.text
        assert "Day P&amp;L" in response.text
        assert "Unrealized P&amp;L" in response.text
        assert "Realized P&amp;L" in response.text
        assert "Net / Gross Exp." in response.text
        assert "Buying Power" in response.text
        assert "Margin Util." in response.text
        assert "Open Alerts" in response.text
        assert "Pre-open Job" in response.text
        assert "$1,000,000" in response.text
        assert "$1,250" in response.text
        assert "$820" in response.text
        assert "Ready for Review" not in response.text
        assert "Needs Review" not in response.text
        assert "trades-canvas" not in response.text
        assert "TSLA" not in response.text
        assert "AI Infrastructure" not in response.text
        assert "gpt-5" not in response.text
        assert "surface-table-wrap" in response.text
        assert "surface-block" in response.text
        assert "surface-block-count" in response.text
        assert "today-global-tab active" in response.text
        assert 'href="/today?tab=overview"' in response.text
        assert 'href="/today?tab=system"' in response.text

    def test_trades_tab_only_renders_trades_workspace_body(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL")

        assert response.status_code == 200
        assert "trades-canvas" in response.text
        assert "Evidence" in response.text
        assert "Signal Summary" not in response.text
        assert "Breakout confirmed + risk approved" in response.text
        assert 'data-testid="trade-plan"' in response.text
        assert 'data-testid="rationale-evidence"' in response.text
        assert 'data-testid="bull-bear"' not in response.text
        assert 'data-testid="signal-groups"' not in response.text
        assert "ticker-card-meta" in response.text
        assert "card-decision-tag" in response.text
        assert "trade-header-table" in response.text
        assert "AI Infrastructure" not in response.text
        assert "gpt-5" not in response.text
        assert "Stock Positions" not in response.text
        assert 'data-bucket="watch"' not in response.text

    def test_trade_detail_drilldown_renders_when_decision_selected(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&decision_id=decision-action&detail_tab=decisions")

        assert response.status_code == 200
        assert "Latest Decision" in response.text
        assert "Enter Long" in response.text
        assert "Breakout confirmed + risk approved" in response.text
        assert "Within Limits" in response.text
        assert "within_limits" not in response.text
        assert 'data-testid="trade-plan"' in response.text
        assert 'data-testid="rationale-evidence"' in response.text
        assert 'data-testid="bull-bear"' not in response.text
        assert 'data-testid="signal-groups"' not in response.text
        assert "Breakout remains valid after the catalyst." in response.text
        assert "Add on closing strength." in response.text
        assert "relative strength is improving" in response.text
        assert "5.0%" in response.text
        assert 'data-panel="timeline"' not in response.text
        assert 'href="/today?tab=trades&ticker=AAPL&detail_tab=trend"' not in response.text
        assert 'href="/today?tab=trades&ticker=AAPL&detail_tab=decisions"' not in response.text
        assert 'href="/today?tab=trades&ticker=AAPL&detail_tab=risk"' not in response.text
        assert "Raw JSON" not in response.text
        assert "Risk Posture" not in response.text
        assert "Primary strategy selected" not in response.text

    def test_today_dashboard_renders_ticker_workspace_sections(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL")

        assert response.status_code == 200
        assert "trades-canvas" in response.text
        assert "ticker-workspace" in response.text
        assert "ticker-detail-hero" in response.text
        assert "Action Now" in response.text
        assert "Open Positions" in response.text
        assert "Closed Today" in response.text
        assert "Needs Re-evaluation" in response.text
        assert "Watch" in response.text
        assert "Latest Decision" in response.text
        assert "Open Position" in response.text
        assert "Latest decision: No Trade" in response.text
        assert "Enter Long" in response.text
        assert "Event / News Summary" in response.text
        assert "Raised guidance: Demand improved across core products." in response.text
        assert "Readthrough from MU" in response.text
        assert "Risk Manager" in response.text
        assert "Applied rules (2)" in response.text
        assert "Lookahead risk" in response.text
        assert "Hedge overlay" in response.text
        assert "Long 10 shares" in response.text
        assert 'data-testid="history-highlights"' in response.text
        assert "History Highlights" in response.text
        assert "sticky-rail" in response.text
        # restructured away:
        assert "ticker-support-grid" not in response.text
        assert "ticker-detail-nav" not in response.text
        assert "Signal Summary" not in response.text
        assert "Position / Execution State" not in response.text
        assert 'data-panel="timeline"' not in response.text
        assert 'data-panel="trend"' not in response.text
        assert 'data-panel="decisions"' not in response.text
        assert 'data-panel="risk"' in response.text
        assert "Raw JSON" not in response.text
        assert "Workspace Detail JSON" not in response.text
        assert "Risk JSON" not in response.text

    def test_trades_workspace_formats_lifecycle_timestamps_without_raw_iso_seconds(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        payload["ticker_workspace"]["detail"]["lifecycle"]["closed_at"] = "2026-06-05T20:02:00Z"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL")

        assert response.status_code == 200
        assert 'datetime="2026-06-05T14:32:00Z"' in response.text
        assert 'datetime="2026-06-05T20:02:00Z"' in response.text
        assert 'data-local-time-format="datetime"' in response.text
        assert ">2026-06-05T14:32:00Z<" not in response.text
        assert ">2026-06-05T20:02:00Z<" not in response.text

    # NOTE: the timeline-panel / detail_tab rendering tests were removed —
    # the verbose timeline section was replaced by the distilled History
    # Highlights block in _tab_trades.html. detail_tab normalization is still
    # covered by the load_today_dashboard tests below.

    def test_risk_macro_tab_renders_summary_first_structure(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "risk-macro"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=risk-macro")

        assert response.status_code == 200
        assert "Risk Status" in response.text
        assert "Top Risk Sources" in response.text
        assert "Other Risk Actions" not in response.text
        assert "Data / Model Availability" in response.text
        assert "Advanced Risk Audit" not in response.text
        assert "Within Limits" in response.text
        assert "Technology concentration" in response.text
        assert "Macro regime unavailable" in response.text
        assert "macro-strip" in response.text
        assert 'data-testid="economic-calendar"' in response.text
        assert 'data-testid="upcoming-earnings"' in response.text
        assert 'data-local-time-format="month_day_time"' in response.text
        assert 'data-local-time-format="month_day"' in response.text
        assert "AAPL" in response.text
        assert "earnings-tag" in response.text
        assert "earnings-tile" not in response.text
        assert "HIGH" in response.text
        assert "US CPI" in response.text
        assert ">2026-06-03T18:00:00Z<" not in response.text
        assert "direct earnings gap risk" not in response.text
        assert "Block New Entry" not in response.text
        assert "Own-event risk is inside the active trade horizon." not in response.text
        assert "block_open" not in response.text
        assert "trades-canvas" not in response.text
        assert "AI Infrastructure" not in response.text

    def test_risk_macro_tab_explains_missing_economic_calendar(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "risk-macro"
        payload["risk_macro"] = {
            **payload["risk_macro"],
            "events": tuple(
                row
                for row in payload["risk_macro"]["events"]
                if "earn" in str(row.get("event_type_label") or row.get("event_type") or "").lower()
            ),
        }
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=risk-macro")

        assert response.status_code == 200
        assert "No upcoming US macro events are loaded for this decision window." in response.text
        assert "No economic calendar rows are currently visible." not in response.text

    def test_portfolio_tab_omits_attention_modules(self, client):
        # Attention (review / alerts / material changes) now lives on the
        # Overview tab; Portfolio focuses on positions, exposure, and P&L.
        payload = _dashboard_payload()
        payload["selected_tab"] = "portfolio"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=portfolio")

        assert response.status_code == 200
        assert "attention-feed" not in response.text
        assert "Ready for Review" not in response.text
        assert "Closed recently and ready for review" not in response.text
        assert "Relative strength improved vs QQQ" not in response.text

    def test_overview_tab_renders_unified_attention_feed(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "overview"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=overview")

        assert response.status_code == 200
        assert "Command Center" in response.text
        assert "attention-feed-list" in response.text
        assert "attn-2col" in response.text
        assert "Needs Attention" in response.text
        # NVDA appears as both a live alert and a review -> one merged card
        # carrying both badges; AAPL is a signal change.
        assert "attention-badge-alert" in response.text
        assert "attention-badge-review" in response.text
        assert "attention-badge-signal" in response.text
        assert "Raised guidance" in response.text
        assert "Closed recently and ready for review" in response.text
        assert "Relative strength improved vs QQQ" in response.text
        assert "Ready for Review" in response.text
        assert "trades-canvas" not in response.text

    def test_overview_tab_collapses_empty_attention_to_single_line(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "overview"
        payload["overview"]["command_center"] = {
            "needs_review": (),
            "open_positions": (),
            "system_issues": (),
        }
        payload["overview"]["live_alerts"] = ()
        payload["overview"]["material_changes"] = ()
        payload["overview"]["attention_feed"] = ()
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=overview")

        assert response.status_code == 200
        assert "Nothing needs attention right now." in response.text
        assert "attention-feed-row" not in response.text

    def test_portfolio_tab_renders_summary_first_structure(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "portfolio"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=portfolio")

        assert response.status_code == 200
        assert "Stock Positions" in response.text
        assert "Option Positions" in response.text
        assert "Hedge Overlays" in response.text
        assert "surface-table-wrap" in response.text
        assert "$2,145" in response.text
        assert "$420" in response.text
        assert "Tactical Stock Trade" in response.text
        assert "Long Call" in response.text
        assert "Long Put" in response.text
        assert "2 positions" in response.text
        assert "$3,696.00 market value" in response.text
        assert "$300" in response.text
        assert "1 strategies" in response.text
        assert "$840.75" in response.text
        assert "max loss $420.00" in response.text
        assert "tactical_stock_trade" not in response.text
        assert "long_call" not in response.text
        assert "surface-block" in response.text
        assert "surface-block-count" in response.text
        assert "trades-canvas" not in response.text

    def test_portfolio_tab_renders_portfolio_analytics_when_available(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "portfolio"
        payload["portfolio"]["analytics"] = {
            "point_count": 4,
            "equity_chart": {
                "points": "0,100 10,120 20,114 30,126",
            },
            "pnl_chart": {
                "bars": (
                    {"x": 0, "y": 80, "w": 8, "h": 0, "positive": True},
                    {"x": 12, "y": 40, "w": 8, "h": 40, "positive": True},
                    {"x": 24, "y": 90, "w": 8, "h": 10, "positive": False},
                    {"x": 36, "y": 50, "w": 8, "h": 30, "positive": True},
                ),
                "baseline_y": 80,
                "bar_width": 8,
            },
            "equity_start": 100.0,
            "equity_end": 126.0,
            "equity_min": 100.0,
            "equity_max": 126.0,
            "metrics": {
                "total_return": 0.26,
                "max_drawdown": 0.05,
                "win_days": 2,
                "loss_days": 1,
                "profitable_days_pct": 0.6666666667,
                "best_day": 20.0,
                "worst_day": -6.0,
                "avg_day_pnl": 8.6666666667,
                "daily_profit_factor": 5.3333333333,
            },
        }
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=portfolio")

        assert response.status_code == 200
        assert 'data-testid="portfolio-analytics"' in response.text
        assert "Account Equity" in response.text
        assert "Daily P&amp;L" in response.text
        assert "Total Return" in response.text
        assert "Max Drawdown" in response.text
        assert "Best Day" in response.text
        assert "Worst Day" in response.text
        assert 'class="portfolio-chart equity-chart"' in response.text
        assert 'class="portfolio-chart pnl-chart"' in response.text
        assert "equity-line" in response.text
        assert "pnl-bar-pos" in response.text or "pnl-bar-neg" in response.text

    def test_portfolio_tab_formats_stock_position_strategy_labels_and_unknowns(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "portfolio"
        payload["portfolio"]["positions"] = (
            {
                "ticker": "AAPL",
                "trade_identity": "tactical_stock_trade",
                "trade_identity_label": "Tactical Stock Trade",
                "strategy_id": "relative_strength_breakout_v1",
                "quantity": Decimal("10"),
                "market_value": Decimal("2145.20"),
                "unrealized_pnl": Decimal("325.10"),
            },
            {
                "ticker": "NVDA",
                "trade_identity": "tactical_stock_trade",
                "trade_identity_label": "Tactical Stock Trade",
                "strategy_id": None,
                "quantity": Decimal("5"),
                "market_value": Decimal("1550.80"),
                "unrealized_pnl": Decimal("-25.10"),
            },
        )
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=portfolio")

        assert response.status_code == 200
        assert "Relative Strength Breakout V1" in response.text
        assert ">None<" not in response.text
        assert "<td>—</td>" in response.text

    def test_candidates_tab_renders_summary_and_operations_modules(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "candidates"
        payload["candidates"]["action_queue"] = (
            {
                "ticker": "TSLA",
                "label": "Pinned",
                "summary": "Review Only because post-event review. Latest result: Still on watch.",
            },
            {
                "ticker": "MSFT",
                "label": "No clean entry, so no trade",
                "summary": "Negative catalyst detected. No clean entry, so no trade. Watch Only.",
            },
        )
        payload["candidates"]["manual_review_queue"] = (
            {
                "ticker": "TSLA",
                "status_label": "Pinned",
                "mode_label": "Review Only",
                "operator_summary": "Review Only because post-event review. Latest result: Still on watch.",
                "reason": "post-event review",
                "last_evaluated_label": "6m ago",
                "decision_state_label": "Enter Long",
                "execution_state_label": "Risk blocked",
                "latest_block_reason": "Awaiting fresh event-risk snapshot",
                "dismiss_form_action": "/today/manual-requests/request-1/dismiss",
                "linked_detail_url": "/today?tab=trades&ticker=TSLA&detail_tab=decisions",
                "degraded_linkage_copy": None,
            },
        )
        payload["candidates"]["decision_readout"] = (
            {
                "ticker": "AAPL",
                "primary_reason": "Momentum setup with clean catalyst.",
                "current_outcome_label": "Ready for review",
                "trade_identity_label": "Action Now",
                "strategy_label": "Gap continuation",
                "confidence": 0.91,
                "selection_reason": "relative strength and catalyst quality remain aligned",
                "signal_bullets": (
                    "Technical: 20d return 8.26%, relative volume 0.78.",
                    "Fundamental: quality 0.98, revenue growth 0.65, margin trend 0.93.",
                    "News: sentiment positive, 2 high-signal items / 24h.",
                ),
                "risk_tags": ("Risk tags: gap risk, momentum.",),
                "invalidators": ("Invalidators: loses VWAP.",),
                "news": (
                    {
                        "title": "Micron raises guidance",
                        "summary": "Memory demand improved across AI infrastructure.",
                        "source_ticker": "MU",
                        "readthrough_label": "Readthrough from MU",
                    },
                ),
                "evaluation_count": 2,
                "evaluations": (
                    {
                        "decision_time": "2026-06-16T13:35:00Z",
                        "outcome": "Ready for review",
                        "strategy_label": "Gap continuation",
                        "confidence": 0.91,
                        "summary": "Momentum setup with clean catalyst.",
                    },
                    {
                        "decision_time": "2026-06-16T13:34:00Z",
                        "outcome": "Ready for review",
                        "strategy_label": "Pullback reclaim",
                        "confidence": 0.77,
                        "summary": "Alternative pullback setup.",
                    },
                ),
                "alternatives": (
                    {
                        "strategy_label": "Pullback reclaim",
                        "operator_summary": "Alternative pullback setup.",
                        "confidence": 0.77,
                    },
                    {
                        "strategy_label": "RS breakout",
                        "operator_summary": "Secondary continuation lens.",
                        "confidence": 0.73,
                    },
                    {
                        "strategy_label": "Reversal try",
                        "operator_summary": "Lower-ranked reversal setup.",
                        "confidence": 0.41,
                    },
                ),
                "detail_internal_ids": {"strategy_match": "gap_continuation_v1"},
            },
        )
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=candidates")

        assert response.status_code == 200
        assert "Agent-Scored Candidates" in response.text
        assert "Manual Watchlist" in response.text
        assert "panel" in response.text
        # removed clutter: standalone Action Queue + the extra count tiles
        assert "Action Queue" not in response.text
        assert "Decision Readout" not in response.text
        assert "Theme Monitor" not in response.text
        assert "Review Only" in response.text
        assert "Still on watch" in response.text
        assert "Momentum setup with clean catalyst." in response.text
        # thesis now lives in the row's Primary Reason column; detail = tabs only
        assert "Recent News" in response.text
        assert "Alternatives" in response.text
        assert "History" in response.text
        assert "Confidence" in response.text
        assert "0.91" in response.text
        assert "relative strength and catalyst quality remain aligned" in response.text
        assert 'data-local-time-format="datetime"' in response.text
        assert ">2026-06-16T13:35:00Z<" not in response.text
        assert "Technical: 20d return 8.26%, relative volume 0.78." in response.text
        assert "Readthrough from MU" in response.text
        assert "Risk tags: gap risk, momentum." in response.text
        assert "Invalidators: loses VWAP." in response.text
        assert "Duplicate Rows" not in response.text
        assert "Pullback reclaim" in response.text
        assert "0.77" in response.text
        assert "Awaiting fresh event-risk snapshot" in response.text
        assert "Advanced Universe Context" not in response.text
        assert "Source ID:" not in response.text
        assert "Outcome ID:" not in response.text
        assert "Trade Identity ID:" not in response.text
        assert "Strategy ID:" not in response.text
        assert "Core Index / Active" not in response.text
        assert "AI Infrastructure" in response.text
        assert "theme-chip-list" in response.text
        assert "scroll-panel" in response.text
        assert "scroll-rail" in response.text
        assert response.text.count('class="dtable candidate-stable-table"') == 2
        assert response.text.count('class="candidate-col-symbol"') == 2
        assert response.text.count('class="candidate-col-reason"') == 2
        assert 'data-testid="candidate-group-AAPL"' in response.text
        assert "trades-canvas" not in response.text
        assert "Signal Summary" not in response.text

    def test_candidates_tab_renders_universe_filter_editor(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "candidates"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=candidates")

        assert response.status_code == 200
        assert 'action="/today/universe-filter"' in response.text
        assert 'name="excluded_sectors"' in response.text
        assert 'value="Utilities"' in response.text
        assert 'name="manual_exclude"' in response.text
        assert 'value="GME"' in response.text

    def test_load_today_dashboard_prefers_selected_audit_detail_confidence_over_workspace_zero(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()
        trade_rows = [
            {
                "trading_decision_id": "decision-nvda",
                "decision_time": datetime(2026, 6, 3, 23, 25, 34, tzinfo=timezone.utc),
                "created_at": datetime(2026, 6, 3, 23, 25, 34, tzinfo=timezone.utc),
                "ticker": "NVDA",
                "decision": "enter_long",
                "instrument_type": "stock",
                "trade_identity": "tactical_stock_trade",
                "selected_strategy_id": "breakout_v1",
                "expression_bucket_id": "long_stock",
                "approved_weight": Decimal("0.05"),
                "confidence": Decimal("0.0"),
                "risk_status": "approved",
                "order_status": "accepted",
                "material_signal_change": False,
            }
        ]
        selected_detail = {
            "trading_decision_id": "decision-nvda",
            "ticker": "NVDA",
            "decision": "enter_long",
            "decision_time": datetime(2026, 6, 3, 23, 25, 34, tzinfo=timezone.utc),
            "strategy_id": "breakout_v1",
            "expression_bucket_id": "long_stock",
            "trade_identity": "tactical_stock_trade",
            "confidence": Decimal("0.74"),
            "thesis": "Breakout remains valid after the open.",
            "key_drivers": [],
            "counterarguments": [],
            "invalidators": [],
            "metadata_json": {},
            "risk_decision": None,
            "signal_snapshot": {},
            "strategy_scores": (),
            "outcomes": (),
        }

        with ExitStack() as stack:
            stack.enter_context(patch("src.web.routers.today._load_trade_rows", return_value=trade_rows))
            stack.enter_context(patch("src.web.routers.today._load_trade_detail", return_value=selected_detail))
            stack.enter_context(patch("src.web.routers.today._load_positions", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_option_positions", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_recent_closed_positions", return_value=()))
            stack.enter_context(
                patch(
                    "src.web.routers.today._load_risk_by_ticker",
                    return_value={"NVDA": {"status": "approved", "reason": "within_limits"}},
                )
            )
            stack.enter_context(
                patch(
                    "src.web.routers.today._load_signal_history_by_ticker",
                    return_value={"NVDA": {"technical": [], "summary": [], "timeline": []}},
                )
            )
            stack.enter_context(patch("src.web.routers.today._load_news_by_ticker", return_value={}))
            stack.enter_context(patch("src.web.routers.today._load_fundamentals_by_ticker", return_value={}))
            stack.enter_context(patch("src.web.routers.today._load_candidate_rows", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_manual_requests", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_portfolio_intents", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_relationships", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_peer_baskets", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_themes", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_live_alerts", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_material_changes", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_risk_exposures", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_learning_factors", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_performance", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_proposals", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_definitions", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_evaluation_results", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_llm_usage", return_value=()))
            dashboard = load_today_dashboard(
                session,
                selected_tab="trades",
                decision_id="decision-nvda",
                selected_ticker="NVDA",
            )

        assert (
            dashboard["ticker_workspace"]["detail"]["latest_conclusion"]["trade_decision"]["confidence"] == Decimal("0.74")
        )

    def test_system_tab_renders_learning_and_ops_modules(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "system"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=system")

        assert response.status_code == 200
        assert "System" in response.text
        assert "System Issues" in response.text
        assert "Reflection Snapshot" in response.text
        assert "Strategy Pipeline" in response.text
        assert "Strategy Performance" in response.text
        assert "LLM Spend" in response.text
        assert "Usage Ledger" in response.text
        assert "Provider Usage" in response.text
        assert "Bullish catalyst continuation respected" in response.text
        assert "Strategy Performance" in response.text
        assert "$4,200" in response.text
        assert "1 active strategy tracked today." in response.text
        assert "Latest learning: Tighten low-volume gap entries" in response.text
        assert "Tighten low-volume gap entries" in response.text
        assert "Succeeded" in response.text
        assert "Accepted" in response.text
        assert "Active" in response.text
        assert "Strategy" in response.text
        assert "gpt-5" in response.text
        assert "market_bars" in response.text
        assert "succeeded" not in response.text
        assert "accepted" not in response.text
        assert "tracked strategy" in response.text
        assert "trades-canvas" not in response.text

    def test_system_tab_aggregate_lines_render_for_risk_exposure_and_llm_usage(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "system"
        payload["system"]["exposure_summary"]["total_exposure"] = Decimal("50157.226068")
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=system")

        assert response.status_code == 200
        assert "1 factor" in response.text
        assert "$50,157.23 exposure" in response.text
        assert "50157.226068 exposure" not in response.text
        assert "1 event" in response.text
        assert "$12.30 estimated cost" in response.text
        assert "surface-block" in response.text
        assert "trades-canvas" not in response.text

    def test_timeline_renders_as_history_highlights(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        payload["ticker_workspace"]["selected_detail_tab"] = "timeline"
        payload["ticker_workspace"]["detail"]["tabs"]["timeline"] = (
            {
                "title": "Pre Open Baseline",
                "time_label": "2026-06-18 16:30 UTC",
                "change_type": "baseline",
                "signal_summary": ("Sentiment neutral", "risk approved"),
                "trade_decision": {"label": "Watch", "summary": "Waiting for confirmation"},
                "risk": {"status_label": "Approved", "summary": "Within limits"},
                "change_summary": (),
            },
            {
                "title": "Pre Open Rerun",
                "time_label": "2026-06-18 16:42 UTC",
                "change_type": "material_change",
                "signal_summary": ("Sentiment negative", "direct negative catalyst: General News"),
                "trade_decision": {"label": "No Trade", "summary": "Catalyst quality faded"},
                "risk": {"status_label": "Reduced", "summary": "Event risk increased"},
                "change_summary": ("sentiment neutral -> negative", "risk approved -> reduced"),
            },
        )
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL&detail_tab=timeline")

        assert response.status_code == 200
        assert "History Highlights" in response.text
        assert "history-hl" in response.text
        assert '<div class="history-hl">' in response.text
        assert '<table class="dtable history-table">' in response.text
        assert '<table class="dtable history-table history-hl">' not in response.text
        assert "2026-06-18 16:42 UTC" in response.text
        # each historical decision shows the agent's per-snapshot reasoning + the change deltas
        assert "Catalyst quality faded" in response.text
        assert "sentiment neutral -&gt; negative" in response.text
        # "Why This Decision" surfaces the agent-written thesis
        assert "Why This Decision" in response.text
        assert "hl-reasoning" in response.text
        assert 'data-panel="timeline"' not in response.text
        assert "ticker-detail-nav" not in response.text

    def test_trades_empty_rationale_copy_uses_quiet_standardized_text(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["bull_bear"]["bull_points"] = ()
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["bull_bear"]["bear_points"] = ()
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["signal_groups"] = ()
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL")

        assert response.status_code == 200
        assert "surface-empty-copy" in response.text
        assert "No bull points." in response.text
        assert "No signal groups." in response.text

    # Removed: Signal Summary primary/grouped sections no longer render — the
    # Signal Summary card was dropped (signals now live only under Evidence,
    # and timeline deltas under History Highlights).

    def test_portfolio_empty_state_uses_quiet_standardized_text(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "portfolio"
        payload["portfolio"]["positions"] = ()
        payload["portfolio"]["option_positions"] = ()
        payload["portfolio"]["hedge_overlays"] = ()
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=portfolio")

        assert response.status_code == 200
        assert "No open stock positions." in response.text
        assert "No open option positions." in response.text
        assert "No hedge overlays." in response.text
        assert response.text.count("quiet-empty") >= 3

    def test_trades_no_selected_ticker_empty_state_uses_standardized_copy(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        payload["ticker_workspace"]["selected_ticker"] = None
        payload["ticker_workspace"]["detail"] = None
        payload["ticker_workspace"]["selected_detail_item"] = None
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades")

        assert response.status_code == 200
        assert "No ticker selected." in response.text
        assert "surface-empty-copy" in response.text
        assert "Latest Conclusion" not in response.text

    def test_today_dashboard_renders_selectable_ticker_cards_and_active_marker(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL&decision_id=decision-action")

        assert response.status_code == 200
        assert '/today?tab=trades&ticker=AAPL' in response.text
        assert '/today?tab=trades&ticker=NVDA' in response.text
        assert '/today?tab=trades&ticker=MSFT' in response.text
        assert 'decision_id=decision-action' not in response.text
        assert 'aria-current="page"' in response.text
        assert 'data-selected-ticker="AAPL"' in response.text

    def test_today_dashboard_passes_selected_ticker_query_param_to_loader(self, client):
        payload = _dashboard_payload()
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload) as load_today_dashboard:
            response = client.get("/today?ticker=NVDA")

        assert response.status_code == 200
        load_today_dashboard.assert_called_once()
        assert load_today_dashboard.call_args.kwargs["selected_ticker"] == "NVDA"

    def test_today_dashboard_route_falls_back_to_highest_priority_ticker_for_invalid_query(self, client):
        session = _query_stub_session()
        trade_rows = _ticker_selection_trade_rows()
        selected_nvda_detail = _selected_trade_detail("NVDA")

        with _patched_today_route_dependencies(
            session,
            trade_rows=trade_rows,
            selected_detail=selected_nvda_detail,
        ) as load_trade_detail:
            response = client.get("/today?tab=trades&ticker=MSFT")

        assert response.status_code == 200
        assert 'data-selected-ticker="NVDA"' in response.text
        assert 'aria-current="page"' in response.text
        load_trade_detail.assert_called_once_with(session, "decision-action")

    def test_today_dashboard_route_falls_back_to_highest_priority_ticker_when_query_missing(self, client):
        session = _query_stub_session()
        trade_rows = _ticker_selection_trade_rows()
        selected_nvda_detail = _selected_trade_detail("NVDA")

        with _patched_today_route_dependencies(
            session,
            trade_rows=trade_rows,
            selected_detail=selected_nvda_detail,
        ) as load_trade_detail:
            response = client.get("/today?tab=trades")

        assert response.status_code == 200
        assert 'data-selected-ticker="NVDA"' in response.text
        assert 'aria-current="page"' in response.text
        load_trade_detail.assert_called_once_with(session, "decision-action")

    def test_today_dashboard_route_renders_empty_workspace_when_no_tickers_exist(self, client):
        session = _query_stub_session()

        with _patched_today_route_dependencies(
            session,
            trade_rows=[],
            selected_detail=None,
        ) as load_trade_detail:
            response = client.get("/today?tab=trades")

        assert response.status_code == 200
        assert "No tickers in the workstation yet." in response.text
        assert "Latest Conclusion" not in response.text
        load_trade_detail.assert_not_called()

    def test_load_today_dashboard_falls_back_to_highest_priority_ticker_for_invalid_query(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()
        trade_rows = _ticker_selection_trade_rows()
        selected_nvda_detail = _selected_trade_detail("NVDA")

        with (
            patch("src.web.routers.today._load_trade_rows", return_value=trade_rows),
            patch("src.web.routers.today._load_trade_detail", return_value=selected_nvda_detail) as load_trade_detail,
            patch("src.web.routers.today._load_positions", return_value=()),
            patch("src.web.routers.today._load_option_positions", return_value=()),
            patch("src.web.routers.today._load_hedge_overlays", return_value=()),
            patch("src.web.routers.today._load_live_alerts", return_value=()),
            patch("src.web.routers.today._load_material_changes", return_value=()),
            patch("src.web.routers.today._load_risk_exposures", return_value=()),
            patch("src.web.routers.today._load_candidate_rows", return_value=()),
            patch("src.web.routers.today._load_manual_requests", return_value=()),
            patch("src.web.routers.today._load_portfolio_intents", return_value=()),
            patch("src.web.routers.today._load_relationships", return_value=()),
            patch("src.web.routers.today._load_peer_baskets", return_value=()),
            patch("src.web.routers.today._load_themes", return_value=()),
            patch("src.web.routers.today._load_learning_factors", return_value=()),
            patch("src.web.routers.today._load_strategy_performance", return_value=()),
            patch("src.web.routers.today._load_strategy_proposals", return_value=()),
            patch("src.web.routers.today._load_strategy_definitions", return_value=()),
            patch("src.web.routers.today._load_strategy_evaluation_results", return_value=()),
            patch("src.web.routers.today._load_llm_usage", return_value=()),
        ):
            dashboard = load_today_dashboard(
                session,
                selected_tab="portfolio",
                decision_id=None,
                selected_ticker="MSFT",
            )

        assert dashboard["ticker_workspace"]["selected_ticker"] == "NVDA"
        assert dashboard["trades"]["selected_detail"]["ticker"] == "NVDA"
        load_trade_detail.assert_called_once_with(session, "decision-action")

    def test_load_today_dashboard_returns_empty_workspace_when_no_tickers_exist(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()

        with (
            patch("src.web.routers.today._load_trade_rows", return_value=[]),
            patch("src.web.routers.today._load_positions", return_value=()),
            patch("src.web.routers.today._load_option_positions", return_value=()),
            patch("src.web.routers.today._load_hedge_overlays", return_value=()),
            patch("src.web.routers.today._load_live_alerts", return_value=()),
            patch("src.web.routers.today._load_material_changes", return_value=()),
            patch("src.web.routers.today._load_risk_exposures", return_value=()),
            patch("src.web.routers.today._load_candidate_rows", return_value=()),
            patch("src.web.routers.today._load_manual_requests", return_value=()),
            patch("src.web.routers.today._load_portfolio_intents", return_value=()),
            patch("src.web.routers.today._load_relationships", return_value=()),
            patch("src.web.routers.today._load_peer_baskets", return_value=()),
            patch("src.web.routers.today._load_themes", return_value=()),
            patch("src.web.routers.today._load_learning_factors", return_value=()),
            patch("src.web.routers.today._load_strategy_performance", return_value=()),
            patch("src.web.routers.today._load_strategy_proposals", return_value=()),
            patch("src.web.routers.today._load_strategy_definitions", return_value=()),
            patch("src.web.routers.today._load_strategy_evaluation_results", return_value=()),
            patch("src.web.routers.today._load_llm_usage", return_value=()),
            patch("src.web.routers.today._load_trade_detail") as load_trade_detail,
        ):
            dashboard = load_today_dashboard(
                session,
                selected_tab="portfolio",
                decision_id=None,
                selected_ticker="NVDA",
            )

        assert dashboard["ticker_workspace"]["selected_ticker"] is None
        assert dashboard["ticker_workspace"]["detail"] is None
        assert dashboard["trades"]["selected_detail"] is None
        load_trade_detail.assert_not_called()

    def test_load_today_dashboard_splits_candidate_and_trade_surface_rows(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()
        candidate_rows = (
            {
                "ticker": "REVIEW",
                "selection_source": "manual_request",
                "result_status": "actionable_trade",
                "strategy_match": "breakout_v1",
                "candidate_score": 0.88,
                "decision_time": "2026-06-03T13:00:00Z",
            },
            {
                "ticker": "PAPER",
                "selection_source": "manual_request",
                "result_status": "actionable_trade",
                "strategy_match": "gap_continuation_v1",
                "candidate_score": 0.82,
                "decision_time": "2026-06-03T13:01:00Z",
            },
            {
                "ticker": "SCAN",
                "selection_source": "scanner",
                "result_status": "actionable_trade",
                "strategy_match": "catalyst_breakout_v1",
                "candidate_score": 0.79,
                "decision_time": "2026-06-03T13:02:00Z",
            },
            {
                "ticker": "WATCH",
                "selection_source": "scanner",
                "result_status": "ordinary_watch",
                "strategy_match": "oversold_bounce_v1",
                "candidate_score": 0.41,
                "decision_time": "2026-06-03T13:03:00Z",
            },
            {
                "ticker": "OPTION",
                "selection_source": "manual_request",
                "result_status": "ordinary_watch",
                "strategy_match": "option_monitor_v1",
                "candidate_score": 0.35,
                "decision_time": "2026-06-03T13:04:00Z",
            },
        )
        manual_requests = (
            {"ticker": "REVIEW", "mode": "review_only"},
            {"ticker": "PAPER", "mode": "paper_trade_eligible"},
            {"ticker": "OPTION", "mode": "paper_trade_eligible"},
        )
        trade_rows = [
            {
                "ticker": "TRADE",
                "decision": "no_trade",
                "created_at": "2026-06-03T13:05:00Z",
            }
        ]

        workspace_payload = {
            "selected_ticker": None,
            "buckets": {
                "action_now": [],
                "open_positions": [],
                "closed_today": [],
                "reviewing": [],
                "watch": [],
                "in_position": [],
            },
            "last_run_at": None,
            "detail": None,
        }

        with ExitStack() as stack:
            stack.enter_context(patch("src.web.routers.today._load_trade_rows", return_value=trade_rows))
            stack.enter_context(patch("src.web.routers.today._load_positions", return_value=()))
            stack.enter_context(
                patch(
                    "src.web.routers.today._load_option_positions",
                    return_value=(
                        {
                            "ticker": "OPTION",
                            "option_strategy_type": "broker_option_position",
                            "trade_identity": "tactical_option_trade",
                            "updated_at": "2026-06-03T13:04:30Z",
                        },
                    ),
                )
            )
            stack.enter_context(patch("src.web.routers.today._load_hedge_overlays", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_live_alerts", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_material_changes", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_risk_exposures", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_candidate_rows", return_value=candidate_rows))
            stack.enter_context(patch("src.web.routers.today._load_manual_requests", return_value=manual_requests))
            stack.enter_context(patch("src.web.routers.today._load_portfolio_intents", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_relationships", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_peer_baskets", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_themes", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_learning_factors", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_performance", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_proposals", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_definitions", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_evaluation_results", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_llm_usage", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_trade_detail", return_value=None))
            build_workspace = stack.enter_context(
                patch("src.web.routers.today.build_ticker_workspace", return_value=workspace_payload)
            )
            build_candidates = stack.enter_context(
                patch(
                    "src.web.routers.today.build_today_candidates_view",
                    return_value={
                        "decision_readout": (),
                        "action_queue": (),
                        "manual_review_queue": (),
                        "agent_candidates": (),
                        "manual_candidates": (),
                        "summary": {},
                    },
                )
            )
            load_today_dashboard(
                session,
                selected_tab="trades",
                decision_id=None,
                selected_ticker=None,
            )

        workspace_tickers = {
            row["ticker"] for row in build_workspace.call_args.kwargs["trade_rows"]
        }

        assert workspace_tickers == {"TRADE", "PAPER", "SCAN", "OPTION"}
        assert "REVIEW" not in workspace_tickers
        assert "OPTION" in workspace_tickers
        build_candidates.assert_called_once_with(
            rows=(),
            manual_requests=(),
            themes=(),
            active_universe_filter=None,
            portfolio_intents=(),
            relationships=(),
            peer_baskets=(),
            thesis_history_by_ticker={},
            news_by_ticker={},
        )

        with ExitStack() as stack:
            stack.enter_context(patch("src.web.routers.today._load_trade_rows", return_value=trade_rows))
            stack.enter_context(patch("src.web.routers.today._load_positions", return_value=()))
            stack.enter_context(
                patch(
                    "src.web.routers.today._load_option_positions",
                    return_value=(
                        {
                            "ticker": "OPTION",
                            "option_strategy_type": "broker_option_position",
                            "trade_identity": "tactical_option_trade",
                            "updated_at": "2026-06-03T13:04:30Z",
                        },
                    ),
                )
            )
            stack.enter_context(patch("src.web.routers.today._load_candidate_rows", return_value=candidate_rows))
            stack.enter_context(patch("src.web.routers.today._load_manual_requests", return_value=manual_requests))
            stack.enter_context(patch("src.web.routers.today._load_portfolio_intents", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_relationships", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_peer_baskets", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_themes", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_news_by_ticker", return_value={}))
            build_candidates = stack.enter_context(
                patch(
                    "src.web.routers.today.build_today_candidates_view",
                    return_value={
                        "decision_readout": (),
                        "action_queue": (),
                        "manual_review_queue": (),
                        "agent_candidates": (),
                        "manual_candidates": (),
                        "summary": {},
                    },
                )
            )
            load_today_dashboard(
                session,
                selected_tab="candidates",
                decision_id=None,
                selected_ticker=None,
            )

        candidate_tickers = {
            row["ticker"] for row in build_candidates.call_args.kwargs["rows"]
        }
        assert candidate_tickers == {"REVIEW", "WATCH"}

    def test_load_today_dashboard_populates_trade_bucket_recency_labels(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()
        recent_trade_time = datetime.now(timezone.utc).replace(microsecond=0)
        trade_rows = [
            {
                "trading_decision_id": "decision-action",
                "ticker": "NVDA",
                "decision": "no_trade",
                "risk_status": "approved",
                "order_status": None,
                "material_signal_change": False,
                "created_at": recent_trade_time.isoformat().replace("+00:00", "Z"),
            }
        ]

        with (
            patch("src.web.routers.today._load_trade_rows", return_value=trade_rows),
            patch("src.web.routers.today._load_positions", return_value=()),
            patch("src.web.routers.today._load_option_positions", return_value=()),
            patch("src.web.routers.today._load_hedge_overlays", return_value=()),
            patch("src.web.routers.today._load_live_alerts", return_value=()),
            patch("src.web.routers.today._load_material_changes", return_value=()),
            patch("src.web.routers.today._load_risk_exposures", return_value=()),
            patch("src.web.routers.today._load_candidate_rows", return_value=()),
            patch("src.web.routers.today._load_manual_requests", return_value=()),
            patch("src.web.routers.today._load_portfolio_intents", return_value=()),
            patch("src.web.routers.today._load_relationships", return_value=()),
            patch("src.web.routers.today._load_peer_baskets", return_value=()),
            patch("src.web.routers.today._load_themes", return_value=()),
            patch("src.web.routers.today._load_learning_factors", return_value=()),
            patch("src.web.routers.today._load_strategy_performance", return_value=()),
            patch("src.web.routers.today._load_strategy_proposals", return_value=()),
            patch("src.web.routers.today._load_strategy_definitions", return_value=()),
            patch("src.web.routers.today._load_strategy_evaluation_results", return_value=()),
            patch("src.web.routers.today._load_llm_usage", return_value=()),
            patch("src.web.routers.today._load_trade_detail", return_value=_selected_trade_detail("NVDA")),
        ):
            dashboard = load_today_dashboard(
                session,
                selected_tab="trades",
                decision_id=None,
                selected_ticker="NVDA",
            )

        item = dashboard["ticker_workspace"]["buckets"]["watch"][0]
        assert item["recency_label"] == "just now"
        assert item["last_updated_label"] is not None

    def test_load_today_dashboard_normalizes_invalid_tab_and_detail_query_state(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()
        trade_rows = _ticker_selection_trade_rows()
        selected_nvda_detail = {
            "ticker": "NVDA",
            "latest_conclusion": {
                "trade_decision": {"label": "Enter Long"},
                "signal_summary": {"summary_bullets": ()},
                "risk_summary": {},
                "position_execution": {},
            },
                "tabs": {
                    "timeline": (
                    {
                        "title": "Decision submitted",
                        "summary": "Trading decision entered long",
                        "detail": "Primary timeline detail",
                    },
                    {
                        "title": "Signal snapshot updated",
                        "summary": "Relative strength improved",
                        "detail": "Secondary timeline detail",
                    },
                    ),
                    "trend": {"technical": (), "news": (), "fundamental": ()},
                    "decisions": (),
                    "risk": {"history": ()},
                },
            }

        with (
            patch("src.web.routers.today._load_trade_rows", return_value=trade_rows),
            patch("src.web.routers.today._load_trade_detail", return_value=selected_nvda_detail),
            patch("src.web.routers.today._load_positions", return_value=()),
            patch("src.web.routers.today._load_option_positions", return_value=()),
            patch("src.web.routers.today._load_hedge_overlays", return_value=()),
            patch("src.web.routers.today._load_live_alerts", return_value=()),
            patch("src.web.routers.today._load_material_changes", return_value=()),
            patch("src.web.routers.today._load_risk_exposures", return_value=()),
            patch("src.web.routers.today._load_candidate_rows", return_value=()),
            patch("src.web.routers.today._load_manual_requests", return_value=()),
            patch("src.web.routers.today._load_portfolio_intents", return_value=()),
            patch("src.web.routers.today._load_relationships", return_value=()),
            patch("src.web.routers.today._load_peer_baskets", return_value=()),
            patch("src.web.routers.today._load_themes", return_value=()),
            patch("src.web.routers.today._load_learning_factors", return_value=()),
            patch("src.web.routers.today._load_strategy_performance", return_value=()),
            patch("src.web.routers.today._load_strategy_proposals", return_value=()),
            patch("src.web.routers.today._load_strategy_definitions", return_value=()),
            patch("src.web.routers.today._load_strategy_evaluation_results", return_value=()),
            patch("src.web.routers.today._load_llm_usage", return_value=()),
        ):
            dashboard = load_today_dashboard(
                session,
                selected_tab="not-a-real-tab",
                decision_id=None,
                selected_ticker="NVDA",
                selected_detail_tab="not-a-real-detail-tab",
                selected_detail_item_index=99,
            )

        assert dashboard["selected_tab"] == "overview"
        assert dashboard["ticker_workspace"]["selected_detail_tab"] == "timeline"
        assert dashboard["ticker_workspace"]["selected_detail_item_index"] == 0
        assert dashboard["ticker_workspace"]["selected_detail_item"]["title"] == "Decision submitted"

    def test_load_today_dashboard_preserves_rich_workspace_detail_and_attaches_audit_detail(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()
        trade_rows = _ticker_selection_trade_rows()
        selected_nvda_detail = _selected_trade_detail("NVDA")

        with ExitStack() as stack:
            stack.enter_context(patch("src.web.routers.today._load_trade_rows", return_value=trade_rows))
            stack.enter_context(patch("src.web.routers.today._load_trade_detail", return_value=selected_nvda_detail))
            stack.enter_context(patch("src.web.routers.today._load_positions", return_value=()))
            stack.enter_context(
                patch(
                    "src.web.routers.today._load_signal_history_by_ticker",
                    return_value={
                        "NVDA": {
                            "technical": [
                                {"label": "price", "points": [1, 2, 3], "summary": "Above support"},
                                {
                                    "label": "relative_strength",
                                    "points": [3, 4, 5],
                                    "summary": "Improving vs QQQ",
                                },
                            ],
                            "summary": ["Relative strength improving vs QQQ"],
                            "timeline": [],
                        }
                    },
                )
            )
            stack.enter_context(
                patch(
                    "src.web.routers.today._load_risk_by_ticker",
                    return_value={"NVDA": {"status": "approved", "reason": "within_limits"}},
                )
            )
            stack.enter_context(patch("src.web.routers.today._load_news_by_ticker", return_value={}))
            stack.enter_context(patch("src.web.routers.today._load_fundamentals_by_ticker", return_value={}))
            stack.enter_context(patch("src.web.routers.today._load_option_positions", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_hedge_overlays", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_live_alerts", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_material_changes", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_risk_exposures", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_candidate_rows", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_manual_requests", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_portfolio_intents", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_relationships", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_peer_baskets", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_themes", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_learning_factors", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_performance", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_proposals", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_definitions", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_evaluation_results", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_llm_usage", return_value=()))
            dashboard = load_today_dashboard(
                session,
                selected_tab="trades",
                decision_id=None,
                selected_ticker="NVDA",
            )

        assert dashboard["ticker_workspace"]["detail"]["latest_conclusion"]["trade_decision"]["strategy_id"] == "breakout_v1"
        assert dashboard["ticker_workspace"]["audit_detail"] == selected_nvda_detail
        assert dashboard["trades"]["selected_detail"] == selected_nvda_detail

    def test_load_today_dashboard_backfills_selected_ticker_trade_row_outside_recent_trade_rows(self):
        from src.db.models.trading import TradingDecision
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()
        session.query.side_effect = lambda model: (
            _ListQuery(
                [
                    SimpleNamespace(
                        trading_decision_id=uuid.uuid4(),
                        decision_time=datetime(2026, 6, 3, 23, 25, 34, tzinfo=timezone.utc),
                        created_at=datetime(2026, 6, 3, 23, 25, 34, tzinfo=timezone.utc),
                        ticker="UBER",
                        decision="no_trade",
                        instrument_type="watch",
                        trade_identity="watch_only",
                        strategy_id="valuation_repair_quality_software_v1",
                        expression_bucket_id="long_stock",
                        approved_weight=Decimal("0"),
                        confidence=Decimal("0.35"),
                        thesis="Direct negative catalyst identified; prefer to monitor.",
                        invalidators_json=["valuation repair reverses"],
                        metadata_json={"selection_reason": "direct company-level negative catalyst blocks bullish candidate"},
                        risk_decision=SimpleNamespace(status="approved"),
                    )
                ]
            )
            if model is TradingDecision
            else _QueryStub()
        )

        with ExitStack() as stack:
            stack.enter_context(patch("src.web.routers.today._load_trade_rows", return_value=_ticker_selection_trade_rows()))
            stack.enter_context(patch("src.web.routers.today._load_trade_detail", return_value=None))
            stack.enter_context(patch("src.web.routers.today._load_positions", return_value=()))
            stack.enter_context(
                patch(
                    "src.web.routers.today._load_risk_by_ticker",
                    return_value={"UBER": {"status": "approved", "reason": "within_limits"}},
                )
            )
            stack.enter_context(
                patch(
                    "src.web.routers.today._load_signal_history_by_ticker",
                    return_value={"UBER": {"technical": [], "summary": [], "timeline": []}},
                )
            )
            stack.enter_context(patch("src.web.routers.today._load_news_by_ticker", return_value={}))
            stack.enter_context(patch("src.web.routers.today._load_fundamentals_by_ticker", return_value={}))
            stack.enter_context(patch("src.web.routers.today._load_option_positions", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_hedge_overlays", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_live_alerts", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_material_changes", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_risk_exposures", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_candidate_rows", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_manual_requests", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_portfolio_intents", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_relationships", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_peer_baskets", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_themes", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_learning_factors", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_performance", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_proposals", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_definitions", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_strategy_evaluation_results", return_value=()))
            stack.enter_context(patch("src.web.routers.today._load_llm_usage", return_value=()))
            dashboard = load_today_dashboard(
                session,
                selected_tab="trades",
                decision_id=None,
                selected_ticker="UBER",
            )

        assert dashboard["ticker_workspace"]["selected_ticker"] == "UBER"
        assert (
            dashboard["ticker_workspace"]["detail"]["latest_conclusion"]["trade_decision"]["strategy_id"]
            == "valuation_repair_quality_software_v1"
        )
        assert (
            dashboard["ticker_workspace"]["detail"]["latest_conclusion"]["trade_decision"]["summary"]
            == "Direct negative catalyst identified; prefer to monitor."
        )

    def test_load_signal_history_by_ticker_maps_real_signal_snapshot_schema(self):
        from src.web.routers.today import _load_signal_history_by_ticker

        session = MagicMock()
        session.query.side_effect = [
            _ListQuery(
                [
                    SimpleNamespace(
                        ticker="UBER",
                        decision_time=datetime(2026, 6, 3, 23, 25, 34, tzinfo=timezone.utc),
                        created_at=datetime(2026, 6, 3, 23, 25, 34, tzinfo=timezone.utc),
                        snapshot_type="pre_open",
                        signal_json={
                            "technical": {
                                "return_20d": -0.0173,
                                "price_vs_sma_20": -0.0291,
                                "price_vs_sma_50": -0.0267,
                                "price_vs_sma_200": -0.1403,
                                "relative_volume": 1.0133,
                                "rs_vs_spy_1d": None,
                            },
                            "fundamental": {
                                "quality_score": 0.7777,
                                "margin_trend_score": 0.3331,
                                "revenue_growth_score": 0.8088,
                                "valuation_percentile": 0.1957,
                            },
                            "events_news": {
                                "sentiment_direction": "negative",
                                "direct_negative_catalyst_type": "general_news",
                                "catalyst_quality_score": 0.0,
                            },
                        },
                    )
                ]
            ),
            _ListQuery([]),
        ]

        history = _load_signal_history_by_ticker(session)

        assert [item["label"] for item in history["UBER"]["technical"]] == ["price", "relative_strength"]
        assert "direct negative catalyst" in history["UBER"]["summary"][0].lower()
        assert "below sma20" in history["UBER"]["technical"][0]["summary"].lower()

    def test_load_trade_detail_includes_lookahead_risk_source_and_generated_hedge_action(self):
        from src.web.routers.today import _load_trade_detail

        decision_id = uuid.uuid4()
        row = SimpleNamespace(
            trading_decision_id=decision_id,
            ticker="NVDA",
            decision="trim",
            decision_time=datetime(2026, 6, 3, 23, 25, 34, tzinfo=timezone.utc),
            strategy_id="breakout_v1",
            expression_bucket_id="long_stock",
            trade_identity="tactical_stock_trade",
            confidence=Decimal("0.52"),
            thesis="Reduce before the event window.",
            metadata_json={},
            prompt_run=None,
            candidate_score=None,
            risk_decision=SimpleNamespace(
                status="approved",
                reason_code="own_event_force_reduce",
                generated_hedge_action_json={"reason_code": "macro_high_overlay"},
                metadata_json={"lookahead_risk_source": "own_event"},
            ),
        )
        session = MagicMock()
        session.query.side_effect = [
            _ListQuery([row]),
            _ListQuery([]),
        ]

        detail = _load_trade_detail(session, str(decision_id))

        assert detail["risk_decision"] == {
            "status": "approved",
            "reason_code": "own_event_force_reduce",
            "generated_hedge_action": {"reason_code": "macro_high_overlay"},
            "lookahead_risk_source": "own_event",
            "applied_rules": (),
        }

    def test_load_trade_rows_bulk_loads_order_statuses(self):
        from src.db.models.trading import IntradaySignalSnapshot, PaperOptionOrder, PaperOrder, TradingDecision
        from src.web.routers.today import _load_trade_rows

        stock_decision_id = uuid.uuid4()
        option_decision_id = uuid.uuid4()
        stock_decision = SimpleNamespace(
            trading_decision_id=stock_decision_id,
            decision_time=datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc),
            ticker="AAPL",
            decision="enter_long",
            instrument_type="stock",
            trade_identity="tactical_stock_trade",
            strategy_id="breakout_v1",
            expression_bucket_id="long_stock",
            approved_weight=Decimal("0.03"),
            target_weight=Decimal("0.04"),
            time_horizon="swing",
            max_loss_pct=Decimal("0.02"),
            confidence=Decimal("0.72"),
            risk_decision=SimpleNamespace(status="approved"),
            candidate_score=None,
            thesis="Breakout confirmed.",
            metadata_json={},
        )
        option_decision = SimpleNamespace(
            trading_decision_id=option_decision_id,
            decision_time=datetime(2026, 6, 3, 14, 1, tzinfo=timezone.utc),
            created_at=datetime(2026, 6, 3, 14, 1, tzinfo=timezone.utc),
            ticker="NVDA",
            decision="open_option_strategy",
            instrument_type="option",
            trade_identity="tactical_option_trade",
            strategy_id="earnings_drift_v1",
            expression_bucket_id="long_call",
            approved_weight=Decimal("0.02"),
            target_weight=Decimal("0.03"),
            time_horizon="event",
            max_loss_pct=Decimal("0.01"),
            confidence=Decimal("0.68"),
            risk_decision=SimpleNamespace(status="approved"),
            candidate_score=None,
            thesis="Event drift confirmed.",
            metadata_json={},
        )
        session = MagicMock()
        paper_order_calls = 0

        def query_for(model):
            nonlocal paper_order_calls
            if model is IntradaySignalSnapshot:
                return _ListQuery([])
            if model is TradingDecision:
                return _ListQuery([stock_decision, option_decision])
            if model is PaperOrder:
                paper_order_calls += 1
                if paper_order_calls == 1:
                    return _ListQuery([SimpleNamespace(trading_decision_id=stock_decision_id, status="filled")])
                return _ListQuery([])
            if model is PaperOptionOrder:
                return _ListQuery([SimpleNamespace(trading_decision_id=option_decision_id, status="accepted")])
            return _ListQuery([])

        session.query.side_effect = query_for

        rows = _load_trade_rows(session)

        assert session.query.call_count == 4
        assert [row["order_status"] for row in rows] == ["filled", "accepted"]

    def test_load_candidate_rows_translates_operator_facing_labels(self):
        from src.web.routers.today import _load_candidate_rows

        session = MagicMock()
        session.query.side_effect = [
            _ListQuery(
                [
                    SimpleNamespace(
                        ticker="UBER",
                        selection_source="direct_negative_catalyst",
                        rejection_reason="blocked_by_missing_data",
                        candidate_status="blocked",
                        strategy_id="valuation_repair_quality_software_v1",
                        trade_classifications=[],
                        watch_candidates=[SimpleNamespace(result_status="blocked_by_missing_data")],
                        decision_time=datetime(2026, 6, 3, 23, 25, 34, tzinfo=timezone.utc),
                        candidate_score=Decimal("0.32"),
                    )
                ]
            ),
            _ListQuery([]),
        ]

        rows = _load_candidate_rows(session)

        assert rows == (
            {
                "ticker": "UBER",
                "candidate_score": 0.32,
                "confidence": 0.32,
                "decision_time": "2026-06-03T23:25:34+00:00",
                "selection_source": "direct_negative_catalyst",
                "why_reviewed_label": "Negative catalyst detected",
                "result_status": "blocked_by_missing_data",
                "current_outcome_label": "Blocked: required data unavailable",
                "trade_identity": "watch_only",
                "trade_identity_label": "Watch Only",
                "strategy_match": "valuation_repair_quality_software_v1",
                "strategy_label": "Valuation repair setup",
                "core_signal_evidence": {},
                "selection_reason": None,
                "risk_tags": [],
                "invalidators": [],
                "missing_required_signals": [],
                "operator_summary": "Negative catalyst detected. Blocked: required data unavailable. Watch Only.",
                "detail_internal_ids": {
                    "selection_source": "direct_negative_catalyst",
                    "result_status": "blocked_by_missing_data",
                    "trade_identity": "watch_only",
                    "strategy_match": "valuation_repair_quality_software_v1",
                },
            },
        )

    def test_load_candidate_rows_prefers_latest_trading_decision_over_classifier_status(self):
        from src.web.routers.today import _load_candidate_rows

        session = MagicMock()
        session.query.side_effect = [
            _ListQuery(
                [
                    SimpleNamespace(
                        ticker="APP",
                        selection_source="scanner",
                        rejection_reason=None,
                        candidate_status="selected",
                        strategy_id="gap_continuation_v1",
                        trade_classifications=[SimpleNamespace(result_status="actionable_trade", trade_identity="tactical_stock_trade")],
                        watch_candidates=[],
                        decision_time=datetime(2026, 6, 3, 13, 0, tzinfo=timezone.utc),
                        candidate_score=Decimal("0.72"),
                    )
                ]
            ),
            _ListQuery(
                [
                    SimpleNamespace(
                        ticker="APP",
                        decision="no_trade",
                        paper_trade_authorized=False,
                        decision_time=datetime(2026, 6, 3, 13, 5, tzinfo=timezone.utc),
                    )
                ]
            ),
        ]

        rows = _load_candidate_rows(session)

        assert rows[0]["result_status"] == "no_trade"
        assert rows[0]["current_outcome_label"] == "No clean entry, so no trade"
        assert "Actionable Trade" not in rows[0]["operator_summary"]

    def test_load_candidate_rows_keeps_latest_scanner_run_when_manual_review_is_newer(self):
        from src.web.routers.today import _load_candidate_rows

        manual_time = datetime(2026, 7, 7, 12, 50, tzinfo=timezone.utc)
        scanner_time = datetime(2026, 7, 7, 12, 45, tzinfo=timezone.utc)

        def candidate(
            *,
            ticker: str,
            run_id: str,
            decision_time: datetime,
            selection_source: str,
            score: str = "0.35",
        ) -> SimpleNamespace:
            return SimpleNamespace(
                ticker=ticker,
                strategy_run_id=run_id,
                selection_source=selection_source,
                rejection_reason=None,
                candidate_status="watch",
                strategy_id="catalyst_breakout_v1",
                trade_classifications=[],
                watch_candidates=[],
                decision_time=decision_time,
                candidate_score=Decimal(score),
            )

        manual_rows = tuple(
            candidate(
                ticker="AAPL" if index % 2 == 0 else "NVDA",
                run_id="manual-run",
                decision_time=manual_time,
                selection_source="manual_request",
            )
            for index in range(22)
        )
        scanner_rows = (
            candidate(ticker="CRDO", run_id="scanner-run", decision_time=scanner_time, selection_source="scanner", score="0.98"),
            candidate(ticker="CRDO", run_id="scanner-run", decision_time=scanner_time, selection_source="scanner", score="0.97"),
            candidate(ticker="CRDO", run_id="scanner-run", decision_time=scanner_time, selection_source="scanner", score="0.96"),
            candidate(ticker="MU", run_id="scanner-run", decision_time=scanner_time, selection_source="scanner"),
            candidate(ticker="SNDK", run_id="scanner-run", decision_time=scanner_time, selection_source="scanner"),
        )

        session = MagicMock()
        session.query.side_effect = [
            _LimitedListQuery((*manual_rows, *scanner_rows)),
            _ListQuery([]),
        ]

        rows = _load_candidate_rows(session)

        tickers = {row["ticker"] for row in rows}
        assert {"MU", "SNDK"}.issubset(tickers)

    def test_load_manual_requests_translates_operator_queue_copy(self):
        from src.web.routers.today import _load_manual_requests
        from src.trading.manual_review.sqlalchemy import ManualReviewAuditRow

        request_id = uuid.uuid4()
        session = MagicMock()
        repository = MagicMock()
        repository.load_manual_review_audit_rows.return_value = (
            ManualReviewAuditRow(
                manual_ticker_request_id=str(request_id),
                ticker="TSLA",
                reason="post-event review",
                mode="review_only",
                status="active",
                created_at=datetime(2026, 6, 5, 14, 30, tzinfo=timezone.utc),
                last_evaluated_at=datetime(2026, 6, 5, 15, 0, tzinfo=timezone.utc),
                latest_result_status="ordinary_watch",
                latest_signal_snapshot_id=None,
                latest_trading_decision_id=None,
                latest_decision_action=None,
                latest_risk_outcome=None,
                latest_order_status=None,
                latest_execution_status=None,
                latest_execution_time=None,
                execution_path_state="snapshot_only",
                latest_block_reason=None,
                linkage_state="snapshot_only",
            ),
        )

        with patch("src.web.routers.today.SqlAlchemyTradingRepository", return_value=repository):
            rows = _load_manual_requests(session)

        assert rows == (
            {
                "manual_ticker_request_id": str(request_id),
                "ticker": "TSLA",
                "reason": "post-event review",
                "mode": "review_only",
                "mode_label": "Review Only",
                "status": "active",
                "status_label": "Pinned",
                "latest_result_status": "ordinary_watch",
                "latest_result_label": "Still on watch",
                "last_evaluated_at": "2026-06-05T15:00:00+00:00",
                "latest_signal_snapshot_id": None,
                "latest_trading_decision_id": None,
                "latest_decision_action": None,
                "latest_risk_outcome": None,
                "latest_order_status": None,
                "latest_execution_status": None,
                "latest_execution_time": None,
                "execution_path_state": "snapshot_only",
                "latest_block_reason": None,
                "linkage_state": "snapshot_only",
                "operator_summary": "Review Only because post-event review. Latest result: Still on watch.",
            },
        )

    def test_load_recent_closed_positions_returns_latest_closed_rows_by_ticker(self):
        from src.web.routers.today import _load_recent_closed_positions

        session = MagicMock()
        session.query.return_value = _ListQuery(
            [
                SimpleNamespace(
                    ticker="NVDA",
                    trade_identity="tactical_stock_trade",
                    strategy_id="breakout_v1",
                    quantity=Decimal("0"),
                    market_value=Decimal("0"),
                    opened_at=datetime(2026, 6, 5, 14, 31, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 6, 5, 20, 5, tzinfo=timezone.utc),
                    closed_at=datetime(2026, 6, 5, 20, 5, tzinfo=timezone.utc),
                    status="closed",
                )
            ]
        )

        rows = _load_recent_closed_positions(session)

        assert rows == (
            {
                "ticker": "NVDA",
                "trade_identity": "tactical_stock_trade",
                "trade_identity_label": "Tactical Stock Trade",
                "strategy_id": "breakout_v1",
                "strategy_label": "Breakout V1",
                "quantity": Decimal("0"),
                "market_value": Decimal("0"),
                "opened_at": datetime(2026, 6, 5, 14, 31, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 6, 5, 20, 5, tzinfo=timezone.utc),
                "closed_at": datetime(2026, 6, 5, 20, 5, tzinfo=timezone.utc),
                "status": "closed",
            },
        )

    def test_load_today_dashboard_builds_command_center_overview(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()
        trade_rows = _ticker_selection_trade_rows()
        selected_nvda_detail = _selected_trade_detail("NVDA")

        with (
            patch("src.web.routers.today._load_trade_rows", return_value=trade_rows),
            patch(
                "src.web.routers.today._load_positions",
                return_value=(
                    {
                        "ticker": "AAPL",
                        "trade_identity": "tactical_stock_trade",
                        "strategy_id": "breakout_v1",
                        "quantity": Decimal("10"),
                        "market_value": Decimal("2145.20"),
                        "summary": "Open position, risk within limits",
                    },
                ),
            ),
            patch(
                "src.web.routers.today._load_recent_closed_positions",
                return_value=(
                    {
                        "ticker": "NVDA",
                        "status": "closed",
                        "closed_at": datetime(2026, 6, 5, 20, 5, tzinfo=timezone.utc),
                        "summary": "Closed recently and ready for review",
                    },
                    {
                        "ticker": "NVDA",
                        "status": "closed",
                        "closed_at": datetime(2026, 6, 4, 20, 5, tzinfo=timezone.utc),
                        "summary": "Older duplicate close should be suppressed",
                    },
                ),
            ),
            patch("src.web.routers.today._load_trade_detail", return_value=selected_nvda_detail),
            patch(
                "src.web.routers.today._load_option_positions",
                return_value=(
                    {
                        "ticker": "QQQ",
                        "option_strategy_type": "long_call",
                        "trade_identity": "tactical_option_trade",
                        "max_loss": Decimal("230.00"),
                    },
                    {
                        "ticker": "NVDA",
                        "option_strategy_type": "long_call",
                        "trade_identity": "tactical_option_trade",
                        "max_loss": Decimal("220.00"),
                    },
                ),
            ),
            patch("src.web.routers.today._load_hedge_overlays", return_value=()),
            patch("src.web.routers.today._load_live_alerts", return_value=()),
            patch("src.web.routers.today._load_material_changes", return_value=()),
            patch("src.web.routers.today._load_risk_exposures", return_value=()),
            patch("src.web.routers.today._load_candidate_rows", return_value=()),
            patch("src.web.routers.today._load_manual_requests", return_value=()),
            patch("src.web.routers.today._load_portfolio_intents", return_value=()),
            patch("src.web.routers.today._load_relationships", return_value=()),
            patch("src.web.routers.today._load_peer_baskets", return_value=()),
            patch("src.web.routers.today._load_themes", return_value=()),
            patch("src.web.routers.today._load_learning_factors", return_value=()),
            patch("src.web.routers.today._load_strategy_performance", return_value=()),
            patch("src.web.routers.today._load_strategy_proposals", return_value=()),
            patch("src.web.routers.today._load_llm_usage", return_value=()),
        ):
            dashboard = load_today_dashboard(
                session,
                selected_tab="portfolio",
                decision_id=None,
                selected_ticker="NVDA",
            )

        assert dashboard["overview"]["command_center"] == {
            "needs_review": (
                {"ticker": "NVDA", "summary": "Closed recently and ready for review"},
            ),
            "open_positions": (
                {"ticker": "AAPL", "summary": "Open position, risk within limits"},
                {"ticker": "QQQ", "summary": "Open option position, max loss $230.00"},
                {"ticker": "NVDA", "summary": "Open option position, max loss $220.00"},
            ),
            "system_issues": (
                {"label": "Macro regime unavailable", "summary": "Global macro regime data is unavailable."},
            ),
        }

    def test_load_today_dashboard_keeps_overview_tab_reachable(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()
        trade_rows = _ticker_selection_trade_rows()
        selected_nvda_detail = _selected_trade_detail("NVDA")

        with (
            patch("src.web.routers.today._load_trade_rows", return_value=trade_rows),
            patch("src.web.routers.today._load_positions", return_value=()),
            patch("src.web.routers.today._load_recent_closed_positions", return_value=()),
            patch("src.web.routers.today._load_trade_detail", return_value=selected_nvda_detail),
            patch("src.web.routers.today._load_option_positions", return_value=()),
            patch("src.web.routers.today._load_hedge_overlays", return_value=()),
            patch("src.web.routers.today._load_live_alerts", return_value=()),
            patch("src.web.routers.today._load_material_changes", return_value=()),
            patch("src.web.routers.today._load_risk_exposures", return_value=()),
            patch("src.web.routers.today._load_candidate_rows", return_value=()),
            patch("src.web.routers.today._load_manual_requests", return_value=()),
            patch("src.web.routers.today._load_portfolio_intents", return_value=()),
            patch("src.web.routers.today._load_relationships", return_value=()),
            patch("src.web.routers.today._load_peer_baskets", return_value=()),
            patch("src.web.routers.today._load_themes", return_value=()),
            patch("src.web.routers.today._load_learning_factors", return_value=()),
            patch("src.web.routers.today._load_strategy_performance", return_value=()),
            patch("src.web.routers.today._load_strategy_proposals", return_value=()),
            patch("src.web.routers.today._load_llm_usage", return_value=()),
        ):
            dashboard = load_today_dashboard(
                session,
                selected_tab="overview",
                decision_id=None,
                selected_ticker="NVDA",
            )

        assert dashboard["selected_tab"] == "overview"
        assert any(tab["id"] == "overview" for tab in dashboard["tabs"])

    def test_load_today_dashboard_builds_risk_macro_summary(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()
        trade_rows = _ticker_selection_trade_rows()
        selected_nvda_detail = _selected_trade_detail("NVDA")

        with (
            patch("src.web.routers.today._load_trade_rows", return_value=trade_rows),
            patch("src.web.routers.today._load_positions", return_value=()),
            patch("src.web.routers.today._load_recent_closed_positions", return_value=()),
            patch("src.web.routers.today._load_trade_detail", return_value=selected_nvda_detail),
            patch("src.web.routers.today._load_option_positions", return_value=()),
            patch("src.web.routers.today._load_hedge_overlays", return_value=()),
            patch("src.web.routers.today._load_live_alerts", return_value=()),
            patch("src.web.routers.today._load_material_changes", return_value=()),
            patch(
                "src.web.routers.today._load_risk_exposures",
                return_value=(
                    {"factor_type": "sector", "factor_name": "Technology", "exposure": Decimal("5.2757")},
                ),
            ),
            patch("src.web.routers.today._load_candidate_rows", return_value=()),
            patch("src.web.routers.today._load_manual_requests", return_value=()),
            patch("src.web.routers.today._load_portfolio_intents", return_value=()),
            patch("src.web.routers.today._load_relationships", return_value=()),
            patch("src.web.routers.today._load_peer_baskets", return_value=()),
            patch("src.web.routers.today._load_themes", return_value=()),
            patch("src.web.routers.today._load_learning_factors", return_value=()),
            patch("src.web.routers.today._load_strategy_performance", return_value=()),
            patch("src.web.routers.today._load_strategy_proposals", return_value=()),
            patch("src.web.routers.today._load_llm_usage", return_value=()),
            patch("src.web.routers.today._load_latest_macro_snapshot_for_today", return_value=None),
        ):
            dashboard = load_today_dashboard(
                session,
                selected_tab="risk-macro",
                decision_id=None,
                selected_ticker="NVDA",
            )

        assert dashboard["risk_macro"]["summary"] == {
            "risk_status": "Within Limits",
            "top_risk_sources": (
                {"label": "Technology concentration", "summary": "theme cap near limit"},
            ),
            "availability_issues": (
                {"label": "Macro regime unavailable", "summary": "Global macro regime data is unavailable."},
            ),
        }

    def test_load_today_dashboard_prefers_latest_macro_snapshot_for_header_regime(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()

        with (
            patch("src.web.routers.today._load_trade_rows", return_value=[]),
            patch("src.web.routers.today._load_positions", return_value=()),
            patch("src.web.routers.today._load_recent_closed_positions", return_value=()),
            patch("src.web.routers.today._load_option_positions", return_value=()),
            patch("src.web.routers.today._load_hedge_overlays", return_value=()),
            patch("src.web.routers.today._load_live_alerts", return_value=()),
            patch("src.web.routers.today._load_material_changes", return_value=()),
            patch("src.web.routers.today._load_risk_exposures", return_value=()),
            patch("src.web.routers.today._load_candidate_rows", return_value=()),
            patch("src.web.routers.today._load_manual_requests", return_value=()),
            patch("src.web.routers.today._load_portfolio_intents", return_value=()),
            patch("src.web.routers.today._load_relationships", return_value=()),
            patch("src.web.routers.today._load_peer_baskets", return_value=()),
            patch("src.web.routers.today._load_themes", return_value=()),
            patch("src.web.routers.today._load_learning_factors", return_value=()),
            patch("src.web.routers.today._load_strategy_performance", return_value=()),
            patch("src.web.routers.today._load_strategy_proposals", return_value=()),
            patch("src.web.routers.today._load_llm_usage", return_value=()),
            patch(
                "src.web.routers.today._load_latest_macro_snapshot_for_today",
                return_value=SimpleNamespace(regime="risk_off"),
            ),
        ):
            dashboard = load_today_dashboard(
                session,
                selected_tab="portfolio",
                decision_id=None,
                selected_ticker=None,
            )

        assert dashboard["header"]["macro_regime"] == "risk_off"
        assert dashboard["header"]["macro_regime_label"] == "Risk Off"

    def test_load_today_dashboard_lazy_loads_only_selected_portfolio_tab(self):
        from src.web.routers.today import load_today_dashboard

        session = _query_stub_session()

        with (
            patch("src.web.routers.today._load_trade_rows", return_value=[]) as load_trade_rows,
            patch("src.web.routers.today._load_positions", return_value=()),
            patch("src.web.routers.today._load_recent_closed_positions", return_value=()),
            patch("src.web.routers.today._load_option_positions", return_value=()),
            patch("src.web.routers.today._load_portfolio_history", return_value=()),
            patch("src.web.routers.today._load_hedge_overlays", return_value=()),
            patch("src.web.routers.today._load_live_alerts", return_value=()),
            patch("src.web.routers.today._load_material_changes", return_value=()),
            patch("src.web.routers.today._load_today_risk_macro", return_value={}),
            patch("src.web.routers.today._load_candidate_rows", return_value=()) as load_candidate_rows,
            patch("src.web.routers.today._load_manual_requests", return_value=()) as load_manual_requests,
            patch("src.web.routers.today._load_signal_history_by_ticker", return_value={}) as load_signal_history,
            patch("src.web.routers.today._load_news_by_ticker", return_value={}) as load_news,
            patch("src.web.routers.today._load_fundamentals_by_ticker", return_value={}) as load_fundamentals,
            patch("src.web.routers.today._load_learning_factors", return_value=()) as load_learning_factors,
            patch("src.web.routers.today._load_strategy_proposals", return_value=()) as load_strategy_proposals,
            patch("src.web.routers.today._load_strategy_definitions", return_value=()) as load_strategy_definitions,
            patch("src.web.routers.today._load_strategy_evaluation_results", return_value=()) as load_strategy_evaluations,
            patch("src.web.routers.today._load_llm_usage", return_value=()) as load_llm_usage,
        ):
            dashboard = load_today_dashboard(
                session,
                selected_tab="portfolio",
                decision_id=None,
                selected_ticker=None,
            )

        assert dashboard["selected_tab"] == "portfolio"
        assert "portfolio" in dashboard
        load_trade_rows.assert_not_called()
        load_candidate_rows.assert_not_called()
        load_manual_requests.assert_not_called()
        load_signal_history.assert_not_called()
        load_news.assert_not_called()
        load_fundamentals.assert_not_called()
        load_learning_factors.assert_not_called()
        load_strategy_proposals.assert_not_called()
        load_strategy_definitions.assert_not_called()
        load_strategy_evaluations.assert_not_called()
        load_llm_usage.assert_not_called()

    def test_load_news_and_fundamentals_by_ticker_map_real_snapshot_and_event_rows(self):
        from src.web.routers.today import _load_fundamentals_by_ticker, _load_news_by_ticker

        signal_session = MagicMock()
        signal_session.query.side_effect = [
            _ListQuery(
                [
                    SimpleNamespace(
                        ticker="UBER",
                        decision_time=datetime(2026, 6, 3, 23, 25, 34, tzinfo=timezone.utc),
                        created_at=datetime(2026, 6, 3, 23, 25, 34, tzinfo=timezone.utc),
                        signal_json={
                            "fundamental": {
                                "quality_score": 0.7777,
                                "margin_trend_score": 0.3331,
                                "revenue_growth_score": 0.8088,
                                "valuation_percentile": 0.1957,
                            }
                        },
                    )
                ]
            )
        ]
        news_session = MagicMock()
        news_session.query.side_effect = [
            _ListQuery([]),
            _ListQuery(
                [
                    SimpleNamespace(
                        ticker="UBER",
                        source_ticker="MU",
                        explicit_ticker_mention_flag=False,
                        headline="Uber layoffs: HR and workplace division cut 23%",
                        summary="The cuts affect recruitment and HR staff.",
                        published_at=datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc),
                    )
                ]
            ),
        ]

        fundamentals = _load_fundamentals_by_ticker(signal_session)
        news = _load_news_by_ticker(news_session)

        assert [item["title"] for item in fundamentals["UBER"]] == [
            "Quality",
            "Margin Trend",
            "Revenue Growth",
            "Valuation Percentile",
        ]
        assert news["UBER"][0]["title"] == "Uber layoffs: HR and workplace division cut 23%"
        assert news["UBER"][0]["source_ticker"] == "MU"
        assert news["UBER"][0]["readthrough_label"] == "Readthrough from MU"
        assert news["UBER"][0]["explicit_ticker_mention"] is False

    def test_load_live_alerts_preserves_readthrough_metadata(self):
        from src.web.routers.today import _load_live_alerts

        session = MagicMock()
        session.query.return_value = _ListQuery(
            [
                SimpleNamespace(
                    ticker="NVDA",
                    severity="high",
                    headline="Micron raises guidance",
                    summary="Memory demand improved.",
                    source_ticker="MU",
                    readthrough_source_ticker="MU",
                )
            ]
        )

        alerts = _load_live_alerts(session)

        assert alerts == (
            {
                "ticker": "NVDA",
                "severity": "high",
                "headline": "Micron raises guidance",
                "summary": "Memory demand improved.",
                "source_ticker": "MU",
                "readthrough_source_ticker": "MU",
            },
        )


class TestTodayDashboardMutations:
    def test_add_manual_request_redirects_back_to_candidates(self, client):
        created_id = uuid.uuid4()
        with patch("src.web.routers.today.create_manual_request", return_value=created_id) as create_manual_request:
            response = client.post(
                "/today/manual-requests",
                data={
                    "ticker": "tsla",
                    "reason": "post-event review",
                    "mode": "review_only",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/today?tab=candidates"
        create_manual_request.assert_called_once()

    def test_create_manual_request_uses_sqlalchemy_service(self):
        from src.web.routers.today import create_manual_request

        created_id = uuid.uuid4()
        session = MagicMock()
        service = MagicMock()
        service.create.return_value = SimpleNamespace(request_id=str(created_id))

        with patch("src.web.routers.today.SQLAlchemyManualTickerRequestService", return_value=service):
            request_id = create_manual_request(
                session,
                ticker="tsla",
                reason="post-event review",
                mode="review_only",
            )

        assert request_id == created_id
        service.create.assert_called_once_with("tsla", "post-event review", "review_only")

    def test_dismiss_manual_request_redirects_back_to_candidates(self, client):
        request_id = uuid.uuid4()
        with patch("src.web.routers.today.dismiss_manual_request") as dismiss_manual_request:
            response = client.post(
                f"/today/manual-requests/{request_id}/dismiss",
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/today?tab=candidates"
        dismiss_manual_request.assert_called_once()

    def test_dismiss_manual_request_uses_sqlalchemy_service(self):
        from src.web.routers.today import dismiss_manual_request

        request_id = uuid.uuid4()
        session = MagicMock()
        service = MagicMock()

        with patch("src.web.routers.today.SQLAlchemyManualTickerRequestService", return_value=service):
            dismiss_manual_request(session, str(request_id))

        service.dismiss.assert_called_once_with(str(request_id))

    def test_update_universe_filter_redirects_back_to_candidates(self, client):
        with patch("src.web.routers.today.update_universe_filter") as update_universe_filter:
            response = client.post(
                "/today/universe-filter",
                data={
                    "profile_name": "default",
                    "min_price": "15",
                    "min_avg_dollar_volume": "7500000",
                    "included_sectors": "Technology,Healthcare",
                    "excluded_sectors": "Utilities",
                    "included_industries": "",
                    "excluded_industries": "",
                    "exchanges": "NASDAQ,NYSE",
                    "asset_types": "us_equity",
                    "manual_include": "AAPL,NVDA",
                    "manual_exclude": "GME",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/today?tab=candidates"
        update_universe_filter.assert_called_once()


class _QueryStub:
    def filter(self, *_args, **_kwargs):
        return self

    def filter_by(self, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def options(self, *_args, **_kwargs):
        return self

    def first(self):
        return None

    def all(self):
        return []


class _ListQuery(_QueryStub):
    def __init__(self, rows):
        self._rows = list(rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _LimitedListQuery(_ListQuery):
    def __init__(self, rows):
        super().__init__(rows)
        self._limit = None

    def limit(self, value):
        self._limit = int(value)
        return self

    def all(self):
        rows = super().all()
        if self._limit is None:
            return rows
        return rows[: self._limit]


def _query_stub_session() -> MagicMock:
    session = MagicMock()
    session.query.return_value = _QueryStub()
    return session


def _ticker_selection_trade_rows() -> list[dict]:
    return [
        {
            "trading_decision_id": "decision-watch",
            "decision_time": datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc),
            "created_at": datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc),
            "ticker": "AAPL",
            "decision": "no_trade",
            "instrument_type": "watch",
            "trade_identity": "watch_only",
            "selected_strategy_id": "watch_strategy_v1",
            "expression_bucket_id": "watch",
            "approved_weight": Decimal("0"),
            "confidence": Decimal("0.25"),
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
        },
        {
            "trading_decision_id": "decision-action",
            "decision_time": datetime(2026, 6, 2, 13, 0, tzinfo=timezone.utc),
            "created_at": datetime(2026, 6, 2, 13, 0, tzinfo=timezone.utc),
            "ticker": "NVDA",
            "decision": "enter_long",
            "instrument_type": "stock",
            "trade_identity": "tactical_stock_trade",
            "selected_strategy_id": "breakout_v1",
            "expression_bucket_id": "long_stock",
            "approved_weight": Decimal("0.05"),
            "confidence": Decimal("0.81"),
            "risk_status": "approved",
            "order_status": "accepted",
            "material_signal_change": True,
        },
    ]


def _selected_trade_detail(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "signal_snapshot": {},
        "llm_decision_json": {},
        "strategy_scores": (),
        "risk_decision": None,
        "outcomes": (),
    }


def _patched_today_route_dependencies(session: MagicMock, *, trade_rows: list[dict], selected_detail: dict | None):
    stack = ExitStack()
    stack.enter_context(
        patch("src.web.routers.today.get_session", return_value=_session_context(session))
    )
    stack.enter_context(patch("src.web.routers.today._load_trade_rows", return_value=trade_rows))
    load_trade_detail = stack.enter_context(
        patch("src.web.routers.today._load_trade_detail", return_value=selected_detail)
    )
    stack.enter_context(patch("src.web.routers.today._load_positions", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_option_positions", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_hedge_overlays", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_live_alerts", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_material_changes", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_risk_exposures", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_candidate_rows", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_manual_requests", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_portfolio_intents", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_relationships", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_peer_baskets", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_themes", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_learning_factors", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_strategy_performance", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_strategy_proposals", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_strategy_definitions", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_strategy_evaluation_results", return_value=()))
    stack.enter_context(patch("src.web.routers.today._load_llm_usage", return_value=()))
    return _exit_stack_with_result(stack, load_trade_detail)


def test_load_today_dashboard_includes_learning_observability():
    from src.web.routers.today import load_today_dashboard

    session = _query_stub_session()

    with (
        patch("src.web.routers.today._load_trade_rows", return_value=[]),
        patch("src.web.routers.today._load_positions", return_value=()),
        patch("src.web.routers.today._load_option_positions", return_value=()),
        patch("src.web.routers.today._load_hedge_overlays", return_value=()),
        patch("src.web.routers.today._load_live_alerts", return_value=()),
        patch("src.web.routers.today._load_material_changes", return_value=()),
        patch("src.web.routers.today._load_risk_exposures", return_value=()),
        patch("src.web.routers.today._load_candidate_rows", return_value=()),
        patch("src.web.routers.today._load_manual_requests", return_value=()),
        patch("src.web.routers.today._load_portfolio_intents", return_value=()),
        patch("src.web.routers.today._load_relationships", return_value=()),
        patch("src.web.routers.today._load_peer_baskets", return_value=()),
        patch("src.web.routers.today._load_themes", return_value=()),
        patch(
            "src.web.routers.today._load_learning_factors",
            return_value=(
                {
                    "factor_key": "lf-risk",
                    "title": "Reduce risk after failed breakouts",
                    "status": "active",
                    "status_label": "Active",
                    "scope": "risk",
                    "scope_label": "Risk",
                    "effect_tags": ("reduce_exposure",),
                },
            ),
        ),
        patch("src.web.routers.today._load_strategy_performance", return_value=()),
        patch("src.web.routers.today._load_strategy_proposals", return_value=({"proposed_strategy_id": "new_v1"},)),
        patch("src.web.routers.today._load_strategy_definitions", return_value=({"strategy_id": "new_v1"},)),
        patch(
            "src.web.routers.today._load_strategy_evaluation_results",
            return_value=({"evaluation_status": "promoted", "new_lifecycle_status": "shadow"},),
        ),
        patch("src.web.routers.today._load_llm_usage", return_value=()),
        patch("src.web.routers.today._load_trade_detail", return_value=None),
    ):
        dashboard = load_today_dashboard(
            session,
            selected_tab="system",
            decision_id=None,
            selected_ticker=None,
        )

    assert dashboard["learning_strategies"]["observability"]["funnel"][0]["count"] == 1
    assert dashboard["learning_strategies"]["observability"]["funnel"][4]["count"] == 1
    assert dashboard["learning_strategies"]["observability"]["weight_inputs"][0]["factor_key"] == "lf-risk"


def test_build_system_view_aggregates_llm_usage_by_day_and_month():
    from datetime import datetime, timezone

    from src.web.routers.today import _build_system_view

    system = _build_system_view(
        overview={"command_center": {"system_issues": ()}},
        learning_strategies={},
        ops_cost={
            "llm_usage": (
                {
                    "created_at": datetime(2026, 7, 4, 21, 0, tzinfo=timezone.utc),
                    "pipeline_name": "intraday_rebalance",
                    "provider": "gemini",
                    "model": "gemini-2.5-flash-lite",
                    "estimated_cost": Decimal("0.01"),
                    "total_tokens": 100,
                    "latency_ms": 500,
                    "status": "succeeded",
                },
                {
                    "created_at": datetime(2026, 7, 4, 22, 0, tzinfo=timezone.utc),
                    "pipeline_name": "intraday_rebalance",
                    "provider": "gemini",
                    "model": "gemini-2.5-flash-lite",
                    "estimated_cost": Decimal("0.02"),
                    "total_tokens": 200,
                    "latency_ms": 700,
                    "status": "succeeded",
                },
                {
                    "created_at": datetime(2026, 7, 5, 1, 0, tzinfo=timezone.utc),
                    "pipeline_name": "reflection",
                    "provider": "gemini",
                    "model": "gemini-2.5-pro",
                    "estimated_cost": Decimal("0.30"),
                    "total_tokens": 900,
                    "latency_ms": 1200,
                    "status": "succeeded",
                },
            ),
            "provider_usage": (),
        },
        risk_macro={"events": (), "exposures": ()},
    )

    daily = system["llm_usage_daily"]
    monthly = system["llm_usage_monthly"]
    assert daily[0]["period_label"] == "2026-07-05"
    assert daily[0]["pipeline_name"] == "reflection"
    assert daily[0]["event_count"] == 1
    assert daily[1]["period_label"] == "2026-07-04"
    assert daily[1]["event_count"] == 2
    assert daily[1]["total_tokens"] == 300
    assert daily[1]["estimated_cost"] == Decimal("0.03")
    assert daily[1]["avg_latency_ms"] == 600
    assert monthly == (
        {
            "period_label": "2026-07",
            "pipeline_name": "intraday_rebalance",
            "provider": "gemini",
            "model": "gemini-2.5-flash-lite",
            "event_count": 2,
            "total_tokens": 300,
            "estimated_cost": Decimal("0.03"),
            "avg_latency_ms": 600,
            "status_label": "Succeeded",
        },
        {
            "period_label": "2026-07",
            "pipeline_name": "reflection",
            "provider": "gemini",
            "model": "gemini-2.5-pro",
            "event_count": 1,
            "total_tokens": 900,
            "estimated_cost": Decimal("0.30"),
            "avg_latency_ms": 1200,
            "status_label": "Succeeded",
        },
    )


def test_load_strategy_proposals_exposes_user_readable_llm_output():
    from src.web.routers.today import _load_strategy_proposals

    row = SimpleNamespace(
        proposed_strategy_id="post_gap_vwap_reclaim_v1",
        display_name="Post-gap VWAP reclaim",
        proposal_status="accepted",
        proposed_lifecycle_status="shadow",
        duplicate_of_strategy_id=None,
        rejection_reason=None,
        evidence_summary="Repeated reclaim setups outperformed after early gap failures.",
        proposal_json={
            "core_thesis": "Wait for a failed gap-down to reclaim VWAP before entering.",
            "required_signals": ["opening_gap_pct", "vwap_reclaim"],
            "optional_signals": ["news_sentiment"],
            "risk_tags": ["gap_failure"],
            "invalidators": ["Fails to hold VWAP"],
        },
    )
    session = MagicMock()
    session.query.return_value.order_by.return_value.limit.return_value.all.return_value = [row]

    proposals = _load_strategy_proposals(session)

    assert proposals[0]["display_name"] == "Post-gap VWAP reclaim"
    assert proposals[0]["core_thesis"] == "Wait for a failed gap-down to reclaim VWAP before entering."
    assert proposals[0]["required_signals"] == ("opening_gap_pct", "vwap_reclaim")
    assert proposals[0]["optional_signals"] == ("news_sentiment",)
    assert proposals[0]["risk_tags"] == ("gap_failure",)
    assert proposals[0]["invalidators"] == ("Fails to hold VWAP",)
    assert proposals[0]["evidence_summary"] == "Repeated reclaim setups outperformed after early gap failures."
    assert proposals[0]["proposed_lifecycle_status_label"] == "Shadow"


def test_load_strategy_performance_computes_win_rate_percentage():
    from src.web.routers.today import _load_strategy_performance

    session = MagicMock()
    session.query.return_value.order_by.return_value.all.return_value = [
        SimpleNamespace(strategy_id="earnings_drift_v1", alpha=Decimal("1.2")),
        SimpleNamespace(strategy_id="earnings_drift_v1", alpha=Decimal("-0.3")),
        SimpleNamespace(strategy_id="earnings_drift_v1", alpha=None),
        SimpleNamespace(strategy_id="gap_reclaim_v1", alpha=Decimal("0.5")),
        SimpleNamespace(strategy_id="gap_reclaim_v1", alpha=Decimal("0.7")),
    ]

    performance = _load_strategy_performance(session)

    assert performance == (
        {
            "strategy_id": "earnings_drift_v1",
            "lifecycle_status": "observed",
            "lifecycle_status_label": "Observed",
            "win_rate": Decimal("50.0"),
            "total_pnl": Decimal("0.9"),
        },
        {
            "strategy_id": "gap_reclaim_v1",
            "lifecycle_status": "observed",
            "lifecycle_status_label": "Observed",
            "win_rate": Decimal("100.0"),
            "total_pnl": Decimal("1.2"),
        },
    )


def test_today_styles_define_attention_feed_row_variants():
    stylesheet = Path("src/static/style.css").read_text()

    assert ".attention-feed-row-review" in stylesheet
    assert ".attention-feed-row-alert" in stylesheet
    assert ".attention-feed-row-signal" in stylesheet


def test_today_kpi_values_scale_to_fit_card_width():
    stylesheet = Path("src/static/style.css").read_text()

    assert ".kpi-card .value" in stylesheet
    assert "container-type: inline-size" in stylesheet
    assert "@container (max-width: 230px)" in stylesheet
    assert "overflow-wrap: anywhere" in stylesheet


def test_history_highlights_table_has_inset_container_spacing():
    stylesheet = Path("src/static/style.css").read_text()

    assert ".history-hl { border: 1px solid var(--accent);" in stylesheet
    assert ".history-hl .history-table" in stylesheet
    assert ".history-hl .history-table th:first-child" in stylesheet


def test_build_attention_feed_merges_by_ticker():
    from src.web.presenters.today_overview import _build_attention_feed

    feed = _build_attention_feed(
        needs_review=({"ticker": "NVDA", "summary": "Closed; ready for review"},),
        live_alerts=({"ticker": "nvda", "severity": "high", "headline": "Raised guidance"},),
        material_changes=({"ticker": "AAPL", "summary": "RS improved"},),
    )

    # NVDA collapses to ONE entry carrying both an alert and a review facet.
    assert len(feed) == 2
    by_ticker = {entry["ticker"]: entry for entry in feed}
    nvda = by_ticker["NVDA"]
    assert nvda["primary_kind"] == "alert"  # alert outranks review
    assert tuple(f["kind"] for f in nvda["facets"]) == ("alert", "review")
    assert by_ticker["AAPL"]["primary_kind"] == "signal"
    # alert-primary ticker sorts ahead of signal-primary ticker
    assert feed[0]["ticker"] == "NVDA"


def test_build_attention_feed_excludes_readthrough_news_alerts():
    from src.web.presenters.today_overview import _build_attention_feed

    feed = _build_attention_feed(
        needs_review=(),
        live_alerts=(
            {
                "ticker": "NVDA",
                "severity": "high",
                "headline": "Micron raises guidance",
                "source_ticker": "MU",
                "readthrough_source_ticker": "MU",
            },
            {"ticker": "AAPL", "severity": "medium", "headline": "AAPL raises guidance"},
        ),
        material_changes=(),
    )

    assert [entry["ticker"] for entry in feed] == ["AAPL"]


@contextmanager
def _session_context(session: MagicMock):
    yield session


@contextmanager
def _exit_stack_with_result(stack: ExitStack, result):
    with stack:
        yield result
