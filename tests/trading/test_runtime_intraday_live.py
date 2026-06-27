from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from src.trading.intraday.signals import IntradaySignalScanRecord, IntradaySignalSnapshotRecord
from src.trading.events import CalendarEventPipeline, PortfolioEventRiskAssessmentPipeline
from src.trading.risk import HedgeActionRecord, PortfolioRiskIntentRecord, RiskConfigResolver
from src.trading.runtime.dispatch import get_job_phase_handler
from src.trading.runtime.intraday_refresh import (
    LiveIntradayRefreshDependencies,
    LiveIntradayRefreshRuntime,
    run_live_intraday_refresh_once,
)
from src.trading.runtime.intraday_refresh_dependencies import build_live_intraday_refresh_dependencies
from src.trading.runtime.lookahead_risk import LookaheadRiskWorkflowHelper
from src.trading.signals import SignalSnapshotResult
from src.trading.signals.sources import EventNewsItemRecord, SourceRecord


class _CallRecorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def record(self, name: str) -> None:
        self.calls.append(name)


class _ScopeLoader:
    def __init__(self, recorder: _CallRecorder, scope: tuple[str, ...]) -> None:
        self.recorder = recorder
        self.scope = scope

    def load_scope(self, *, decision_time: datetime) -> tuple[str, ...]:
        assert decision_time.tzinfo is not None
        self.recorder.record("load_scope")
        return self.scope


class _BaselineLoader:
    def __init__(self, recorder: _CallRecorder, baselines: dict[str, SignalSnapshotResult]) -> None:
        self.recorder = recorder
        self.baselines = baselines

    def load_for_tickers(self, *, tickers: tuple[str, ...], decision_time: datetime) -> dict[str, SignalSnapshotResult]:
        assert tickers == ("AAPL", "MSFT")
        assert decision_time.tzinfo is not None
        self.recorder.record("load_baselines")
        return dict(self.baselines)


class _PreviousSnapshotLoader:
    def __init__(self, recorder: _CallRecorder, previous: dict[str, IntradaySignalSnapshotRecord]) -> None:
        self.recorder = recorder
        self.previous = previous

    def load_for_tickers(
        self, *, tickers: tuple[str, ...], decision_time: datetime
    ) -> dict[str, IntradaySignalSnapshotRecord]:
        assert tickers == ("AAPL", "MSFT")
        assert decision_time.tzinfo is not None
        self.recorder.record("load_previous_intraday")
        return dict(self.previous)


class _RequestContextLoader:
    def __init__(self, recorder: _CallRecorder, contexts: dict[str, object]) -> None:
        self.recorder = recorder
        self.contexts = contexts

    def load_for_tickers(self, *, tickers: tuple[str, ...], decision_time: datetime) -> dict[str, object]:
        assert tickers == ("AAPL", "MSFT")
        assert decision_time.tzinfo is not None
        self.recorder.record("load_request_context")
        return dict(self.contexts)


class _SourceRefreshService:
    def __init__(self, recorder: _CallRecorder) -> None:
        self.recorder = recorder
        self.calls: list[tuple[tuple[str, ...], str, tuple[str, ...]]] = []

    def refresh_tickers(
        self,
        tickers: tuple[str, ...],
        *,
        as_of: datetime,
        run_type: str,
        source_families: tuple[str, ...],
    ) -> None:
        assert as_of.tzinfo is not None
        self.recorder.record("refresh_sources")
        self.calls.append((tickers, run_type, source_families))


class _IntradaySourceRepository:
    def __init__(self, recorder: _CallRecorder, source_rows: dict[tuple[str, str], tuple[SourceRecord, ...]]) -> None:
        self.recorder = recorder
        self.source_rows = source_rows

    def latest_available_by_family(
        self,
        ticker: str,
        source_family: str,
        decision_time: datetime,
    ) -> tuple[SourceRecord, ...]:
        assert decision_time.tzinfo is not None
        self.recorder.record(f"latest:{ticker}:{source_family}")
        return self.source_rows.get((ticker, source_family), ())


class _PortfolioSyncWorkflow:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(self, *, as_of: datetime) -> object:
        assert as_of.tzinfo is not None
        self.recorder.record("portfolio_sync")
        return self.result


class _MacroLookaheadHelper:
    def __init__(self) -> None:
        self.received_macro_risk_state: str | None = None

    def build_intraday_portfolio_risk_intent(
        self,
        *,
        rebalance_requests,
        portfolio_context,
        config,
        decision_time: datetime,
        macro_risk_state: str | None,
    ) -> PortfolioRiskIntentRecord:
        self.received_macro_risk_state = macro_risk_state
        assert macro_risk_state == "high"
        return PortfolioRiskIntentRecord.create(
            decision_time=decision_time,
            risk_window="1-5d",
            aggregate_risk_state="macro_high_risk",
            hedge_actions=(
                HedgeActionRecord(
                    action="open_hedge",
                    risk_source="macro",
                    severity="high",
                    target_underlier="SPY",
                    target_exposure_type="broad_market",
                    coverage_ratio=0.5,
                    reason_code="macro_high_overlay",
                    metadata_json={},
                ),
            ),
        )


class _NewsAlertService:
    def __init__(self, recorder: _CallRecorder, alerts: tuple[object, ...]) -> None:
        self.recorder = recorder
        self.alerts = alerts

    def build_alerts(
        self,
        *,
        source_items,
        existing_dedupe_keys,
        affected_positions_by_ticker,
        affected_candidates_by_ticker,
        affected_themes_by_ticker,
    ):
        assert {item.ticker for item in source_items} == {"AAPL"}
        assert {item.source_family for item in source_items} == {"events_news", "social_macro"}
        assert existing_dedupe_keys == frozenset({"seen-news"})
        assert affected_positions_by_ticker["AAPL"] == ("AAPL",)
        assert affected_candidates_by_ticker["MSFT"] == ("MSFT",)
        assert affected_themes_by_ticker == {}
        self.recorder.record("build_alerts")
        return self.alerts


