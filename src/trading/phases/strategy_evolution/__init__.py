"""Live strategy evolution runtime assembly and orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

from src.core import config as app_config
from src.trading.phases._shell.support import build_runtime_report
from src.trading.phases.strategy_evolution.pipeline import StrategyEvolutionPipeline, StrategyEvolutionRequest
from src.trading.trade_day import trade_date_for


@dataclass(frozen=True)
class StrategyEvolutionLoadResult:
    status: str
    request: StrategyEvolutionRequest | None
    reasons: tuple[str, ...] = ()


class LiveStrategyEvolutionRequestLoader:
    """Assemble same-day persisted reflection artifacts into one evolution request."""

    def __init__(self, *, repository: Any) -> None:
        self.repository = repository

    def load(self, *, trade_date: date, decision_time: datetime) -> StrategyEvolutionLoadResult:
        payload = self.repository.load_strategy_evolution_inputs(trade_date=trade_date)
        daily_reflections = tuple(payload.get("daily_reflections") or ())
        current_reflections = tuple(
            reflection
            for reflection in daily_reflections
            if getattr(reflection, "trade_date", None) == trade_date
        )
        if not current_reflections:
            return StrategyEvolutionLoadResult(
                status="skipped",
                request=None,
                reasons=("daily_reflection_missing",),
            )
        request = StrategyEvolutionRequest(
            trade_date=trade_date,
            decision_time=decision_time,
            available_for_decision_at=decision_time,
            daily_reflections=daily_reflections,
            learning_factors=tuple(payload.get("learning_factors") or ()),
            rejected_candidates=tuple(payload.get("rejected_candidates") or ()),
            candidate_outcome_evaluations=tuple(payload.get("candidate_outcome_evaluations") or ()),
        )
        return StrategyEvolutionLoadResult(status="ready", request=request)


@dataclass(frozen=True)
class LiveStrategyEvolutionDependencies:
    request_loader: Any
    strategy_evolution_pipeline: Any


class LiveStrategyEvolutionRuntime:
    """Run the post-close strategy evolution phase from persisted artifacts."""

    def __init__(
        self,
        *,
        dependencies: LiveStrategyEvolutionDependencies,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.dependencies = dependencies
        self.now = now or (lambda: datetime.now(timezone.utc))

    def run(self) -> dict[str, Any]:
        decision_time = self.now()
        trade_date = trade_date_for(decision_time, app_config.SCHEDULER_TIMEZONE)
        load_result = self.dependencies.request_loader.load(
            trade_date=trade_date,
            decision_time=decision_time,
        )
        if load_result.status != "ready" or load_result.request is None:
            return build_runtime_report(
                phase="strategy_evolution",
                as_of=decision_time,
                status="skipped",
                summary={"reasons": list(load_result.reasons)},
            )
        result = self.dependencies.strategy_evolution_pipeline.run(request=load_result.request)
        return build_runtime_report(
            phase="strategy_evolution",
            as_of=decision_time,
            summary={
                "strategy_proposal_count": len(tuple(getattr(result, "strategy_proposals", ()))),
                "strategy_definition_count": len(tuple(getattr(result, "strategy_definitions", ()))),
                "strategy_evaluation_result_count": len(
                    tuple(getattr(result, "strategy_evaluation_results", ()))
                ),
                "lifecycle_update_count": len(tuple(getattr(result, "lifecycle_updates", ()))),
            },
        )


def build_live_strategy_evolution_dependencies(session: Any | None = None) -> LiveStrategyEvolutionDependencies:
    """Build the default production dependency graph for one live evolution run."""
    if session is None:
        raise RuntimeError("db_session_required_for_live_strategy_evolution_dependencies")
    from src.agents.prompt_registry import PromptRegistry
    from src.agents.strategy_evolution import _default_agent_runner
    from src.trading.repositories.sqlalchemy import SQLAlchemyTradingRepository

    repository = SQLAlchemyTradingRepository(session)
    return LiveStrategyEvolutionDependencies(
        request_loader=LiveStrategyEvolutionRequestLoader(repository=repository),
        strategy_evolution_pipeline=StrategyEvolutionPipeline(
            repository=repository,
            prompt_registry=PromptRegistry.get_default(),
            model_name=app_config.STRATEGY_EVOLUTION_MODEL_NAME,
            agent_runner=_default_agent_runner,
        ),
    )


def run_live_strategy_evolution_once(
    *,
    dependencies: LiveStrategyEvolutionDependencies | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Execute one live strategy evolution run with injected dependencies."""
    return run_strategy_evolution_once(
        dependencies=dependencies,
        now=now,
    )


def run_strategy_evolution_once(
    *,
    dependencies: LiveStrategyEvolutionDependencies | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Execute one live strategy evolution run with injected dependencies."""
    if dependencies is not None:
        return LiveStrategyEvolutionRuntime(dependencies=dependencies, now=now).run()

    from src.db.connection import get_session

    with get_session() as session:
        return LiveStrategyEvolutionRuntime(
            dependencies=build_live_strategy_evolution_dependencies(session),
            now=now,
        ).run()
