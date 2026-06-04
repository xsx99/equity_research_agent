"""Today dashboard route tests."""
from __future__ import annotations

import uuid
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
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
    decision_id = str(uuid.uuid4())
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
            "rows": (
                {
                    "trading_decision_id": decision_id,
                    "decision_time": datetime(2026, 6, 2, 13, 45, tzinfo=timezone.utc),
                    "ticker": "AAPL",
                    "decision": "enter_long",
                    "instrument_type": "stock",
                    "trade_identity": "tactical_stock_trade",
                    "selected_strategy_id": "earnings_drift_v1",
                    "expression_bucket_id": "long_stock",
                    "approved_weight": Decimal("0.05"),
                    "confidence": Decimal("0.72"),
                    "risk_status": "approved",
                    "order_status": "filled",
                },
            ),
            "selected_detail": {
                "trading_decision_id": decision_id,
                "ticker": "AAPL",
                "llm_decision_json": {"decision": "enter_long"},
                "validation_status": "succeeded",
                "signal_snapshot": {"fresh_catalyst_type": "own_earnings_beat_raise"},
                "strategy_scores": (
                    {"strategy_id": "earnings_drift_v1", "candidate_score": Decimal("0.81")},
                ),
                "risk_decision": {"status": "approved", "reason_code": "within_limits"},
                "outcomes": (
                    {"evaluation_status": "interim", "alpha": Decimal("0.02")},
                ),
            },
        },
        "ticker_workspace": {
            "selected_ticker": "AAPL",
            "buckets": {
                "action_now": (
                    {
                        "ticker": "AAPL",
                        "decision": "enter_long",
                        "confidence": Decimal("0.72"),
                    },
                ),
                "in_position": (),
                "watch": (),
            },
            "detail": {
                "ticker": "AAPL",
                "latest_conclusion": {
                    "trade_decision": {"label": "Enter Long"},
                    "signal_summary": {
                        "summary_bullets": ("Relative strength improved vs QQQ",),
                        "technical_charts": (),
                        "news_snippets": (),
                        "fundamental_snippets": (),
                    },
                    "risk_summary": {"status": "approved", "reason": "within_limits"},
                    "position_execution": {"order_status": "filled"},
                },
                "tabs": {
                    "timeline": (),
                    "trend": {"technical": (), "news": (), "fundamental": ()},
                    "decisions": (),
                    "risk": {"current_stance": {}, "position_state": {}, "history": ()},
                },
            },
        },
        "risk_macro": {
            "risk_config_version": "risk_config_resolver_v1",
            "binding_constraints": ("theme cap near limit",),
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
            "exposures": (
                {"factor_type": "sector", "factor_name": "Technology", "exposure": Decimal("0.37")},
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
            "rows": (
                {
                    "ticker": "MSFT",
                    "selection_source": "scanner",
                    "result_status": "ordinary_watch",
                    "trade_identity": "watch_only",
                    "strategy_match": "relative_strength_breakout_v1",
                },
            ),
            "manual_requests": (
                {
                    "manual_ticker_request_id": manual_request_id,
                    "ticker": "TSLA",
                    "reason": "post-event review",
                    "mode": "review_only",
                    "status": "active",
                    "latest_result_status": "ordinary_watch",
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
        with patch("src.web.routers.today.load_today_dashboard", return_value=_dashboard_payload()):
            response = client.get("/today")

        assert response.status_code == 200
        assert "Today Dashboard" in response.text
        assert "Overview" in response.text
        assert "Portfolio" in response.text
        assert "Trades" in response.text
        assert "Risk &amp; Macro" in response.text
        assert "Candidates" in response.text
        assert "Learning &amp; Strategies" in response.text
        assert "Ops &amp; Cost" in response.text
        assert "Raised guidance" in response.text
        assert "AAPL" in response.text
        assert "TSLA" in response.text
        assert "AI Infrastructure" in response.text
        assert "gpt-5" in response.text

    def test_trade_detail_drilldown_renders_when_decision_selected(self, client):
        payload = _dashboard_payload()
        detail_id = payload["trades"]["rows"][0]["trading_decision_id"]
        with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
            response = client.get(f"/today?tab=trades&decision_id={detail_id}")

        assert response.status_code == 200
        assert "Trade Detail" in response.text
        assert "own_earnings_beat_raise" in response.text
        assert "within_limits" in response.text
        assert "0.81" in response.text

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
            response = client.get("/today?ticker=MSFT")

        assert response.status_code == 200
        assert "Trade Detail" in response.text
        assert "<strong>Ticker:</strong> NVDA" in response.text
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
            response = client.get("/today")

        assert response.status_code == 200
        assert "Trade Detail" in response.text
        assert "<strong>Ticker:</strong> NVDA" in response.text
        load_trade_detail.assert_called_once_with(session, "decision-action")

    def test_today_dashboard_route_renders_empty_workspace_when_no_tickers_exist(self, client):
        session = _query_stub_session()

        with _patched_today_route_dependencies(
            session,
            trade_rows=[],
            selected_detail=None,
        ) as load_trade_detail:
            response = client.get("/today")

        assert response.status_code == 200
        assert "No trading decisions yet." in response.text
        assert "Trade Detail" not in response.text
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
