from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.trading import runtime
from src.trading.runtime_live import LivePreopenDependencies, LivePreopenRuntime, run_live_preopen_once


class _CallRecorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def record(self, name: str) -> None:
        self.calls.append(name)


class _UniverseFilterLoader:
    def __init__(self, recorder: _CallRecorder, config: object) -> None:
        self.recorder = recorder
        self.config = config

    def load_active(self) -> object:
        self.recorder.record("load_universe_filter")
        return self.config


class _ManualRequestLoader:
    def __init__(self, recorder: _CallRecorder, requests: tuple[object, ...]) -> None:
        self.recorder = recorder
        self.requests = requests

    def load_active(self) -> tuple[object, ...]:
        self.recorder.record("load_manual_requests")
        return self.requests


class _UniverseScanPipeline:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(self, *, config: object, decision_time: datetime, manual_requests: tuple[object, ...]) -> object:
        assert config is not None
        assert decision_time.tzinfo is not None
        assert isinstance(manual_requests, tuple)
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
        assert snapshots
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
        assert candidates
        assert classifications
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
        assert candidates
        assert classifications
        assert risk_decisions
        assert decision_time.tzinfo is not None
        self.recorder.record("trading_decision")
        return self.result


class _PaperExecutionWorkflow:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(
        self,
        *,
        trading_decisions: tuple[object, ...],
        risk_decisions: tuple[object, ...],
        trade_date: datetime,
    ) -> object:
        assert trading_decisions
        assert risk_decisions
        assert trade_date.tzinfo is not None
        self.recorder.record("paper_execution")
        return self.result


def _build_runtime(*, execute_paper_orders: bool) -> tuple[LivePreopenRuntime, _CallRecorder]:
    recorder = _CallRecorder()
    universe_result = SimpleNamespace(included_symbols=("AAPL", "MSFT"))
    strategy_result = SimpleNamespace(
        candidates=(SimpleNamespace(ticker="AAPL"),),
        classifications=(SimpleNamespace(ticker="AAPL"),),
    )
    portfolio_result = SimpleNamespace(portfolio_context=SimpleNamespace(account_equity=100000.0))
    risk_result = SimpleNamespace(risk_decisions=(SimpleNamespace(ticker="AAPL"),))
    decision_result = SimpleNamespace(decisions=(SimpleNamespace(ticker="AAPL", decision="enter_long"),))
    execution_result = SimpleNamespace(paper_orders=(SimpleNamespace(ticker="AAPL"),))
    dependencies = LivePreopenDependencies(
        universe_filter_loader=_UniverseFilterLoader(
            recorder,
            SimpleNamespace(profile_name="default"),
        ),
        manual_request_loader=_ManualRequestLoader(recorder, (SimpleNamespace(ticker="NVDA"),)),
        universe_scan_pipeline=_UniverseScanPipeline(recorder, universe_result),
        signal_pipeline=_SignalPipeline(recorder, (SimpleNamespace(ticker="AAPL"),)),
        strategy_pipeline=_StrategyPipeline(recorder, strategy_result),
        portfolio_sync_workflow=_PortfolioSyncWorkflow(recorder, portfolio_result),
        risk_workflow=_RiskWorkflow(recorder, risk_result),
        trading_decision_pipeline=_TradingDecisionPipeline(recorder, decision_result),
        paper_execution_workflow=_PaperExecutionWorkflow(recorder, execution_result),
    )
    runtime = LivePreopenRuntime(
        dependencies=dependencies,
        now=lambda: datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc),
        execute_paper_orders=execute_paper_orders,
    )
    return runtime, recorder


def test_live_preopen_runtime_runs_morning_chain_without_execution_by_default():
    runtime, recorder = _build_runtime(execute_paper_orders=False)

    result = runtime.run()

    assert recorder.calls == [
        "load_universe_filter",
        "load_manual_requests",
        "universe_scan",
        "signal_snapshot",
        "strategy_scoring",
        "portfolio_sync",
        "risk",
        "trading_decision",
    ]
    assert result["status"] == "passed"
    assert result["phase"] == "preopen"
    assert result["execution"]["mode"] == "dry_run"
    assert result["execution"]["orders_submitted"] == 0


def test_live_preopen_runtime_executes_paper_orders_only_when_enabled():
    runtime, recorder = _build_runtime(execute_paper_orders=True)

    result = runtime.run()

    assert recorder.calls[-1] == "paper_execution"
    assert result["execution"]["mode"] == "execute"
    assert result["execution"]["orders_submitted"] == 1


def test_scheduler_preopen_phase_delegates_to_live_runtime(monkeypatch):
    expected = {"status": "passed", "phase": "preopen", "execution": {"mode": "dry_run", "orders_submitted": 0}}

    def _fake_live_preopen() -> dict[str, object]:
        return expected

    monkeypatch.setattr(runtime, "run_live_preopen_once", _fake_live_preopen)

    result = runtime.run_job_phase("preopen")

    assert result is expected


def test_run_live_preopen_once_builds_default_dependencies_when_not_injected(monkeypatch):
    runtime_instance, _recorder = _build_runtime(execute_paper_orders=False)

    monkeypatch.setattr(
        "src.trading.runtime_live.build_live_preopen_dependencies",
        lambda _session: runtime_instance.dependencies,
    )

    result = run_live_preopen_once(now=lambda: datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc))

    assert result["status"] == "passed"
    assert result["execution"]["mode"] == "dry_run"
