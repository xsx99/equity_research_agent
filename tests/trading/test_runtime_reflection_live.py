from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.trading.post_close.reflection import ReflectionPipelineRequest
from src.trading.runtime.dispatch import get_job_phase_handler
from src.trading.runtime.reflection import (
    LiveReflectionDependencies,
    LiveReflectionRequestLoader,
    LiveReflectionRuntime,
    ReflectionLoadResult,
    run_live_reflection_once,
)


class _Repository:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def load_reflection_inputs(self, *, trade_date: date) -> dict[str, object]:
        assert trade_date == date(2026, 6, 4)
        return dict(self.payload)


def test_live_reflection_request_loader_assembles_same_day_option_and_hedge_artifacts():
    decision_time = datetime(2026, 6, 4, 22, 0, tzinfo=timezone.utc)
    payload = {
        "portfolio_outcome": {"account_equity": 100250.0, "day_pnl": 250.0},
        "morning_macro_snapshot": {"regime": "neutral"},
        "strategy_candidates": ({"ticker": "AAPL"},),
        "manual_ticker_requests": ({"ticker": "MSFT", "mode": "review_only"},),
        "trading_decisions": ({"ticker": "AAPL", "decision": "enter_long"},),
        "rejected_decisions": ({"ticker": "MSFT", "decision": "no_trade"},),
        "intraday_news_alerts": ({"ticker": "AAPL", "severity": "high"},),
        "intraday_rebalance_decisions": ({"ticker": "AAPL", "action": "exit"},),
        "paper_orders": ({"ticker": "AAPL", "action": "buy"},),
        "paper_executions": ({"ticker": "AAPL", "fill_price": 101.0},),
        "risk_snapshots": ({"account_equity": 100250.0},),
        "risk_factor_exposures": ({"factor_type": "sector", "factor_value": "technology"},),
        "portfolio_snapshots": ({"account_equity": 100250.0},),
        "candidate_outcome_evaluations": ({"ticker": "AAPL", "alpha": 0.03},),
        "benchmark_peer_returns": {"QQQ": 0.01},
        "paper_option_decisions": ({"ticker": "AAPL", "option_strategy_type": "long_call"},),
        "paper_option_positions": ({"ticker": "AAPL", "quantity": 1},),
        "option_risk_snapshots": ({"ticker": "AAPL", "risk_status": "approved"},),
        "worst_case_assignment_snapshots": (),
        "risk_hedge_overlays": (
            {
                "ticker": "QQQ",
                "action": "adjust_hedge",
                "option_strategy_type": "long_put",
                "protected_notional": 15000.0,
            },
        ),
        "hedge_effectiveness": {
            "overlay_count": 1,
            "assignment_overlay_count": 0,
            "protected_notional": 15000.0,
        },
        "learning_factors_used": ({"factor_key": "lf_2026_06_03_01"},),
    }
    loader = LiveReflectionRequestLoader(repository=_Repository(payload))

    result = loader.load(trade_date=date(2026, 6, 4), decision_time=decision_time)

    assert result.status == "ready"
    assert isinstance(result.request, ReflectionPipelineRequest)
    assert result.request is not None
    assert result.request.portfolio_outcome["day_pnl"] == 250.0
    assert result.request.morning_macro_snapshot["regime"] == "neutral"
    assert result.request.trading_decisions[0]["ticker"] == "AAPL"
    assert result.request.intraday_news_alerts[0]["severity"] == "high"
    assert result.request.candidate_outcome_evaluations[0]["alpha"] == 0.03
    assert result.request.risk_hedge_overlays[0]["ticker"] == "QQQ"
    assert result.request.hedge_effectiveness["protected_notional"] == 15000.0
    assert result.request.learning_factors_used[0]["factor_key"] == "lf_2026_06_03_01"


def test_live_reflection_request_loader_returns_skipped_when_portfolio_outcome_missing():
    loader = LiveReflectionRequestLoader(repository=_Repository({"portfolio_outcome": None, "portfolio_snapshots": ()}))

    result = loader.load(
        trade_date=date(2026, 6, 4),
        decision_time=datetime(2026, 6, 4, 22, 0, tzinfo=timezone.utc),
    )

    assert result.status == "skipped"
    assert result.request is None
    assert "portfolio_outcome_missing" in result.reasons