class _RebalancePipeline:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result
        self.last_requests: tuple[object, ...] = ()
        self.last_portfolio_risk_intent = None

    def run(
        self,
        *,
        rebalance_requests: tuple[object, ...],
        portfolio_context: object,
        risk_appetite: str,
        portfolio_risk_intent: object | None = None,
        trade_date: datetime | None = None,
        execute_approved: bool = False,
    ) -> object:
        assert portfolio_context is not None
        assert risk_appetite == "balanced"
        if execute_approved:
            assert trade_date is not None
        else:
            assert trade_date is None
        self.last_requests = rebalance_requests
        self.last_portfolio_risk_intent = portfolio_risk_intent
        self.recorder.record("rebalance")
        return self.result


class _TradingRepository:
    def __init__(self, recorder: _CallRecorder) -> None:
        self.recorder = recorder
        self.saved_scan = None
        self.saved_snapshots: list[IntradaySignalSnapshotRecord] = []
        self.saved_alerts: list[object] = []
        self.saved_macro_snapshots: list[object] = []
        self.saved_calendar_events: list[object] = []
        self.saved_event_assessments: list[object] = []

    def save_intraday_signal_scan(self, scan: IntradaySignalScanRecord) -> None:
        self.recorder.record("save_scan")
        self.saved_scan = scan

    def save_intraday_signal_snapshot(self, snapshot: IntradaySignalSnapshotRecord) -> None:
        self.recorder.record(f"save_snapshot:{snapshot.ticker}")
        self.saved_snapshots.append(snapshot)

    def save_news_alert(self, alert: object) -> None:
        self.recorder.record(f"save_alert:{alert.ticker}")
        self.saved_alerts.append(alert)

    def save_macro_snapshot(self, snapshot: object) -> None:
        self.saved_macro_snapshots.append(snapshot)

    def save_calendar_events(self, events: tuple[object, ...]) -> None:
        self.saved_calendar_events.extend(events)

    def save_portfolio_event_risk_assessments(self, assessments: tuple[object, ...]) -> None:
        self.saved_event_assessments.extend(assessments)

    def load_portfolio_event_risk_assessments(self, *, decision_time: datetime, ticker: str | None = None):
        del decision_time, ticker
        return ()


@dataclass(frozen=True)
class _NewsAlert:
    ticker: str
    dedupe_key: str
    alert_type: str = "news"
    severity: str = "high"
    sentiment: str | None = None
    headline: str | None = None
    summary: str | None = None
    source_ticker: str | None = None
    affected_themes: tuple[str, ...] = ()
    readthrough_source_ticker: str | None = None
    metadata_json: dict[str, object] | None = None


def _source_record(*, ticker: str, family: str, payload: dict) -> SourceRecord:
    now = datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc)
    return SourceRecord(
        ticker=ticker,
        source_family=family,
        source="fixture",
        source_table="source_table",
        source_record_id=f"{ticker}-{family}",
        event_time=now,
        published_at=now,
        ingested_at=now,
        available_for_decision_at=now,
        payload=payload,
    )


def _baseline_snapshot(*, ticker: str, sector: str | None = None) -> SignalSnapshotResult:
    now = datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc)
    fundamental_json = {"market_cap": 1_000_000_000}
    if sector is not None:
        fundamental_json["sector"] = sector
    return SignalSnapshotResult(
        signal_snapshot_id=f"{ticker}-baseline",
        ticker=ticker,
        snapshot_type="pre_open",
        decision_time=now,
        available_for_decision_at=now,
        max_input_available_for_decision_at=now,
        signal_json={
            "technical": {"last_price": 100.0, "atr_pct": 0.02, "dollar_volume": 50_000_000.0},
            "fundamental": fundamental_json,
            "insider": {
                "purchase_count_30d": 2,
                "insider_net_buy_value_30d": 300000.0,
            },
            "social_macro": {
                "policy_headwind_flag": False,
                "social_macro_importance_score": 0.1,
            },
        },
        source_freshness_json={
            "technical": "fresh",
            "fundamental": "fresh",
            "insider": "fresh",
            "social_macro": "fresh",
        },
        missing_signals_json=[],
        stale_signals_json=[],
        source_record_refs_json=[],
        source_available_times_json={
            "insider": now.isoformat(),
            "social_macro": now.isoformat(),
        },
        excluded_future_source_count=0,
        point_in_time_passed=True,
        selection_source="scanner",
        manual_request_id=None,
    )


def _previous_intraday(*, ticker: str) -> IntradaySignalSnapshotRecord:
    now = datetime(2026, 6, 4, 15, 0, tzinfo=timezone.utc)
    return IntradaySignalSnapshotRecord(
        intraday_signal_snapshot_id=f"{ticker}-intraday-prev",
        intraday_signal_scan_id="scan-prev",
        ticker=ticker,
        decision_time=now,
        baseline_signal_snapshot_id=f"{ticker}-baseline",
        previous_intraday_snapshot_id=None,
        refreshed_signals_json={"technical": {"last_price": 101.0}},
        carried_forward_signals_json={"fundamental": {"market_cap": 1_000_000_000}},
        delta_vs_baseline_json={"technical": {"last_price": 1.0}},
        delta_vs_previous_json={"technical": {"last_price": 0.5}},
        source_freshness_json={"technical": "fresh"},
        metadata_json={},
        created_at=now,
    )


