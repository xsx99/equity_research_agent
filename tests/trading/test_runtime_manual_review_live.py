from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from src.trading.manual_review.requests import ManualTickerRequest
from src.trading.runtime.dispatch import get_job_phase_handler
from src.trading.runtime.manual_review import (
    LiveManualReviewDependencies,
    LiveManualReviewRuntime,
    run_live_manual_review_once,
)
from src.trading.runtime.support import build_execution_report
from src.trading.data_sources.universe import UniverseFilterConfig


class _CallRecorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def record(self, name: str) -> None:
        self.calls.append(name)


class _UniverseFilterLoader:
    def __init__(self, recorder: _CallRecorder, config: UniverseFilterConfig) -> None:
        self.recorder = recorder
        self.config = config

    def load_active(self) -> UniverseFilterConfig:
        self.recorder.record("load_universe_filter")
        return self.config


class _ManualRequestLoader:
    def __init__(self, recorder: _CallRecorder, requests: tuple[ManualTickerRequest, ...]) -> None:
        self.recorder = recorder
        self.requests = requests

    def load_active(self) -> tuple[ManualTickerRequest, ...]:
        self.recorder.record("load_manual_requests")
        return self.requests


class _UniverseScanPipeline:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(self, *, config: UniverseFilterConfig, decision_time: datetime, manual_requests: tuple[object, ...]) -> object:
        assert config.manual_include == ()
        assert tuple(request.ticker for request in manual_requests) == ("MSFT", "NVDA")
        assert decision_time.tzinfo is not None
        self.recorder.record("universe_scan")
        return self.result


class _SignalPipeline:
    def __init__(self, recorder: _CallRecorder, snapshots: tuple[object, ...]) -> None:
        self.recorder = recorder
        self.snapshots = snapshots

    def build_pre_open_snapshots(self, *, universe_result: object, decision_time: datetime) -> tuple[object, ...]:
        assert universe_result is not None
        assert decision_time.tzinfo is not None
        self.recorder.record("signal_snapshot")
        return self.snapshots


class _StrategyPipeline:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(self, *, snapshots: tuple[object, ...], decision_time: datetime) -> object:
        assert [snapshot.ticker for snapshot in snapshots] == ["MSFT", "NVDA"]
        assert decision_time.tzinfo is not None
        self.recorder.record("strategy_scoring")
        return self.result


class _PortfolioSyncWorkflow:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(self, *, as_of: datetime) -> object:
        assert as_of.tzinfo is not None
        self.recorder.record("portfolio_sync")
        return self.result


class _RiskWorkflow:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(
        self,
        *,
        candidates: tuple[object, ...],
        classifications: tuple[object, ...],
        portfolio_context: object,
        decision_time: datetime,
    ) -> object:
        assert len(candidates) == 2
        assert len(classifications) == 2
        assert portfolio_context is not None
        assert decision_time.tzinfo is not None
        self.recorder.record("risk")
        return self.result


class _TradingDecisionPipeline:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(
        self,
        *,
        candidates: tuple[object, ...],
        classifications: tuple[object, ...],
        risk_decisions: tuple[object, ...],
        decision_time: datetime,
    ) -> object:
        assert len(candidates) == 2
        assert len(classifications) == 2
        assert len(risk_decisions) == 2
        assert decision_time.tzinfo is not None
        self.recorder.record("trading_decision")
        return self.result


def _manual_request(*, ticker: str, mode: str) -> ManualTickerRequest:
    now = datetime(2026, 6, 4, 13, 15, tzinfo=timezone.utc)
    return ManualTickerRequest(
        request_id=f"{ticker.lower()}-request",
        ticker=ticker,
        reason=f"review {ticker}",
        mode=mode,
        status="active",
        created_at=now,
    )


def _build_runtime() -> tuple[LiveManualReviewRuntime, _CallRecorder]:
    recorder = _CallRecorder()
    requests = (
        _manual_request(ticker="MSFT", mode="review_only"),
        _manual_request(ticker="NVDA", mode="paper_trade_eligible"),
    )
    universe_result = SimpleNamespace(included_symbols=("MSFT", "NVDA"))
    snapshots = (
        SimpleNamespace(ticker="MSFT"),
        SimpleNamespace(ticker="NVDA"),
    )
    strategy_result = SimpleNamespace(
        candidates=(SimpleNamespace(ticker="MSFT"), SimpleNamespace(ticker="NVDA")),
        classifications=(SimpleNamespace(ticker="MSFT"), SimpleNamespace(ticker="NVDA")),
    )
    portfolio_result = SimpleNamespace(portfolio_context=SimpleNamespace(account_equity=100000.0))
    risk_result = SimpleNamespace(risk_decisions=(SimpleNamespace(ticker="MSFT"), SimpleNamespace(ticker="NVDA")))
    decision_result = SimpleNamespace(
        decisions=(
            SimpleNamespace(ticker="MSFT", metadata_json={"paper_trade_authorized": False}),
            SimpleNamespace(ticker="NVDA", metadata_json={"paper_trade_authorized": True}),
        )
    )
    dependencies = LiveManualReviewDependencies(
        universe_filter_loader=_UniverseFilterLoader(
            recorder,
            UniverseFilterConfig(manual_include=("AAPL",), excluded_sectors=("Financials",)),
        ),
        manual_request_loader=_ManualRequestLoader(recorder, requests),
        universe_scan_pipeline=_UniverseScanPipeline(recorder, universe_result),
        signal_pipeline=_SignalPipeline(recorder, snapshots),
        strategy_pipeline=_StrategyPipeline(recorder, strategy_result),
        portfolio_sync_workflow=_PortfolioSyncWorkflow(recorder, portfolio_result),
        risk_workflow=_RiskWorkflow(recorder, risk_result),
        trading_decision_pipeline=_TradingDecisionPipeline(recorder, decision_result),
    )
    runtime = LiveManualReviewRuntime(
        dependencies=dependencies,
        now=lambda: datetime(2026, 6, 4, 13, 15, tzinfo=timezone.utc),
    )
    return runtime, recorder


def test_live_manual_review_runtime_runs_request_scoped_chain_in_dry_run_mode():
    runtime, recorder = _build_runtime()

    result = runtime.run()

    assert recorder.calls == [
        "load_manual_requests",
        "load_universe_filter",
        "universe_scan",
        "signal_snapshot",
        "strategy_scoring",
        "portfolio_sync",
        "risk",
        "trading_decision",
    ]
    assert result["status"] == "passed"
    assert result["phase"] == "manual_review"
    assert result["summary"]["manual_request_count"] == 2
    assert result["summary"]["review_only_request_count"] == 1
    assert result["summary"]["paper_trade_eligible_request_count"] == 1
    assert result["execution"] == build_execution_report(mode="dry_run", orders_submitted=0)


def test_run_live_manual_review_once_builds_default_dependencies_when_not_injected(monkeypatch):
    runtime, _recorder = _build_runtime()

    monkeypatch.setattr(
        "src.trading.runtime.manual_review.build_live_manual_review_dependencies",
        lambda _session: runtime.dependencies,
    )

    result = run_live_manual_review_once(now=lambda: datetime(2026, 6, 4, 13, 15, tzinfo=timezone.utc))

    assert result["status"] == "passed"
    assert result["phase"] == "manual_review"


def test_runtime_dispatch_routes_manual_review_to_live_runtime():
    from src.trading.runtime.manual_review import run_live_manual_review_once as live_handler

    assert get_job_phase_handler("manual_review") is live_handler
