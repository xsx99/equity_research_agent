"""Today dashboard route tests."""
from __future__ import annotations

import uuid
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
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
        "selected_tab": "overview",
        "tabs": (
            {"id": "overview", "label": "Overview"},
            {"id": "portfolio", "label": "Portfolio"},
            {"id": "trades", "label": "Trades"},
            {"id": "risk-macro", "label": "Risk & Macro"},
            {"id": "candidates", "label": "Candidates"},
            {"id": "learning-strategies", "label": "Learning & Strategies"},
            {"id": "ops-cost", "label": "Ops & Cost"},
        ),
        "header": {
            "trade_date": date(2026, 6, 2),
            "macro_regime": "neutral",
            "risk_appetite": "balanced",
            "nav": Decimal("1000000"),
            "day_pnl": Decimal("1250.50"),
            "buying_power": Decimal("2000000"),
            "gross_exposure": Decimal("0.42"),
            "open_alert_count": 2,
            "material_signal_change_count": 3,
            "llm_cost_estimate": Decimal("18.42"),
        },
        "job_timeline": (
            {"label": "Universe refresh", "status": "succeeded"},
            {"label": "Reflection", "status": "succeeded"},
        ),
        "overview": {
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
        },
        "portfolio": {
            "positions": (
                {
                    "ticker": "AAPL",
                    "trade_identity": "tactical_stock_trade",
                    "strategy_id": "earnings_drift_v1",
                    "quantity": Decimal("10"),
                    "market_value": Decimal("2145.20"),
                },
            ),
            "option_positions": (
                {
                    "ticker": "NVDA",
                    "option_strategy_type": "long_call",
                    "trade_identity": "tactical_option_trade",
                    "max_loss": Decimal("420.00"),
                },
            ),
            "hedge_overlays": (
                {
                    "ticker": "SPY",
                    "option_strategy_type": "long_put",
                    "protected_notional": Decimal("25000"),
                },
            ),
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
                "trade_decision": {"label": "Watch", "summary": "Waiting for confirmation"},
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
                        "latest_decision": "Hold",
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
                        "summary": "Changed from watch to enter_long",
                    },
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
                            {"title": "Raised guidance", "summary": "Demand improved across core products"},
                        ),
                        "fundamental_snippets": (
                            {"title": "Margin outlook", "summary": "Gross margin remains stable"},
                        ),
                    },
                    "risk_summary": {"status": "approved", "status_label": "Approved", "reason": "within_limits"},
                    "position_execution": {
                        "position_label": "Long 10 shares",
                        "order_status": "filled",
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
                            "trade_decision": {"label": "Watch", "summary": "Waiting for confirmation"},
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
                                "summary": "The system promoted AAPL from watch to enter_long after risk approval.",
                            },
                            "risk": {"status_label": "Approved", "summary": "within_limits"},
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
                        "current_stance": {"status": "approved", "reason": "within_limits"},
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
                "regime": "risk_off",
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
                    "scheduled_at": datetime(2026, 6, 3, 18, 0, tzinfo=timezone.utc),
                    "event_type": "own_company_earnings",
                    "importance": "high",
                    "portfolio_risk_level": "high",
                    "affected_ticker": "AAPL",
                    "risk_mechanism": "direct earnings gap risk",
                },
            ),
            "risk_sources": (
                {
                    "ticker": "AAPL",
                    "risk_source": "own_event",
                    "severity": "high",
                    "recommended_action": "block_open",
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
                {"ticker": "VOO", "intent_type": "core_index", "lifecycle_status": "active"},
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
        },
        "learning_strategies": {
            "reflection": {
                "status": "succeeded",
                "what_worked": ("Bullish catalyst continuation respected",),
            },
            "learning_factors": (
                {
                    "title": "Tighten low-volume gap entries",
                    "status": "active",
                    "scope": "strategy",
                },
            ),
            "strategy_performance": (
                {
                    "strategy_id": "earnings_drift_v1",
                    "lifecycle_status": "active",
                    "win_rate": Decimal("0.58"),
                    "total_pnl": Decimal("4200"),
                },
            ),
            "strategy_proposals": (
                {
                    "proposed_strategy_id": "semis_readthrough_v1",
                    "proposal_status": "accepted",
                },
            ),
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
                    "cache_status": "miss",
                },
            ),
        },
    }