def _build_runtime() -> tuple[
    LiveIntradayRefreshRuntime,
    _CallRecorder,
    _RebalancePipeline,
    _TradingRepository,
    _SourceRefreshService,
]:
    recorder = _CallRecorder()
    refresh_service = _SourceRefreshService(recorder)
    baseline_time = datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc)
    source_rows = {
        ("AAPL", "technical"): (_source_record(ticker="AAPL", family="technical", payload={"bars": [{"close": 104.0}]}),),
        ("AAPL", "events_news"): (
            _source_record(
                ticker="AAPL",
                family="events_news",
                payload={
                    "event_news_item_id": "news-aapl-1",
                    "ticker": "AAPL",
                    "source_ticker": "AAPL",
                    "event_type": "earnings_update",
                    "direction": "positive",
                    "sentiment": "positive",
                    "importance": "high",
                    "headline": "AAPL guide raised",
                    "summary": "Raised guide",
                    "provider": "fixture",
                    "source_refs_json": [],
                    "dedupe_key": "aapl-news-1",
                    "metadata_json": {},
                },
            ),
        ),
        ("AAPL", "social_macro"): (
            SourceRecord(
                ticker="AAPL",
                source_family="social_macro",
                source="fixture",
                source_table="social_macro_items",
                source_record_id="aapl-social-1",
                event_time=baseline_time,
                published_at=baseline_time,
                ingested_at=baseline_time,
                available_for_decision_at=baseline_time,
                payload={
                    "category": "trump_update",
                    "title": "Trump threatens tighter AI chip export controls",
                    "summary": "Potential AI chip export restriction headwind.",
                    "sentiment_direction": "negative",
                    "importance_score": 0.92,
                    "importance_label": "high",
                    "policy_headwind_flag": True,
                    "policy_tailwind_flag": False,
                    "explicit_ticker_mention_flag": True,
                    "explicit_theme_mention_flag": True,
                    "theme_tags": ["ai_semis"],
                },
            ),
        ),
        ("AAPL", "insider"): (
            SourceRecord(
                ticker="AAPL",
                source_family="insider",
                source="fixture",
                source_table="insider_trades",
                source_record_id="aapl-insider-1",
                event_time=baseline_time,
                published_at=baseline_time,
                ingested_at=baseline_time,
                available_for_decision_at=baseline_time,
                payload={
                    "transaction_type": "purchase",
                    "total_value": 300000.0,
                    "is_officer": True,
                    "is_director": False,
                    "filing_date": "2026-06-04",
                },
            ),
        ),
        ("MSFT", "technical"): (_source_record(ticker="MSFT", family="technical", payload={"bars": [{"close": 98.0}]}),),
        ("MSFT", "events_news"): (),
        ("MSFT", "social_macro"): (),
        ("MSFT", "insider"): (),
    }
    portfolio_result = SimpleNamespace(
        portfolio_context=SimpleNamespace(
            account_equity=100000.0,
            total_margin_requirement=0.0,
            margin_model_profile="estimated_fidelity_like_conservative_v1",
            margin_model_version="v1",
        ),
        positions=(SimpleNamespace(ticker="AAPL"),),
    )
    rebalance_pipeline = _RebalancePipeline(
        recorder,
        SimpleNamespace(decisions=(SimpleNamespace(ticker="AAPL"),)),
    )
    trading_repository = _TradingRepository(recorder)
    dependencies = LiveIntradayRefreshDependencies(
        scope_loader=_ScopeLoader(recorder, ("AAPL", "MSFT")),
        baseline_loader=_BaselineLoader(
            recorder,
            {"AAPL": _baseline_snapshot(ticker="AAPL"), "MSFT": _baseline_snapshot(ticker="MSFT")},
        ),
        previous_snapshot_loader=_PreviousSnapshotLoader(
            recorder,
            {"AAPL": _previous_intraday(ticker="AAPL")},
        ),
        source_repository=_IntradaySourceRepository(recorder, source_rows),
        source_ingestion_service=refresh_service,
        portfolio_sync_workflow=_PortfolioSyncWorkflow(recorder, portfolio_result),
        news_alert_service=_NewsAlertService(
            recorder,
            (
                _NewsAlert(
                    ticker="AAPL",
                    dedupe_key="aapl-news-1",
                    metadata_json={"source_family": "events_news"},
                ),
                _NewsAlert(
                    ticker="AAPL",
                    dedupe_key="aapl-social-1",
                    alert_type="trump_update",
                    sentiment="negative",
                    metadata_json={"source_family": "social_macro"},
                ),
            ),
        ),
        rebalance_pipeline=rebalance_pipeline,
        trading_repository=trading_repository,
        request_context_loader=_RequestContextLoader(
            recorder,
            {
                "AAPL": SimpleNamespace(
                    selection_source="risk_manager",
                    strategy_id="relative_strength_rotation_v1",
                    strategy_version="v1",
                    expression_bucket_id="long_stock",
                    expression_bucket_version="v1",
                    trade_identity="tactical_stock_trade",
                    instrument_type="stock",
                    candidate_score=0.82,
                    target_weight=0.05,
                    allow_open_new=False,
                ),
                "MSFT": SimpleNamespace(
                    selection_source="manual_request",
                    strategy_id="earnings_reaction_v1",
                    strategy_version="v1",
                    expression_bucket_id="long_stock",
                    expression_bucket_version="v1",
                    trade_identity="tactical_stock_trade",
                    instrument_type="stock",
                    candidate_score=0.67,
                    target_weight=0.03,
                    allow_open_new=True,
                    manual_request_id="msft-request",
                    manual_request_mode="paper_trade_eligible",
                ),
            },
        ),
        existing_news_dedupe_key_loader=lambda tickers, decision_time: frozenset({"seen-news"}),
        candidate_context_loader=lambda tickers, decision_time: {"MSFT": ("MSFT",)},
        position_context_loader=lambda tickers, positions: {"AAPL": ("AAPL",)},
        theme_context_loader=lambda tickers, decision_time: {},
        macro_state_loader=lambda decision_time: None,
    )
    runtime = LiveIntradayRefreshRuntime(
        dependencies=dependencies,
        now=lambda: datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc),
    )
    return runtime, recorder, rebalance_pipeline, trading_repository, refresh_service


