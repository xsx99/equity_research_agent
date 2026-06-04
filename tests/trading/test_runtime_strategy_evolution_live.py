from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.trading.runtime_dispatch import get_job_phase_handler
from src.trading.strategy_evolution import StrategyEvolutionRequest
from src.trading.runtime_strategy_evolution_live import (
    LiveStrategyEvolutionDependencies,
    LiveStrategyEvolutionRequestLoader,
    LiveStrategyEvolutionRuntime,
    StrategyEvolutionLoadResult,
    run_live_strategy_evolution_once,
)


class _Repository:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def load_strategy_evolution_inputs(self, *, trade_date: date) -> dict[str, object]:
        assert trade_date == date(2026, 6, 4)
        return dict(self.payload)


def test_live_strategy_evolution_request_loader_assembles_same_day_artifacts():
    decision_time = datetime(2026, 6, 4, 22, 30, tzinfo=timezone.utc)
    payload = {
        "daily_reflections": (
            SimpleNamespace(
                daily_reflection_id="reflection-1",
                trade_date=date(2026, 6, 4),
                status="succeeded",
                strategy_proposal_hints=({"title": "Lean into reclaims"},),
                metadata_json={},
            ),
        ),
        "learning_factors": (
            SimpleNamespace(
                learning_factor_id="lf-1",
                factor_key="lf_2026_06_04_01",
                status="candidate",
            ),
        ),
        "rejected_candidates": (
            {"ticker": "AAPL", "strategy_id": "gap_reclaim_v1", "rejection_reason": "risk_limit"},
        ),
        "candidate_outcome_evaluations": (
            SimpleNamespace(
                candidate_outcome_evaluation_id="outcome-1",
                ticker="AAPL",
                strategy_id="gap_reclaim_v1",
                alpha=0.04,
            ),
        ),
    }
    loader = LiveStrategyEvolutionRequestLoader(repository=_Repository(payload))

    result = loader.load(trade_date=date(2026, 6, 4), decision_time=decision_time)

    assert result.status == "ready"
    assert isinstance(result.request, StrategyEvolutionRequest)
    assert result.request is not None
    assert result.request.trade_date == date(2026, 6, 4)
    assert result.request.daily_reflections[0].daily_reflection_id == "reflection-1"
    assert result.request.learning_factors[0].factor_key == "lf_2026_06_04_01"
    assert result.request.rejected_candidates[0]["ticker"] == "AAPL"
    assert result.request.candidate_outcome_evaluations[0].alpha == 0.04


def test_live_strategy_evolution_request_loader_returns_skipped_when_reflection_missing():
    loader = LiveStrategyEvolutionRequestLoader(
        repository=_Repository(
            {
                "daily_reflections": (),
                "learning_factors": (),
                "rejected_candidates": (),
                "candidate_outcome_evaluations": (),
            }
        )
    )

    result = loader.load(
        trade_date=date(2026, 6, 4),
        decision_time=datetime(2026, 6, 4, 22, 30, tzinfo=timezone.utc),
    )

    assert result.status == "skipped"
    assert result.request is None
    assert result.reasons == ("daily_reflection_missing",)


@dataclass(frozen=True)
class _RequestLoader:
    result: StrategyEvolutionLoadResult

    def load(self, *, trade_date: date, decision_time: datetime) -> StrategyEvolutionLoadResult:
        assert trade_date == date(2026, 6, 4)
        assert decision_time.tzinfo is not None
        return self.result


class _StrategyEvolutionPipeline:
    def __init__(self) -> None:
        self.requests: list[StrategyEvolutionRequest] = []

    def run(self, *, request: StrategyEvolutionRequest):
        self.requests.append(request)
        return SimpleNamespace(
            strategy_proposals=(SimpleNamespace(strategy_proposal_id="proposal-1"),),
            strategy_definitions=(SimpleNamespace(strategy_definition_id="definition-1"),),
            strategy_evaluation_results=(SimpleNamespace(strategy_evaluation_result_id="evaluation-1"),),
            lifecycle_updates=(SimpleNamespace(strategy_evaluation_result_id="transition-1"),),
        )


def test_live_strategy_evolution_runtime_returns_skipped_without_running_pipeline():
    runtime = LiveStrategyEvolutionRuntime(
        dependencies=LiveStrategyEvolutionDependencies(
            request_loader=_RequestLoader(
                StrategyEvolutionLoadResult(
                    status="skipped",
                    request=None,
                    reasons=("daily_reflection_missing",),
                )
            ),
            strategy_evolution_pipeline=_StrategyEvolutionPipeline(),
        ),
        now=lambda: datetime(2026, 6, 4, 22, 30, tzinfo=timezone.utc),
    )

    result = runtime.run()

    assert result["status"] == "skipped"
    assert result["phase"] == "strategy_evolution"
    assert result["summary"]["reasons"] == ["daily_reflection_missing"]


def test_live_strategy_evolution_runtime_runs_pipeline_when_request_is_ready():
    request = StrategyEvolutionRequest(
        trade_date=date(2026, 6, 4),
        decision_time=datetime(2026, 6, 4, 22, 30, tzinfo=timezone.utc),
        available_for_decision_at=datetime(2026, 6, 4, 22, 30, tzinfo=timezone.utc),
        daily_reflections=(SimpleNamespace(daily_reflection_id="reflection-1", strategy_proposal_hints=()),),
    )
    pipeline = _StrategyEvolutionPipeline()
    runtime = LiveStrategyEvolutionRuntime(
        dependencies=LiveStrategyEvolutionDependencies(
            request_loader=_RequestLoader(StrategyEvolutionLoadResult(status="ready", request=request)),
            strategy_evolution_pipeline=pipeline,
        ),
        now=lambda: datetime(2026, 6, 4, 22, 30, tzinfo=timezone.utc),
    )

    result = runtime.run()

    assert len(pipeline.requests) == 1
    assert result["status"] == "passed"
    assert result["phase"] == "strategy_evolution"
    assert result["summary"]["strategy_proposal_count"] == 1
    assert result["summary"]["strategy_definition_count"] == 1
    assert result["summary"]["strategy_evaluation_result_count"] == 1
    assert result["summary"]["lifecycle_update_count"] == 1


def test_run_live_strategy_evolution_once_builds_default_dependencies_when_not_injected(monkeypatch):
    request = StrategyEvolutionRequest(
        trade_date=date(2026, 6, 4),
        decision_time=datetime(2026, 6, 4, 22, 30, tzinfo=timezone.utc),
        available_for_decision_at=datetime(2026, 6, 4, 22, 30, tzinfo=timezone.utc),
        daily_reflections=(SimpleNamespace(daily_reflection_id="reflection-1", strategy_proposal_hints=()),),
    )
    pipeline = _StrategyEvolutionPipeline()
    dependencies = LiveStrategyEvolutionDependencies(
        request_loader=_RequestLoader(StrategyEvolutionLoadResult(status="ready", request=request)),
        strategy_evolution_pipeline=pipeline,
    )
    monkeypatch.setattr(
        "src.trading.runtime_strategy_evolution_live.build_live_strategy_evolution_dependencies",
        lambda _session: dependencies,
    )

    result = run_live_strategy_evolution_once(now=lambda: datetime(2026, 6, 4, 22, 30, tzinfo=timezone.utc))

    assert result["status"] == "passed"
    assert result["phase"] == "strategy_evolution"


def test_runtime_dispatch_routes_strategy_evolution_to_live_runtime():
    from src.trading.runtime_strategy_evolution_live import run_live_strategy_evolution_once as live_handler

    assert get_job_phase_handler("strategy_evolution") is live_handler