class TestTodayDashboard:
    def test_root_redirects_to_today(self, client):
        response = client.get("/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/today"

    def test_get_today_dashboard_renders_tabs_and_sections(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "overview"
        payload["overview"]["operator_strip"] = {
            "primary": (
                {"label": "Market Phase", "value": "Pre-open", "tone": "neutral"},
                {"label": "Runtime Mode", "value": "Live Manual Review", "tone": "neutral"},
            ),
            "context": (
                {"label": "Macro Regime", "value": "Risk Off", "tone": "warning"},
                {"label": "Live Status", "value": "Degraded", "tone": "warning"},
            ),
        }
        payload["overview"]["metric_cards"] = (
            {
                "label": "Net Liquidation Value",
                "primary_value": "$1,000,000.00",
                "secondary_value": None,
                "meta": {
                    "updated_at_label": "2026-06-16 13:31 UTC",
                    "source_of_truth_label": "Broker equity snapshot",
                    "basis_note": None,
                },
            },
        )
        payload["overview"]["current_summary"] = {
            "headline": "Macro is defensive and operator attention is concentrated in a small queue.",
            "items": ("3 open alerts", "2 material signal changes", "1 manual review request awaiting linkage"),
            "hidden_item_count": 1,
            "meta": {
                "updated_at_label": "2026-06-16 13:31 UTC",
            },
        }
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=overview")

        assert response.status_code == 200
        assert "Today Dashboard" in response.text
        assert "today-shell" in response.text
        assert "operator-strip" in response.text
        assert "operator-strip-group-primary" in response.text
        assert "operator-strip-group-context" in response.text
        assert "today-global-tabs" in response.text
        assert "today-workspace" in response.text
        assert "Overview" in response.text
        assert "Portfolio" in response.text
        assert "Trades" in response.text
        assert "Risk &amp; Macro" in response.text
        assert "Candidates" in response.text
        assert "Learning &amp; Strategies" in response.text
        assert "Ops &amp; Cost" in response.text
        assert "Raised guidance" in response.text
        assert "Needs Review" in response.text
        assert "Open Positions" in response.text
        assert "System Issues" in response.text
        assert "trades-canvas" not in response.text
        assert "TSLA" not in response.text
        assert "AI Infrastructure" not in response.text
        assert "gpt-5" not in response.text
        assert "surface-table-wrap" in response.text
        assert "surface-block" in response.text
        assert "surface-block-count" in response.text
        assert "overview-operator-strip" in response.text
        assert "overview-metric-card" in response.text
        assert "Current Session Summary" in response.text
        assert "Broker equity snapshot" in response.text

    def test_trades_tab_only_renders_trades_workspace_body(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL")

        assert response.status_code == 200
        assert "trades-canvas" in response.text
        assert "Signal Summary" in response.text
        assert "Breakout confirmed + risk approved" in response.text
        assert "ticker-card-meta" in response.text
        assert "meta-pill" in response.text
        assert "support-kv-row" in response.text
        assert "AI Infrastructure" not in response.text
        assert "gpt-5" not in response.text
        assert "Stock Positions" not in response.text

    def test_trade_detail_drilldown_renders_when_decision_selected(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&decision_id=decision-action&detail_tab=decisions")

        assert response.status_code == 200
        assert "Latest Conclusion" in response.text
        assert "Trade Decision" in response.text
        assert "own_earnings_beat_raise" in response.text
        assert "within_limits" in response.text
        assert "History" in response.text
        assert 'data-panel="timeline"' in response.text
        assert 'href="/today?tab=trades&ticker=AAPL&detail_tab=trend"' not in response.text
        assert 'href="/today?tab=trades&ticker=AAPL&detail_tab=decisions"' not in response.text
        assert 'href="/today?tab=trades&ticker=AAPL&detail_tab=risk"' not in response.text
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
        assert "ticker-support-grid" in response.text
        assert "ticker-detail-nav" in response.text
        assert "Action Now" in response.text
        assert "Open Positions" in response.text
        assert "Closed Today" in response.text
        assert "Reviewing" in response.text
        assert "Watch" in response.text
        assert "Latest Conclusion" in response.text
        assert "Lifecycle" in response.text
        assert "Open Position" in response.text
        assert 'data-panel="timeline"' in response.text
        assert "Trade Decision" in response.text
        assert "Signal Summary" in response.text
        assert "Event / News Summary" in response.text
        assert "Raised guidance: Demand improved across core products." in response.text
        assert "Risk Manager Summary" in response.text
        assert "Position / Execution State" in response.text
        assert 'data-testid="signal-summary"' in response.text
        assert 'data-testid="history-cards"' in response.text
        assert "History" in response.text
        assert "sticky-rail" in response.text
        assert 'data-panel="trend"' not in response.text
        assert 'data-panel="decisions"' not in response.text
        assert 'data-panel="risk"' not in response.text

    def test_trades_workspace_renders_timeline_as_only_detail_section(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        payload["ticker_workspace"]["selected_detail_tab"] = "timeline"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL&detail_tab=timeline")

        assert response.status_code == 200
        assert "ticker-detail-nav" in response.text
        assert "Timeline" in response.text
        assert 'href="/today?tab=trades&ticker=AAPL&detail_tab=trend"' not in response.text
        assert 'href="/today?tab=trades&ticker=AAPL&detail_tab=decisions"' not in response.text
        assert 'href="/today?tab=trades&ticker=AAPL&detail_tab=risk"' not in response.text
        assert 'data-panel="timeline"' in response.text
        assert 'data-panel="trend"' not in response.text
        assert 'data-panel="decisions"' not in response.text
        assert 'data-panel="risk"' not in response.text
        assert "Primary strategy selected" not in response.text

    def test_trades_workspace_invalid_detail_tab_falls_back_to_timeline(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        payload["ticker_workspace"]["selected_detail_tab"] = "timeline"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL&detail_tab=decisions")

        assert response.status_code == 200
        assert 'data-panel="timeline"' in response.text
        assert 'data-panel="decisions"' not in response.text
        assert 'data-panel="risk"' not in response.text
        assert "Decision Ledger" not in response.text
        assert "Risk Posture" not in response.text
        assert 'data-panel="decisions"' not in response.text

    def test_risk_macro_tab_renders_summary_first_structure(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "risk-macro"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=risk-macro")

        assert response.status_code == 200
        assert "Risk Status" in response.text
        assert "Top Risk Sources" in response.text
        assert "Data / Model Availability" in response.text
        assert "Advanced Risk Audit" in response.text
        assert "Within Limits" in response.text
        assert "Technology concentration" in response.text
        assert "Macro regime unavailable" in response.text
        assert "macro-strip" in response.text
        assert 'data-testid="event-risk-list"' in response.text
        assert "direct earnings gap risk" in response.text
        assert "AAPL / high" in response.text
        assert "block_open" in response.text
        assert "trades-canvas" not in response.text
        assert "AI Infrastructure" not in response.text

    def test_overview_tab_renders_command_center_modules(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "overview"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=overview")

        assert response.status_code == 200
        assert "Needs Review" in response.text
        assert "Open Positions" in response.text
        assert "System Issues" in response.text
        assert "Closed recently and ready for review" in response.text
        assert "Open position, risk within limits" in response.text
        assert "Macro regime unavailable" in response.text
        assert "Session Watch" not in response.text

    def test_portfolio_tab_renders_summary_first_structure(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "portfolio"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=portfolio")

        assert response.status_code == 200
        assert "Holdings Snapshot" in response.text
        assert "Stock Book" in response.text
        assert "surface-table-wrap" in response.text
        assert "$2,145.20" in response.text
        assert "$420.00" in response.text
        assert "surface-block" in response.text
        assert "surface-block-count" in response.text
        assert "trades-canvas" not in response.text

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
                "duplicate_count": 4,
                "alternatives": (
                    {"strategy_label": "Pullback reclaim", "operator_summary": "Alternative pullback setup."},
                    {"strategy_label": "RS breakout", "operator_summary": "Secondary continuation lens."},
                    {"strategy_label": "Reversal try", "operator_summary": "Lower-ranked reversal setup."},
                ),
                "detail_internal_ids": {"strategy_match": "gap_continuation_v1"},
            },
        )
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=candidates")

        assert response.status_code == 200
        assert "Action Queue" in response.text
        assert "Decision Readout" in response.text
        assert "Manual Review Queue" in response.text
        assert "Theme Monitor" in response.text
        assert "surface-block" in response.text
        assert "Manual Review Queue" in response.text
        assert "Review Only" in response.text
        assert "Still on watch" in response.text
        assert "Candidate Decisions" in response.text
        assert "Momentum setup with clean catalyst." in response.text
        assert "Strategy alternatives" in response.text
        assert "Pullback reclaim" in response.text
        assert "Awaiting fresh event-risk snapshot" in response.text
        assert "Advanced Universe Context" in response.text
        assert "Advanced" in response.text
        assert "theme-chip-list" in response.text
        assert "scroll-panel" in response.text
        assert "scroll-rail" in response.text
        assert 'data-testid="candidate-group-AAPL"' in response.text
        assert "trades-canvas" not in response.text
        assert "Signal Summary" not in response.text

    def test_learning_tab_renders_summary_first_structure(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "learning-strategies"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=learning-strategies")

        assert response.status_code == 200
        assert "Reflection Snapshot" in response.text
        assert "Strategy Pipeline" in response.text
        assert "Performance Snapshot" in response.text
        assert "surface-block" in response.text
        assert "Bullish catalyst continuation respected" in response.text
        assert "Strategy Performance" in response.text
        assert "$4,200.00" in response.text
        assert "Tighten low-volume gap entries" in response.text
        assert "tracked strategy" in response.text
        assert "trades-canvas" not in response.text

    def test_ops_cost_tab_renders_summary_first_structure(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "ops-cost"
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=ops-cost")

        assert response.status_code == 200
        assert "LLM Spend" in response.text
        assert "Model Footprint" in response.text
        assert "Usage Ledger" in response.text
        assert "$12.30" in response.text
        assert "Provider Usage" in response.text
        assert "Provider Calls" in response.text
        assert "market_bars" in response.text
        assert "surface-block" in response.text
        assert "gpt-5" in response.text
        assert "trades-canvas" not in response.text

    def test_timeline_tab_renders_history_cards(self, client):
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
                "signal_summary": ("Sentiment negative", "direct negative catalyst: general_news"),
                "trade_decision": {"label": "No Trade", "summary": "Catalyst quality faded"},
                "risk": {"status_label": "Reduced", "summary": "Event risk increased"},
                "change_summary": ("sentiment neutral -> negative", "risk approved -> reduced"),
            },
        )
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL&detail_tab=timeline")

        assert response.status_code == 200
        assert 'data-panel="timeline"' in response.text
        assert "History" in response.text
        assert "Pre Open Baseline" in response.text
        assert "Pre Open Rerun" in response.text
        assert "Trade Decision" in response.text
        assert "Risk" in response.text
        assert "sentiment neutral -&gt; negative" in response.text
        assert "Timeline Detail Sheet" not in response.text
        assert 'data-panel="trend"' not in response.text

    def test_trades_empty_support_copy_uses_quiet_standardized_text(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["signal_summary"]["summary_bullets"] = ()
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["signal_summary"]["hidden_bullet_count"] = 3
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["signal_summary"]["grouped_sections"] = (
            {"label": "Policy / Social", "bullets": ("Policy headline turned into a tailwind",)},
        )
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["signal_summary"]["technical_charts"] = ()
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["signal_summary"]["news_snippets"] = ()
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["signal_summary"]["fundamental_snippets"] = ()
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["position_execution"]["summary"] = None
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL")

        assert response.status_code == 200
        assert "surface-empty-copy" in response.text
        assert "Unavailable." in response.text

    def test_trades_tab_renders_signal_summary_sections_and_timeline_delta_fields(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "trades"
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["signal_summary"]["latest_signal_time_label"] = (
            "2026-06-18 17:41 UTC"
        )
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["signal_summary"]["primary_sections"] = (
            {"label": "Trend", "bullets": ("Relative strength improved vs QQQ",)},
            {"label": "Policy / Social", "bullets": ("Policy headline turned into a tailwind",)},
        )
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["signal_summary"]["hidden_bullet_count"] = 2
        payload["ticker_workspace"]["detail"]["latest_conclusion"]["signal_summary"]["grouped_sections"] = (
            {"label": "Insider", "bullets": ("Insider cluster buy count accelerated",)},
            {"label": "Policy / Social", "bullets": ("Policy headline turned into a tailwind",)},
        )
        payload["ticker_workspace"]["detail"]["tabs"]["timeline"] = (
            {
                "title": "Pre Open Baseline",
                "time_label": "2026-06-18 16:30 UTC",
                "change_type": "baseline",
                "signal_summary": ("Sentiment neutral", "Risk approved"),
                "trade_decision": {"label": "Watch", "summary": "Waiting for confirmation"},
                "risk": {"status_label": "Approved", "summary": "Within limits"},
                "change_summary": (),
            },
            {
                "title": "Pre Open Rerun",
                "time_label": "2026-06-18 16:42 UTC",
                "change_type": "material_change",
                "signal_summary": ("Sentiment negative", "Risk reduced"),
                "trade_decision": {"label": "No Trade", "summary": "Catalyst quality faded after a fresh event-risk check."},
                "risk": {"status_label": "Reduced", "summary": "Event risk increased"},
                "change_summary": ("sentiment neutral -> negative", "risk approved -> reduced"),
            },
        )
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=trades&ticker=AAPL")

        assert response.status_code == 200
        assert "Latest signal 2026-06-18 17:41 UTC" in response.text
        assert "Trend" in response.text
        assert "Policy / Social" in response.text
        assert "2 more signals in other groups" in response.text
        assert "Signal summary audit" not in response.text
        assert "sentiment neutral -&gt; negative" in response.text

    def test_overview_empty_state_uses_quiet_standardized_text(self, client):
        payload = _dashboard_payload()
        payload["selected_tab"] = "overview"
        payload["overview"]["live_alerts"] = ()
        payload["overview"]["material_changes"] = ()
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get("/today?tab=overview")

        assert response.status_code == 200
        assert "No live alerts." in response.text
        assert "No material changes." in response.text
        assert response.text.count("surface-empty-copy") >= 2

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
            patch("src.web.routers.today._load_llm_usage", return_value=()),
        ):
            dashboard = load_today_dashboard(
                session,
                selected_tab="overview",
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
            patch("src.web.routers.today._load_llm_usage", return_value=()),
            patch("src.web.routers.today._load_trade_detail") as load_trade_detail,
        ):
            dashboard = load_today_dashboard(
                session,
                selected_tab="overview",
                decision_id=None,
                selected_ticker="NVDA",
            )

        assert dashboard["ticker_workspace"]["selected_ticker"] is None
        assert dashboard["ticker_workspace"]["detail"] is None
        assert dashboard["trades"]["selected_detail"] is None
        load_trade_detail.assert_not_called()

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
                "risk": {"history": (), "raw_json": None},
                "raw_json": {},
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
        }

    def test_load_candidate_rows_translates_operator_facing_labels(self):
        from src.web.routers.today import _load_candidate_rows

        session = MagicMock()
        session.query.return_value = _ListQuery(
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
        )

        rows = _load_candidate_rows(session)

        assert rows == (
            {
                "ticker": "UBER",
                "selection_source": "direct_negative_catalyst",
                "why_reviewed_label": "Negative catalyst detected",
                "result_status": "blocked_by_missing_data",
                "current_outcome_label": "Blocked: required data unavailable",
                "trade_identity": "watch_only",
                "trade_identity_label": "Watch Only",
                "strategy_match": "valuation_repair_quality_software_v1",
                "strategy_label": "Valuation repair setup",
                "operator_summary": "Negative catalyst detected. Blocked: required data unavailable. Watch Only.",
                "detail_internal_ids": {
                    "selection_source": "direct_negative_catalyst",
                    "result_status": "blocked_by_missing_data",
                    "trade_identity": "watch_only",
                    "strategy_match": "valuation_repair_quality_software_v1",
                },
            },
        )

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
                "strategy_id": "breakout_v1",
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
                selected_tab="overview",
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
                selected_tab="overview",
                decision_id=None,
                selected_ticker=None,
            )

        assert dashboard["header"]["macro_regime"] == "risk_off"

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
    stack.enter_context(patch("src.web.routers.today._load_llm_usage", return_value=()))
    return _exit_stack_with_result(stack, load_trade_detail)


@contextmanager
def _session_context(session: MagicMock):
    yield session


@contextmanager
def _exit_stack_with_result(stack: ExitStack, result):
    with stack:
        yield result
