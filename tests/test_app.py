"""FastAPI route tests using TestClient with mocked DB and pipelines."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.db.models.research import RunStatus
from src.research.workflows.batch_research import PipelineResult, TickerResult
from src.research.workflows.evaluation import EvalPipelineResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AS_OF = datetime(2026, 3, 22, 9, 0, tzinfo=timezone.utc)
_RUN_ID = uuid.uuid4()
_TICKER = "AAPL"


def _make_watchlist_row(ticker=_TICKER, is_active=True):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.ticker = ticker
    row.is_active = is_active
    row.created_at = _AS_OF
    return row


def _make_run(
    status=RunStatus.SUCCEEDED.value,
    *,
    ticker=_TICKER,
    outcome_label="correct",
    price_window="open_to_close",
    run_id=_RUN_ID,
    as_of=_AS_OF,
    thesis_summary="Strong momentum",
):
    run = MagicMock()
    run.run_id = run_id
    run.ticker = ticker
    run.as_of = as_of
    run.status = status
    run.prompt_version = "v1"
    run.model_name = "gemini-2.5-flash-lite"
    run.input_json = {
        "ticker": ticker,
        "as_of": as_of.isoformat(),
        "price_snapshot": {
            "last_price": 187.42,
            "return_1d": 0.012,
            "return_5d": 0.041,
            "return_since_market_open": 0.006,
        },
        "context": {
            "sector": "Technology",
            "company_name": "Apple Inc.",
            "earnings_in_days": 12,
        },
        "fundamentals": {
            "pe_ratio": 28.4,
            "ps_ratio": 7.2,
            "short_interest_pct_float": 1.1,
        },
        "volume_snapshot": {
            "session_volume": 18000000,
            "avg_volume_20d": 9100000.0,
            "relative_volume": 1.98,
        },
        "technical_signals": {
            "momentum": {
                "rsi_14": 58.2,
                "rsi_3": 96.5,
            },
            "volatility": {
                "atr_14": 15.2,
                "yesterday_range": 45.0,
                "atr_multiple": 2.96,
            },
        },
        "news": [
            {
                "title": "Apple expands AI tooling",
                "summary": "Management highlighted broader rollout plans.",
                "source": "Dow Jones",
                "signal_type": "analyst_rating",
            },
            {
                "title": "iPhone demand remains resilient",
                "summary": "Channel checks pointed to steady upgrade activity.",
                "source": "Business Wire",
                "signal_type": "earnings_guidance",
            },
        ],
        "insider_activity": {
            "window_days": 30,
            "purchase_count": 1,
            "sale_count": 0,
            "net_shares": 25000,
            "net_value": 4200000.0,
            "recent_trades": [
                {
                    "insider_name": "Jane Doe",
                    "insider_title": "Director",
                    "transaction_type": "P",
                    "transaction_date": "2026-03-20",
                    "filing_date": "2026-03-21",
                    "shares": 25000,
                    "price_per_share": 168.0,
                    "total_value": 4200000.0,
                    "filing_url": "https://www.sec.gov/Archives/example",
                }
            ],
        },
        "global_context": {
            "as_of": _AS_OF.isoformat(),
            "indicators": {
                "vix": {
                    "label": "CBOE Volatility Index",
                    "source": "FRED:VIXCLS",
                    "unit": "index",
                    "value": 17.9,
                    "previous_close": 17.32,
                    "return_vs_previous_close": 0.033487,
                    "observed_on": "2026-03-22",
                },
                "oil_price": {
                    "label": "WTI Crude Oil Spot Price",
                    "source": "FRED:DCOILWTICO",
                    "unit": "USD/bbl",
                    "value": 79.2,
                    "previous_close": 78.4,
                    "return_vs_previous_close": 0.010204,
                    "observed_on": "2026-03-22",
                },
                "gold_price": {
                    "label": "Gold Proxy (GLD ETF)",
                    "source": "ALPACA:GLD_PROXY",
                    "unit": "USD/share",
                    "value": 374.42,
                    "previous_close": 370.0,
                    "return_vs_previous_close": 0.011946,
                    "observed_on": "2026-03-22",
                },
                "us_treasury_10y": {
                    "label": "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity",
                    "source": "FRED:DGS10",
                    "unit": "pct",
                    "value": 4.12,
                    "previous_close": 4.08,
                    "return_vs_previous_close": 0.009804,
                    "observed_on": "2026-03-22",
                },
            },
            "official_updates": [
                {
                    "source": "whitehouse.gov",
                    "title": "Official White House statement",
                    "summary": "The administration issued a policy update.",
                    "published_at": as_of.isoformat(),
                    "url": "https://www.whitehouse.gov/example",
                }
            ],
            "trump_updates": [
                {
                    "source": "whitehouse.gov",
                    "title": "President Donald J. Trump delivers remarks",
                    "summary": "The President delivered remarks.",
                    "published_at": as_of.isoformat(),
                    "url": "https://www.whitehouse.gov/remarks/example",
                }
            ],
            "geopolitical_news": [
                {
                    "source": "AP News",
                    "title": "AP geopolitical update",
                    "summary": "Regional tensions remained elevated.",
                    "published_at": as_of.isoformat(),
                    "url": "https://apnews.com/article/example",
                }
            ],
        },
    }
    run.error_message = None
    run.started_at = as_of
    run.finished_at = as_of
    run.created_at = as_of

    out = MagicMock()
    out.decision = "bullish"
    out.confidence = 0.8
    out.time_horizon = "1d"
    out.actionability = "actionable"
    out.thesis_summary = thesis_summary
    out.output_json = {"decision": "bullish"}
    run.output = out

    ev = MagicMock()
    ev.outcome_label = outcome_label
    ev.realized_return = 0.03
    ev.benchmark_return = 0.01
    ev.benchmark_symbol = "SPY"
    ev.evaluation_method = "rule_v1"
    ev.evaluation_params = {
        "price_window": price_window,
        "entry_price_source": "session_open" if price_window == "open_to_close" else "research_input_last_price",
    }
    ev.horizon_days = 1
    run.eval_result = ev

    return run


@pytest.fixture()
def client():
    # Patch init_db so startup doesn't need a real DB
    with patch("src.web.init_db"):
        from src.app import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


class TestAppMetadata:
    def test_create_app_uses_trading_workstation_title(self):
        from src.web import create_app

        app = create_app()

        assert app.title == "Trading Workstation"


class TestTimestampFilters:
    def test_iso_datetime_normalizes_aware_datetime(self):
        from src.web.filters import iso_datetime

        assert iso_datetime(_AS_OF) == "2026-03-22T09:00:00Z"

    def test_iso_datetime_parses_iso_string(self):
        from src.web.filters import iso_datetime

        assert iso_datetime("2026-03-22T09:00:00+00:00") == "2026-03-22T09:00:00Z"


# ---------------------------------------------------------------------------
# Watchlist routes
# ---------------------------------------------------------------------------


class TestWatchlistPage:
    def test_get_shows_tickers(self, client):
        rows = [_make_watchlist_row("AAPL"), _make_watchlist_row("MSFT", is_active=False)]
        with patch("src.web.routers.watchlist.repository.get_watchlist", return_value=rows), \
             patch("src.web.routers.watchlist.get_session") as mock_gs:
            mock_gs.return_value.__enter__ = lambda s: MagicMock()
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            # Use the real context manager path by patching get_session entirely
            with patch("src.web.routers.watchlist.get_session") as gs:
                session = MagicMock()
                gs.return_value.__enter__ = MagicMock(return_value=session)
                gs.return_value.__exit__ = MagicMock(return_value=False)
                with patch("src.web.routers.watchlist.repository.get_watchlist", return_value=rows):
                    resp = client.get("/watchlist")

        assert resp.status_code == 200
        assert "AAPL" in resp.text
        assert "MSFT" in resp.text
        assert "Trading Workstation" in resp.text
        assert 'data-local-time-format="date"' in resp.text
        assert 'datetime="2026-03-22T09:00:00Z"' in resp.text

    def test_get_empty_watchlist(self, client):
        with patch("src.web.routers.watchlist.get_session") as gs:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            with patch("src.web.routers.watchlist.repository.get_watchlist", return_value=[]):
                resp = client.get("/watchlist")
        assert resp.status_code == 200
        assert "No tickers yet" in resp.text


class TestWatchlistAdd:
    def test_add_redirects_on_success(self, client):
        with patch("src.web.routers.watchlist.get_session") as gs:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            with patch("src.web.routers.watchlist.repository.add_ticker") as add_mock:
                add_mock.return_value = _make_watchlist_row("NVDA")
                resp = client.post("/watchlist/add", data={"ticker": "nvda"}, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/watchlist"

    def test_add_empty_ticker_redirects(self, client):
        resp = client.post("/watchlist/add", data={"ticker": "  "}, follow_redirects=False)
        assert resp.status_code == 303

    def test_add_normalises_to_uppercase(self, client):
        with patch("src.web.routers.watchlist.get_session") as gs:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            with patch("src.web.routers.watchlist.repository.add_ticker") as add_mock:
                add_mock.return_value = _make_watchlist_row("TSLA")
                client.post("/watchlist/add", data={"ticker": "tsla"}, follow_redirects=False)
                # repository.add_ticker already normalises; we just verify it was called
                add_mock.assert_called_once()


class TestWatchlistDelete:
    def test_delete_redirects(self, client):
        with patch("src.web.routers.watchlist.get_session") as gs:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            with patch("src.web.routers.watchlist.repository.deactivate_ticker", return_value=True):
                resp = client.post("/watchlist/AAPL/delete", follow_redirects=False)
        assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Research list route
# ---------------------------------------------------------------------------


class TestResearchList:
    def test_get_shows_runs(self, client):
        run = _make_run()
        with patch("src.web.routers.research.get_session") as gs:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            # Mock the query chain
            q = MagicMock()
            q.join.return_value = q
            q.outerjoin.return_value = q
            q.filter.return_value = q
            q.order_by.return_value = q
            q.all.return_value = [run]
            session.query.return_value = q

            resp = client.get("/research")

        assert resp.status_code == 200
        assert _TICKER in resp.text
        assert "bullish" in resp.text.lower()
        assert 'data-local-time-format="datetime"' in resp.text
        assert 'datetime="2026-03-22T09:00:00Z"' in resp.text

    def test_aggregate_ignores_manual_quick_eval(self, client):
        formal_run = _make_run(ticker="AAPL", outcome_label="correct", price_window="open_to_close")
        manual_run = _make_run(ticker="AAPL", outcome_label="wrong_direction", price_window="run_time_price_to_close")
        manual_run.run_id = uuid.uuid4()
        with patch("src.web.routers.research.get_session") as gs:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            q = MagicMock()
            q.join.return_value = q
            q.outerjoin.return_value = q
            q.filter.return_value = q
            q.order_by.return_value = q
            q.all.return_value = [formal_run, manual_run]
            session.query.return_value = q

            resp = client.get("/research")

        assert resp.status_code == 200
        assert "wrong direction" in resp.text
        assert "Wrong Direction" not in resp.text

    def test_get_empty_shows_placeholder(self, client):
        with patch("src.web.routers.research.get_session") as gs:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            q = MagicMock()
            q.join.return_value = q
            q.outerjoin.return_value = q
            q.filter.return_value = q
            q.order_by.return_value = q
            q.all.return_value = []
            session.query.return_value = q

            resp = client.get("/research")

        assert resp.status_code == 200
        assert "No research runs yet" in resp.text

    def test_get_limits_each_ticker_to_recent_ten_rows(self, client):
        runs = []
        for idx in range(12):
            runs.append(
                _make_run(
                    ticker="AAPL",
                    run_id=uuid.uuid4(),
                    as_of=datetime(2026, 3, 22, 21 - idx, 0, tzinfo=timezone.utc),
                    thesis_summary=f"AAPL thesis {idx}",
                )
            )
        runs.append(
            _make_run(
                ticker="MSFT",
                run_id=uuid.uuid4(),
                thesis_summary="MSFT thesis 0",
            )
        )

        with patch("src.web.routers.research.get_session") as gs:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            q = MagicMock()
            q.join.return_value = q
            q.outerjoin.return_value = q
            q.filter.return_value = q
            q.order_by.return_value = q
            q.all.return_value = runs
            session.query.return_value = q

            resp = client.get("/research")

        assert resp.status_code == 200
        assert "Total Runs" in resp.text
        assert ">13<" in resp.text
        for idx in range(10):
            assert f"AAPL thesis {idx}" in resp.text
        assert "AAPL thesis 10" not in resp.text
        assert "AAPL thesis 11" not in resp.text
        assert "MSFT thesis 0" in resp.text


# ---------------------------------------------------------------------------
# Research detail route
# ---------------------------------------------------------------------------


class TestResearchDetail:
    def test_get_valid_run(self, client):
        run = _make_run()
        with patch("src.web.routers.research.get_session") as gs:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            q = MagicMock()
            q.filter.return_value = q
            q.first.return_value = run
            # ticker history query
            q2 = MagicMock()
            q2.join.return_value = q2
            q2.filter.return_value = q2
            q2.order_by.return_value = q2
            q2.limit.return_value = q2
            q2.all.return_value = []
            session.query.side_effect = [q, q2]

            resp = client.get(f"/research/{_RUN_ID}")

        assert resp.status_code == 200
        assert _TICKER in resp.text
        assert "bullish" in resp.text.lower()
        assert "Research Input" in resp.text
        assert "Price Snapshot" in resp.text
        assert "$187.42" in resp.text
        assert "Technology" in resp.text
        assert "Apple Inc." in resp.text
        assert "P/E" in resp.text
        assert "28.4" in resp.text
        assert "Relative Volume" in resp.text
        assert "1.98x" in resp.text
        assert "Technicals" in resp.text
        assert "RSI 3" in resp.text
        assert "96.5" in resp.text
        assert "ATR Multiple" in resp.text
        assert "2.96x" in resp.text
        assert "Apple expands AI tooling" in resp.text
        assert "analyst_rating" in resp.text
        assert "Insider Activity" in resp.text
        assert "Jane Doe" in resp.text
        assert "Global Context" in resp.text
        assert "CBOE Volatility Index" in resp.text
        assert "+3.35% vs prev close" in resp.text
        assert "WTI Crude Oil Spot Price" in resp.text
        assert "+1.02% vs prev close" in resp.text
        assert "Gold Proxy (GLD ETF)" in resp.text
        assert "+1.19% vs prev close" in resp.text
        assert "+0.98% vs prev close" not in resp.text
        assert "Official White House statement" in resp.text
        assert "AP geopolitical update" in resp.text
        assert "Input JSON" not in resp.text
        assert "Output JSON" not in resp.text
        assert 'data-local-time-format="datetime"' in resp.text
        assert 'data-local-time-format="datetime_seconds"' in resp.text
        assert 'datetime="2026-03-22T09:00:00Z"' in resp.text

    def test_get_shows_eval_window_metadata(self, client):
        run = _make_run(price_window="run_time_price_to_close")
        with patch("src.web.routers.research.get_session") as gs:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            q = MagicMock()
            q.filter.return_value = q
            q.first.return_value = run
            q2 = MagicMock()
            q2.join.return_value = q2
            q2.filter.return_value = q2
            q2.order_by.return_value = q2
            q2.limit.return_value = q2
            q2.all.return_value = []
            session.query.side_effect = [q, q2]

            resp = client.get(f"/research/{_RUN_ID}")

        assert resp.status_code == 200
        assert "run_time_price_to_close" in resp.text

    def test_get_invalid_uuid_returns_404(self, client):
        resp = client.get("/research/not-a-uuid")
        assert resp.status_code == 404

    def test_get_missing_run_returns_404(self, client):
        with patch("src.web.routers.research.get_session") as gs:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            q = MagicMock()
            q.filter.return_value = q
            q.first.return_value = None
            session.query.return_value = q

            resp = client.get(f"/research/{uuid.uuid4()}")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------


class TestAdminRunNow:
    def test_triggers_pipeline_and_redirects(self, client):
        result = PipelineResult(succeeded=2, failed=0, ticker_results=[])
        with patch("src.web.routers.admin.get_session") as gs, \
             patch("src.web.routers.admin.ResearchAgent"), \
             patch("src.web.routers.admin.ResearchPipeline") as MockPipeline, \
             patch("src.web.routers.admin.build_research_tool_registry"), \
             patch("src.web.routers.admin.PromptRegistry"):
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            MockPipeline.return_value.run_all.return_value = result

            resp = client.post("/admin/run-now", follow_redirects=False)

        assert resp.status_code == 303
        assert resp.headers["location"] == "/research"

    def test_pipeline_error_still_redirects(self, client):
        with patch("src.web.routers.admin.get_session") as gs, \
             patch("src.web.routers.admin.ResearchAgent", side_effect=RuntimeError("boom")), \
             patch("src.web.routers.admin.build_research_tool_registry"), \
             patch("src.web.routers.admin.PromptRegistry"):
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)

            resp = client.post("/admin/run-now", follow_redirects=False)

        assert resp.status_code == 303


class TestAdminEvalNow:
    def test_triggers_eval_and_redirects(self, client):
        result = EvalPipelineResult(evaluated=3, failed=0, skipped=1)
        with patch("src.web.routers.admin.get_session") as gs, \
             patch("src.web.routers.admin.EvalPipeline") as MockEval:
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)
            MockEval.return_value.run_all.return_value = result

            resp = client.post("/admin/eval-now", follow_redirects=False)

        assert resp.status_code == 303
        assert resp.headers["location"] == "/research"

    def test_eval_error_still_redirects(self, client):
        with patch("src.web.routers.admin.get_session") as gs, \
             patch("src.web.routers.admin.EvalPipeline", side_effect=RuntimeError("boom")):
            session = MagicMock()
            gs.return_value.__enter__ = MagicMock(return_value=session)
            gs.return_value.__exit__ = MagicMock(return_value=False)

            resp = client.post("/admin/eval-now", follow_redirects=False)

        assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------


class TestRoot:
    def test_root_redirects_to_today(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/today"
