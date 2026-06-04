from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from src.trading.intraday.signals import IntradaySignalScanRecord, IntradaySignalSnapshotRecord
from src.trading.runtime_dispatch import get_job_phase_handler
from src.trading.runtime_intraday_live import (
    LiveIntradayRefreshDependencies,
    LiveIntradayRefreshRuntime,
    run_live_intraday_refresh_once,
)
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


class _NewsAlertService:
    def __init__(self, recorder: _CallRecorder, alerts: tuple[object, ...]) -> None:
        self.recorder = recorder
        self.alerts = alerts

    def build_alerts(
        self,
        *,
        event_items,
        existing_dedupe_keys,
        affected_positions_by_ticker,
        affected_candidates_by_ticker,
        affected_themes_by_ticker,
    ):
        assert {item.ticker for item in event_items} == {"AAPL"}
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

    def run(
        self,
        *,
        rebalance_requests: tuple[object, ...],
        portfolio_context: object,
        risk_appetite: str,
        trade_date: datetime | None = None,
        execute_approved: bool = False,
    ) -> object:
        assert portfolio_context is not None
        assert risk_appetite == "balanced"
        assert trade_date is None
        assert execute_approved is False
        self.last_requests = rebalance_requests
        self.recorder.record("rebalance")
        return self.result


class _TradingRepository:
    def __init__(self, recorder: _CallRecorder) -> None:
        self.recorder = recorder
        self.saved_scan = None
        self.saved_snapshots: list[IntradaySignalSnapshotRecord] = []
        self.saved_alerts: list[object] = []

    def save_intraday_signal_scan(self, scan: IntradaySignalScanRecord) -> None:
        self.recorder.record("save_scan")
        self.saved_scan = scan

    def save_intraday_signal_snapshot(self, snapshot: IntradaySignalSnapshotRecord) -> None:
        self.recorder.record(f"save_snapshot:{snapshot.ticker}")
        self.saved_snapshots.append(snapshot)

    def save_news_alert(self, alert: object) -> None:
        self.recorder.record(f"save_alert:{alert.ticker}")
        self.saved_alerts.append(alert)


@dataclass(frozen=True)
class _NewsAlert:
    ticker: str
    dedupe_key: str


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


def _baseline_snapshot(*, ticker: str) -> SignalSnapshotResult:
    now = datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc)
    return SignalSnapshotResult(
        signal_snapshot_id=f"{ticker}-baseline",
        ticker=ticker,
        snapshot_type="pre_open",
        decision_time=now,
        available_for_decision_at=now,
        max_input_available_for_decision_at=now,
        signal_json={
            "technical": {"last_price": 100.0, "atr_pct": 0.02, "dollar_volume": 50_000_000.0},
            "fundamental": {"market_cap": 1_000_000_000},
        },
        source_freshness_json={"technical": "fresh", "fundamental": "fresh"},
        missing_signals_json=[],
        stale_signals_json=[],
        source_record_refs_json=[],
        source_available_times_json={},
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


def _build_runtime() -> tuple[LiveIntradayRefreshRuntime, _CallRecorder, _RebalancePipeline, _TradingRepository]:
    recorder = _CallRecorder()
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
        ("MSFT", "technical"): (_source_record(ticker="MSFT", family="technical", payload={"bars": [{"close": 98.0}]}),),
        ("MSFT", "events_news"): (),
    }
    portfolio_result = SimpleNamespace(
        portfolio_context=SimpleNamespace(account_equity=100000.0),
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
        portfolio_sync_workflow=_PortfolioSyncWorkflow(recorder, portfolio_result),
        news_alert_service=_NewsAlertService(recorder, (_NewsAlert(ticker="AAPL", dedupe_key="aapl-news-1"),)),
        rebalance_pipeline=rebalance_pipeline,
        trading_repository=trading_repository,
        request_context_loader=_RequestContextLoader(
            recorder,
            {
                "AAPL": SimpleNamespace(
                    selection_source="portfolio",
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
                ),
            },
        ),
        existing_news_dedupe_key_loader=lambda tickers, decision_time: frozenset({"seen-news"}),
        candidate_context_loader=lambda tickers, decision_time: {"MSFT": ("MSFT",)},
        position_context_loader=lambda tickers, positions: {"AAPL": ("AAPL",)},
        theme_context_loader=lambda tickers, decision_time: {},
    )
    runtime = LiveIntradayRefreshRuntime(
        dependencies=dependencies,
        now=lambda: datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc),
    )
    return runtime, recorder, rebalance_pipeline, trading_repository


def test_live_intraday_refresh_runtime_runs_live_intraday_chain_in_dry_run_mode():
    runtime, recorder, rebalance_pipeline, trading_repository = _build_runtime()

    result = runtime.run()

    assert recorder.calls == [
        "load_scope",
        "load_baselines",
        "load_previous_intraday",
        "load_request_context",
        "portfolio_sync",
        "save_scan",
        "latest:AAPL:technical",
        "save_snapshot:AAPL",
        "latest:MSFT:technical",
        "save_snapshot:MSFT",
        "latest:AAPL:events_news",
        "latest:MSFT:events_news",
        "build_alerts",
        "save_alert:AAPL",
        "rebalance",
    ]
    assert [request.ticker for request in rebalance_pipeline.last_requests] == ["AAPL", "MSFT"]
    assert rebalance_pipeline.last_requests[0].allow_open_new is False
    assert rebalance_pipeline.last_requests[1].allow_open_new is True
    assert result["status"] == "passed"
    assert result["phase"] == "intraday_refresh"
    assert result["summary"]["ticker_count"] == 2
    assert result["summary"]["news_alert_count"] == 1
    assert result["summary"]["intraday_rebalance_decision_count"] == 1
    assert result["execution"] == {"mode": "dry_run", "orders_submitted": 0}
    assert trading_repository.saved_scan is not None
    assert len(trading_repository.saved_snapshots) == 2
    assert len(trading_repository.saved_alerts) == 1


def test_run_live_intraday_refresh_once_builds_default_dependencies_when_not_injected(monkeypatch):
    runtime, _recorder, _pipeline, _repository = _build_runtime()

    monkeypatch.setattr(
        "src.trading.runtime_intraday_live.build_live_intraday_refresh_dependencies",
        lambda _session: runtime.dependencies,
    )

    result = run_live_intraday_refresh_once(now=lambda: datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc))

    assert result["status"] == "passed"
    assert result["phase"] == "intraday_refresh"


def test_runtime_dispatch_routes_intraday_refresh_to_live_runtime():
    from src.trading.runtime_intraday_live import run_live_intraday_refresh_once as live_handler

    assert get_job_phase_handler("intraday_refresh") is live_handler