def test_live_intraday_refresh_runtime_runs_live_intraday_chain_in_dry_run_mode():
    runtime, recorder, rebalance_pipeline, trading_repository, refresh_service = _build_runtime()

    result = runtime.run()

    assert recorder.calls == [
        "load_scope",
        "refresh_sources",
        "load_baselines",
        "load_previous_intraday",
        "load_request_context",
        "portfolio_sync",
        "save_scan",
        "latest:AAPL:technical",
        "latest:AAPL:events_news",
        "latest:AAPL:social_macro",
        "latest:AAPL:insider",
        "save_snapshot:AAPL",
        "latest:MSFT:technical",
        "latest:MSFT:events_news",
        "latest:MSFT:social_macro",
        "latest:MSFT:insider",
        "save_snapshot:MSFT",
        "build_alerts",
        "save_alert:AAPL",
        "save_alert:AAPL",
        "rebalance",
    ]
    assert refresh_service.calls == [
        (
            ("AAPL", "MSFT"),
            "intraday_refresh",
            ("technical", "events_news", "social_macro", "option_chain"),
        )
    ]
    assert [request.ticker for request in rebalance_pipeline.last_requests] == ["AAPL", "MSFT"]
    assert rebalance_pipeline.last_requests[0].allow_open_new is False
    assert rebalance_pipeline.last_requests[1].allow_open_new is True
    assert rebalance_pipeline.last_requests[1].manual_request_id == "msft-request"
    assert rebalance_pipeline.last_requests[1].manual_request_mode == "paper_trade_eligible"
    assert rebalance_pipeline.last_requests[0].direct_company_negative_evidence is False
    assert rebalance_pipeline.last_requests[0].bearish_signal_sources == ()
    assert rebalance_pipeline.last_requests[0].metadata_json["social_policy_alert_count"] == 1
    assert rebalance_pipeline.last_requests[0].alerts[1]["source_family"] == "social_macro"
    assert result["status"] == "passed"
    assert result["phase"] == "intraday_refresh"
    assert result["summary"]["ticker_count"] == 2
    assert result["summary"]["news_alert_count"] == 2
    assert result["summary"]["intraday_rebalance_decision_count"] == 1
    assert result["execution"] == {
        "mode": "dry_run",
        "orders_submitted": 0,
        "option_orders_submitted": 0,
        "orders_skipped": 0,
        "orders_failed": 0,
        "skip_reasons": {},
    }
    assert trading_repository.saved_scan is not None
    assert len(trading_repository.saved_snapshots) == 2
    assert len(trading_repository.saved_alerts) == 2
    assert trading_repository.saved_snapshots[0].refreshed_signals_json["social_macro"]["policy_headwind_flag"] is True
    assert trading_repository.saved_snapshots[0].carried_forward_signals_json["insider"]["purchase_count_30d"] == 2
    assert trading_repository.saved_snapshots[0].source_freshness_json["insider"] == "carried_forward_from_baseline"


def test_live_intraday_refresh_runtime_requires_paper_execution_when_option_execution_enabled():
    runtime, _recorder, _rebalance_pipeline, _trading_repository, _refresh_service = _build_runtime()
    runtime.execute_paper_option_orders = True

    try:
        runtime.run()
    except ValueError as exc:
        assert str(exc) == "option_execution_requires_paper_order_execution"
    else:
        raise AssertionError("expected option execution policy validation to fail")


def test_live_intraday_refresh_runtime_reports_option_orders_separately_when_enabled():
    runtime, _recorder, rebalance_pipeline, _trading_repository, _refresh_service = _build_runtime()
    runtime.execute_paper_orders = True
    runtime.execute_paper_option_orders = True
    rebalance_pipeline.result = SimpleNamespace(
        decisions=(SimpleNamespace(ticker="AAPL"),),
        execution_summary={"orders_submitted": 1, "option_orders_submitted": 1},
    )

    result = runtime.run()

    assert result["execution"] == {
        "mode": "execute",
        "orders_submitted": 1,
        "option_orders_submitted": 1,
        "orders_skipped": 0,
        "orders_failed": 0,
        "skip_reasons": {},
    }


def test_live_intraday_refresh_runtime_passes_portfolio_risk_intent_into_rebalance_pipeline():
    runtime, _recorder, rebalance_pipeline, _trading_repository, _refresh_service = _build_runtime()
    runtime.dependencies = LiveIntradayRefreshDependencies(
        **{
            **runtime.dependencies.__dict__,
            "lookahead_helper": SimpleNamespace(
                build_intraday_portfolio_risk_intent=lambda **kwargs: PortfolioRiskIntentRecord.create(
                    decision_time=kwargs["decision_time"],
                    risk_window="1-5d",
                    aggregate_risk_state="macro_high_risk",
                )
            ),
        }
    )

    runtime.run()

    assert rebalance_pipeline.last_portfolio_risk_intent is not None
    assert rebalance_pipeline.last_portfolio_risk_intent.aggregate_risk_state == "macro_high_risk"