@dataclass(frozen=True)
class _RequestLoader:
    result: ReflectionLoadResult

    def load(self, *, trade_date: date, decision_time: datetime) -> ReflectionLoadResult:
        assert trade_date == date(2026, 6, 4)
        assert decision_time.tzinfo is not None
        return self.result


class _ReflectionPipeline:
    def __init__(self) -> None:
        self.requests: list[ReflectionPipelineRequest] = []

    def run(self, *, request: ReflectionPipelineRequest):
        self.requests.append(request)
        return SimpleNamespace(
            daily_reflections=(SimpleNamespace(daily_reflection_id="reflection-1"),),
            learning_factors=(SimpleNamespace(learning_factor_id="lf-1"),),
        )


def test_live_reflection_runtime_returns_skipped_without_running_pipeline():
    runtime = LiveReflectionRuntime(
        dependencies=LiveReflectionDependencies(
            request_loader=_RequestLoader(
                ReflectionLoadResult(status="skipped", request=None, reasons=("portfolio_outcome_missing",))
            ),
            reflection_pipeline=_ReflectionPipeline(),
        ),
        now=lambda: datetime(2026, 6, 4, 22, 0, tzinfo=timezone.utc),
    )

    result = runtime.run()

    assert result["status"] == "skipped"
    assert result["phase"] == "reflection"
    assert result["summary"]["reasons"] == ["portfolio_outcome_missing"]


def test_live_reflection_runtime_runs_pipeline_when_request_is_ready():
    request = ReflectionPipelineRequest(
        trade_date=date(2026, 6, 4),
        decision_time=datetime(2026, 6, 4, 22, 0, tzinfo=timezone.utc),
        available_for_decision_at=datetime(2026, 6, 4, 22, 0, tzinfo=timezone.utc),
        portfolio_outcome={"day_pnl": 250.0},
        morning_macro_snapshot={"regime": "neutral"},
        trading_decisions=({"ticker": "AAPL"},),
        portfolio_snapshots=({"account_equity": 100250.0},),
    )
    pipeline = _ReflectionPipeline()
    runtime = LiveReflectionRuntime(
        dependencies=LiveReflectionDependencies(
            request_loader=_RequestLoader(ReflectionLoadResult(status="ready", request=request)),
            reflection_pipeline=pipeline,
        ),
        now=lambda: datetime(2026, 6, 4, 22, 0, tzinfo=timezone.utc),
    )

    result = runtime.run()

    assert len(pipeline.requests) == 1
    assert result["status"] == "passed"
    assert result["phase"] == "reflection"
    assert result["summary"]["daily_reflection_count"] == 1
    assert result["summary"]["learning_factor_count"] == 1


def test_run_live_reflection_once_builds_default_dependencies_when_not_injected(monkeypatch):
    request = ReflectionPipelineRequest(
        trade_date=date(2026, 6, 4),
        decision_time=datetime(2026, 6, 4, 22, 0, tzinfo=timezone.utc),
        available_for_decision_at=datetime(2026, 6, 4, 22, 0, tzinfo=timezone.utc),
        portfolio_outcome={"day_pnl": 250.0},
        morning_macro_snapshot={"regime": "neutral"},
        trading_decisions=({"ticker": "AAPL"},),
        portfolio_snapshots=({"account_equity": 100250.0},),
    )
    pipeline = _ReflectionPipeline()
    dependencies = LiveReflectionDependencies(
        request_loader=_RequestLoader(ReflectionLoadResult(status="ready", request=request)),
        reflection_pipeline=pipeline,
    )
    monkeypatch.setattr(
        "src.trading.runtime.reflection.build_live_reflection_dependencies",
        lambda _session: dependencies,
    )

    result = run_live_reflection_once(now=lambda: datetime(2026, 6, 4, 22, 0, tzinfo=timezone.utc))

    assert result["status"] == "passed"
    assert result["phase"] == "reflection"


def test_runtime_dispatch_routes_reflection_to_live_runtime():
    from src.trading.runtime.reflection import run_live_reflection_once as live_handler

    assert get_job_phase_handler("reflection") is live_handler