def test_live_intraday_refresh_runtime_passes_macro_risk_state_into_intraday_lookahead_helper():
    runtime, _recorder, rebalance_pipeline, _repository, _refresh_service = _build_runtime()
    runtime.dependencies = LiveIntradayRefreshDependencies(
        **{
            **runtime.dependencies.__dict__,
            "macro_state_loader": lambda decision_time: "high",
            "lookahead_helper": _MacroLookaheadHelper(),
        }
    )

    runtime.run()

    assert runtime.dependencies.lookahead_helper.received_macro_risk_state == "high"
    assert rebalance_pipeline.last_portfolio_risk_intent.aggregate_risk_state == "macro_high_risk"
    assert rebalance_pipeline.last_portfolio_risk_intent.hedge_actions[0].risk_source == "macro"


def test_live_intraday_refresh_runtime_persists_calendar_and_event_risk_context_from_new_intraday_events():
    runtime, _recorder, rebalance_pipeline, repository, _refresh_service = _build_runtime()
    captured_kwargs: list[dict[str, object]] = []
    macro_snapshot = SimpleNamespace(
        macro_snapshot_id="macro-preopen-1",
        regime="risk_off",
        risk_budget_multiplier=0.6,
        source_freshness={"global_context": {"status": "fresh"}},
    )
    runtime.dependencies = LiveIntradayRefreshDependencies(
        **{
            **runtime.dependencies.__dict__,
            "macro_snapshot_loader": lambda decision_time: macro_snapshot,
            "calendar_event_pipeline": CalendarEventPipeline(),
            "event_risk_pipeline": PortfolioEventRiskAssessmentPipeline(),
            "lookahead_helper": SimpleNamespace(
                build_intraday_portfolio_risk_intent=lambda **kwargs: (
                    captured_kwargs.append(kwargs)
                    or PortfolioRiskIntentRecord.create(
                        decision_time=kwargs["decision_time"],
                        risk_window="1-5d",
                        aggregate_risk_state="macro_high_risk",
                    )
                )
            ),
        }
    )

    runtime.run()

    assert repository.saved_macro_snapshots == []
    assert len(repository.saved_calendar_events) >= 1
    assert len(repository.saved_event_assessments) >= 1
    assert captured_kwargs[0]["macro_snapshot"].macro_snapshot_id == "macro-preopen-1"
    assert captured_kwargs[0]["macro_risk_state"] == "high"
    assert captured_kwargs[0]["event_assessments"][0].metadata_json["material_change"] is True
    assert "new_event" in captured_kwargs[0]["event_assessments"][0].metadata_json["material_change_fields"]
    assert rebalance_pipeline.last_portfolio_risk_intent.aggregate_risk_state == "macro_high_risk"


def test_intraday_helper_derives_sector_cluster_assessment_from_readthrough_alert():
    helper = LookaheadRiskWorkflowHelper()
    now = datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc)
    portfolio_context = SimpleNamespace(
        account_equity=100000.0,
        total_margin_requirement=0.0,
        margin_model_profile="estimated_fidelity_like_conservative_v1",
        margin_model_version="v1",
        positions=(
            SimpleNamespace(
                ticker="NVDA",
                trade_identity="tactical_stock_trade",
                sector="Semiconductors",
            ),
        ),
    )
    config = RiskConfigResolver().resolve(
        risk_appetite="balanced",
        portfolio_context=portfolio_context,
        macro_risk_budget_multiplier=1.0,
    )

    intent = helper.build_intraday_portfolio_risk_intent(
        rebalance_requests=(
            SimpleNamespace(
                ticker="NVDA",
                trade_identity="tactical_stock_trade",
                existing_position=True,
                allow_open_new=False,
                alerts=(
                    {
                        "alert_type": "earnings_readthrough",
                        "severity": "high",
                        "source_ticker": "AVGO",
                        "readthrough_source_ticker": "AVGO",
                        "affected_themes": ["ai_semis"],
                    },
                ),
                metadata_json={"sector": "Semiconductors"},
            ),
        ),
        portfolio_context=portfolio_context,
        config=config,
        decision_time=now,
        macro_risk_state=None,
    )

    assert intent.aggregate_risk_state == "event_cluster_risk"
    assert intent.hedge_actions[0].risk_source == "sector_event_cluster"
    assert intent.hedge_actions[0].target_underlier == "SMH"


def test_intraday_helper_keeps_same_ticker_themed_earnings_alert_on_own_event_path():
    helper = LookaheadRiskWorkflowHelper()
    now = datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc)
    portfolio_context = SimpleNamespace(
        account_equity=100000.0,
        total_margin_requirement=0.0,
        margin_model_profile="estimated_fidelity_like_conservative_v1",
        margin_model_version="v1",
        positions=(
            SimpleNamespace(
                ticker="NVDA",
                trade_identity="tactical_stock_trade",
                sector="Semiconductors",
            ),
        ),
    )
    config = RiskConfigResolver().resolve(
        risk_appetite="balanced",
        portfolio_context=portfolio_context,
        macro_risk_budget_multiplier=1.0,
    )

    intent = helper.build_intraday_portfolio_risk_intent(
        rebalance_requests=(
            SimpleNamespace(
                ticker="NVDA",
                trade_identity="tactical_stock_trade",
                existing_position=True,
                allow_open_new=False,
                alerts=(
                    {
                        "alert_type": "earnings_update",
                        "severity": "high",
                        "source_ticker": "NVDA",
                        "affected_themes": ["ai_semis"],
                    },
                ),
                metadata_json={"sector": "Semiconductors"},
            ),
        ),
        portfolio_context=portfolio_context,
        config=config,
        decision_time=now,
        macro_risk_state=None,
    )

    assert intent.aggregate_risk_state == "mixed_risk"
    assert intent.position_actions[0].risk_source == "own_event"
    assert intent.hedge_actions == ()


def test_intraday_helper_ignores_non_dict_alert_before_cluster_path():
    helper = LookaheadRiskWorkflowHelper()
    now = datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc)
    portfolio_context = SimpleNamespace(
        account_equity=100000.0,
        total_margin_requirement=0.0,
        margin_model_profile="estimated_fidelity_like_conservative_v1",
        margin_model_version="v1",
        positions=(),
    )
    config = RiskConfigResolver().resolve(
        risk_appetite="balanced",
        portfolio_context=portfolio_context,
        macro_risk_budget_multiplier=1.0,
    )

    intent = helper.build_intraday_portfolio_risk_intent(
        rebalance_requests=(
            SimpleNamespace(
                ticker="NVDA",
                trade_identity="tactical_stock_trade",
                existing_position=True,
                allow_open_new=False,
                alerts=("bad-alert-shape",),
                metadata_json={"sector": "Semiconductors"},
            ),
        ),
        portfolio_context=portfolio_context,
        config=config,
        decision_time=now,
        macro_risk_state=None,
    )

    assert intent.aggregate_risk_state == "risk_normalized"
    assert intent.position_actions == ()
    assert intent.hedge_actions == ()


def test_live_intraday_refresh_runtime_keeps_readthrough_and_theme_fields_on_rebalance_requests():
    runtime, recorder, rebalance_pipeline, _repository, _refresh_service = _build_runtime()

    class _LocalLoader:
        def __init__(self, name: str, result: dict[str, object]) -> None:
            self.name = name
            self.result = result

        def load_for_tickers(self, *, tickers: tuple[str, ...], decision_time: datetime) -> dict[str, object]:
            assert decision_time.tzinfo is not None
            recorder.record(self.name)
            return dict(self.result)

    class _LocalNewsAlertService:
        def __init__(self, alerts: tuple[object, ...]) -> None:
            self.alerts = alerts

        def build_alerts(
            self,
            *,
            source_items,
            existing_dedupe_keys,
            affected_positions_by_ticker,
            affected_candidates_by_ticker,
            affected_themes_by_ticker,
        ):
            assert {item.ticker for item in source_items} == {"AAPL"}
            assert existing_dedupe_keys == frozenset({"seen-news"})
            assert affected_positions_by_ticker["AAPL"] == ("AAPL",)
            assert affected_candidates_by_ticker["MSFT"] == ("MSFT",)
            assert affected_themes_by_ticker == {"NVDA": ("ai_semis",)}
            recorder.record("build_alerts")
            return self.alerts

    runtime.dependencies = LiveIntradayRefreshDependencies(
        **{
            **runtime.dependencies.__dict__,
            "scope_loader": _ScopeLoader(recorder, ("AAPL", "MSFT", "NVDA")),
            "baseline_loader": _LocalLoader(
                "load_baselines",
                {
                    "AAPL": _baseline_snapshot(ticker="AAPL"),
                    "MSFT": _baseline_snapshot(ticker="MSFT"),
                    "NVDA": _baseline_snapshot(ticker="NVDA", sector="Semiconductors"),
                },
            ),
            "previous_snapshot_loader": _LocalLoader(
                "load_previous_intraday",
                {
                    "AAPL": _previous_intraday(ticker="AAPL"),
                    "NVDA": _previous_intraday(ticker="NVDA"),
                },
            ),
            "source_repository": _IntradaySourceRepository(
                recorder,
                {
                    ("AAPL", "technical"): (_source_record(ticker="AAPL", family="technical", payload={"bars": [{"close": 104.0}]}),),
                    ("AAPL", "events_news"): (
                        _source_record(
                            ticker="AAPL",
                            family="events_news",
                            payload={
                                "event_news_item_id": "news-aapl-1",
                                "ticker": "AAPL",
                                "source_ticker": "AAPL",
                                "event_type": "earnings_update",
                                "direction": "positive",
                                "sentiment": "positive",
                                "importance": "high",
                                "headline": "AAPL guide raised",
                                "summary": "Raised guide",
                                "provider": "fixture",
                                "source_refs_json": [],
                                "dedupe_key": "aapl-news-1",
                                "metadata_json": {},
                            },
                        ),
                    ),
                    ("MSFT", "technical"): (_source_record(ticker="MSFT", family="technical", payload={"bars": [{"close": 98.0}]}),),
                    ("MSFT", "events_news"): (),
                    ("NVDA", "technical"): (_source_record(ticker="NVDA", family="technical", payload={"bars": [{"close": 121.0}]}),),
                    ("NVDA", "events_news"): (),
                },
            ),
            "request_context_loader": _LocalLoader(
                "load_request_context",
                {
                    "AAPL": SimpleNamespace(
                        selection_source="risk_manager",
                        strategy_id="relative_strength_rotation_v1",
                        strategy_version="v1",
                        expression_bucket_id="long_stock",
                        expression_bucket_version="v1",
                        trade_identity="tactical_stock_trade",
                        instrument_type="stock",
                        candidate_score=0.82,
                        target_weight=0.05,
                        allow_open_new=False,
                    ),
                    "MSFT": SimpleNamespace(
                        selection_source="manual_request",
                        strategy_id="earnings_reaction_v1",
                        strategy_version="v1",
                        expression_bucket_id="long_stock",
                        expression_bucket_version="v1",
                        trade_identity="tactical_stock_trade",
                        instrument_type="stock",
                        candidate_score=0.67,
                        target_weight=0.03,
                        allow_open_new=True,
                        manual_request_id="msft-request",
                        manual_request_mode="paper_trade_eligible",
                    ),
                    "NVDA": SimpleNamespace(
                        selection_source="manual_request",
                        strategy_id="semis_readthrough_v1",
                        strategy_version="v1",
                        expression_bucket_id="long_stock",
                        expression_bucket_version="v1",
                        trade_identity="tactical_stock_trade",
                        instrument_type="stock",
                        candidate_score=0.74,
                        target_weight=0.04,
                        allow_open_new=True,
                        manual_request_id="nvda-request",
                        manual_request_mode="review_only",
                    ),
                },
            ),
            "candidate_context_loader": lambda tickers, decision_time: {"MSFT": ("MSFT",), "NVDA": ("NVDA",)},
            "position_context_loader": lambda tickers, positions: {"AAPL": ("AAPL",)},
            "theme_context_loader": lambda tickers, decision_time: {"NVDA": ("ai_semis",)},
            "news_alert_service": _LocalNewsAlertService(
                (
                    _NewsAlert(ticker="AAPL", dedupe_key="aapl-news-1"),
                    _NewsAlert(
                        ticker="NVDA",
                        dedupe_key="nvda-news-1",
                        alert_type="guidance_update",
                        severity="high",
                        sentiment="positive",
                        headline="NVDA raised after AVGO readthrough",
                        summary="Semiconductor readthrough from AVGO",
                        source_ticker="AVGO",
                        affected_themes=("ai_semis",),
                        readthrough_source_ticker="AVGO",
                    ),
                ),
            ),
        }
    )

    runtime.run()

    request = next(item for item in rebalance_pipeline.last_requests if item.ticker == "NVDA")
    assert request.metadata_json["sector"] == "Semiconductors"
    assert request.manual_request_id == "nvda-request"
    assert request.manual_request_mode == "review_only"
    assert request.alerts[0]["affected_themes"] == ["ai_semis"]
    assert request.alerts[0]["source_ticker"] == "AVGO"
    assert request.alerts[0]["readthrough_source_ticker"] == "AVGO"


def test_live_intraday_refresh_runtime_refreshes_open_option_position_marks_and_greeks():
    recorder = _CallRecorder()
    decision_time = datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc)
    class _LocalLoader:
        def __init__(self, name: str, result: dict[str, object]) -> None:
            self.name = name
            self.result = result

        def load_for_tickers(self, *, tickers: tuple[str, ...], decision_time: datetime) -> dict[str, object]:
            assert decision_time.tzinfo is not None
            recorder.record(self.name)
            return dict(self.result)

    class _LocalNewsAlertService:
        def build_alerts(
            self,
            *,
            source_items,
            existing_dedupe_keys,
            affected_positions_by_ticker,
            affected_candidates_by_ticker,
            affected_themes_by_ticker,
        ):
            recorder.record("build_alerts")
            return ()

    source_rows = {
        ("QQQ", "technical"): (_source_record(ticker="QQQ", family="technical", payload={"bars": [{"close": 500.0}]}),),
        ("QQQ", "option_chain"): (
            _source_record(
                ticker="QQQ",
                family="option_chain",
                payload={
                    "contracts": [
                        {
                            "option_type": "put",
                            "strike": 475.0,
                            "expiry": "2026-06-09",
                            "delta": -0.31,
                            "gamma": 0.02,
                            "theta": -0.03,
                            "vega": 0.07,
                            "chosen_price": 3.2,
                            "mid": 3.2,
                        }
                    ]
                },
            ),
        ),
        ("QQQ", "events_news"): (),
    }
    portfolio_result = SimpleNamespace(
        portfolio_context=SimpleNamespace(
            account_equity=100000.0,
            total_margin_requirement=0.0,
            margin_model_profile="estimated_fidelity_like_conservative_v1",
            margin_model_version="v1",
            positions=(
                SimpleNamespace(
                    ticker="QQQ",
                    trade_identity="risk_hedge_overlay",
                    quantity=1.0,
                    market_value=320.0,
                    sector="Technology",
                ),
            ),
        ),
        positions=(),
    )
    rebalance_pipeline = _RebalancePipeline(
        recorder,
        SimpleNamespace(decisions=(SimpleNamespace(ticker="QQQ"),)),
    )
    trading_repository = _TradingRepository(recorder)
    runtime = LiveIntradayRefreshRuntime(
        dependencies=LiveIntradayRefreshDependencies(
            scope_loader=_ScopeLoader(recorder, ("QQQ",)),
            baseline_loader=_LocalLoader("load_baselines", {"QQQ": _baseline_snapshot(ticker="QQQ", sector="Technology")}),
            previous_snapshot_loader=_LocalLoader("load_previous_intraday", {}),
            request_context_loader=_LocalLoader(
                "load_request_context",
                {
                    "QQQ": SimpleNamespace(
                        selection_source="risk_manager",
                        strategy_id="risk_manager_hedge_overlay_v1",
                        strategy_version="v1",
                        expression_bucket_id="defined_risk_directional_option",
                        expression_bucket_version="v1",
                        trade_identity="risk_hedge_overlay",
                        instrument_type="option",
                        candidate_score=0.0,
                        target_weight=0.0,
                        allow_open_new=False,
                        metadata_json={
                            "paper_option_position_id": "qqq-open-position",
                            "option_strategy_type": "long_put",
                            "event_through_expiry": True,
                            "option_strategy": {
                                "option_strategy_type": "long_put",
                                "underlying_price": 500.0,
                                "net_debit_or_credit": 3.2,
                            },
                        },
                    )
                },
            ),
            source_repository=_IntradaySourceRepository(recorder, source_rows),
            portfolio_sync_workflow=_PortfolioSyncWorkflow(recorder, portfolio_result),
            news_alert_service=_LocalNewsAlertService(),
            rebalance_pipeline=rebalance_pipeline,
            trading_repository=trading_repository,
            existing_news_dedupe_key_loader=lambda tickers, decision_time: frozenset(),
            candidate_context_loader=lambda tickers, decision_time: {},
            position_context_loader=lambda tickers, positions: {"QQQ": ("QQQ",)},
            theme_context_loader=lambda tickers, decision_time: {},
            macro_state_loader=lambda decision_time: None,
        ),
        now=lambda: decision_time,
    )

    runtime.run()

    assert "latest:QQQ:option_chain" in recorder.calls
    assert len(trading_repository.saved_snapshots) == 1
    snapshot = trading_repository.saved_snapshots[0]
    assert snapshot.refreshed_signals_json["option"]["mark_price"] == 320.0
    assert snapshot.refreshed_signals_json["option"]["delta"] == -0.31
    assert snapshot.source_freshness_json["option_chain"] == "fresh"
    request = rebalance_pipeline.last_requests[0]
    assert request.instrument_type == "option"
    assert request.existing_position is True
    assert request.current_price == 320.0
    assert request.signal_freshness["option_chain"] == "fresh"
    assert request.metadata_json["paper_option_position_id"] == "qqq-open-position"
    assert request.metadata_json["option_strategy"]["option_strategy_type"] == "long_put"
    assert request.metadata_json["option_mark_price"] == 320.0


def test_run_live_intraday_refresh_once_builds_default_dependencies_when_not_injected(monkeypatch):
    runtime, _recorder, _pipeline, _repository, _refresh_service = _build_runtime()

    monkeypatch.setattr(
        "src.trading.runtime.intraday_refresh.build_live_intraday_refresh_dependencies",
        lambda _session: runtime.dependencies,
    )

    result = run_live_intraday_refresh_once(now=lambda: datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc))

    assert result["status"] == "passed"
    assert result["phase"] == "intraday_refresh"


def test_run_live_intraday_refresh_once_builds_default_dependencies_for_option_execution(monkeypatch):
    runtime, _recorder, _pipeline, _repository, _refresh_service = _build_runtime()

    monkeypatch.setattr(
        "src.trading.runtime.intraday_refresh.build_live_intraday_refresh_dependencies",
        lambda _session: runtime.dependencies,
    )

    result = run_live_intraday_refresh_once(
        now=lambda: datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc),
        execute_paper_orders=True,
        execute_paper_option_orders=True,
    )

    assert result["status"] == "passed"
    assert result["execution"]["mode"] == "execute"


def test_runtime_dispatch_routes_intraday_refresh_to_live_runtime():
    from src.trading.runtime import dispatch
    from src.trading.runtime.intraday_refresh import run_live_intraday_refresh_once as live_handler

    assert dispatch.JOB_PHASE_HANDLERS["intraday_refresh"] is live_handler
    assert callable(get_job_phase_handler("intraday_refresh"))


def test_build_live_intraday_refresh_dependencies_injects_option_broker_into_rebalance_pipeline(monkeypatch):
    captured: dict[str, object] = {}

    class _Repo:
        pass

    class _SourceRepo:
        pass

    class _Broker:
        pass

    class _OptionBroker:
        def __init__(self, **kwargs):
            captured["option_broker_kwargs"] = kwargs

    class _PromptRegistry:
        @staticmethod
        def get_default():
            return "prompt-registry"

    class _PortfolioSyncWorkflow:
        def __init__(self, **kwargs):
            captured["portfolio_sync_kwargs"] = kwargs

    class _RebalancePipeline:
        def __init__(self, **kwargs):
            captured["rebalance_kwargs"] = kwargs

    monkeypatch.setattr("src.agents.prompt_registry.PromptRegistry", _PromptRegistry)
    monkeypatch.setattr("src.agents.trading._default_agent_runner", "runner")
    monkeypatch.setattr("src.trading.brokers.paper_stock.PaperStockBroker", lambda: _Broker())
    monkeypatch.setattr("src.trading.brokers.paper_option.PaperOptionBroker", _OptionBroker)
    monkeypatch.setattr("src.trading.repositories.source_sqlalchemy.SQLAlchemySignalSourceRepository", lambda session: _SourceRepo())
    monkeypatch.setattr("src.trading.repositories.sqlalchemy.SqlAlchemyTradingRepository", lambda session: _Repo())
    monkeypatch.setattr("src.trading.runtime.lookahead_risk.LookaheadRiskWorkflowHelper", lambda **kwargs: "lookahead-helper")
    monkeypatch.setattr("src.trading.risk.PortfolioHedgePlanner", lambda: "hedge-planner")
    monkeypatch.setattr("src.trading.workflows.portfolio_sync.BrokerPortfolioSyncWorkflow", _PortfolioSyncWorkflow)
    monkeypatch.setattr("src.trading.runtime.intraday_refresh_dependencies.IntradayRebalancePipeline", _RebalancePipeline)

    dependencies = build_live_intraday_refresh_dependencies(session=object())

    assert isinstance(dependencies, LiveIntradayRefreshDependencies)
    assert captured["portfolio_sync_kwargs"]["broker"].__class__ is _Broker
    assert captured["rebalance_kwargs"]["broker"].__class__ is _Broker
    assert captured["rebalance_kwargs"]["option_broker"].__class__ is _OptionBroker
    assert captured["option_broker_kwargs"]["trading_base_url"] == "https://paper-api.alpaca.markets"
