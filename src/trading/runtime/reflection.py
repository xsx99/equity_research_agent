"""Live reflection runtime assembly and orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

from src.core import config as app_config
from src.trading.post_close.reflection import ReflectionPipeline, ReflectionPipelineRequest
from src.trading.runtime.trade_day import local_day_bounds_utc, trade_date_for
from src.trading.runtime.support import build_runtime_report


@dataclass(frozen=True)
class ReflectionLoadResult:
    status: str
    request: ReflectionPipelineRequest | None
    reasons: tuple[str, ...] = ()


class LiveReflectionRequestLoader:
    """Assemble same-day persisted artifacts into one reflection request."""

    def __init__(self, *, repository: Any) -> None:
        self.repository = repository

    def load(
        self,
        *,
        trade_date: date,
        decision_time: datetime,
        window: tuple[datetime, datetime],
    ) -> ReflectionLoadResult:
        payload = self.repository.load_reflection_inputs(trade_date=trade_date, window=window)
        portfolio_outcome = payload.get("portfolio_outcome")
        portfolio_snapshots = tuple(payload.get("portfolio_snapshots") or ())
        reasons: list[str] = []
        if not portfolio_outcome:
            reasons.append("portfolio_outcome_missing")
        if not portfolio_snapshots:
            reasons.append("portfolio_snapshots_missing")
        if reasons:
            return ReflectionLoadResult(status="skipped", request=None, reasons=tuple(reasons))
        request = ReflectionPipelineRequest(
            trade_date=trade_date,
            decision_time=decision_time,
            available_for_decision_at=decision_time,
            portfolio_outcome=dict(portfolio_outcome),
            morning_macro_snapshot=dict(payload.get("morning_macro_snapshot") or {}),
            strategy_candidates=tuple(payload.get("strategy_candidates") or ()),
            manual_ticker_requests=tuple(payload.get("manual_ticker_requests") or ()),
            trading_decisions=tuple(payload.get("trading_decisions") or ()),
            rejected_decisions=tuple(payload.get("rejected_decisions") or ()),
            intraday_news_alerts=tuple(payload.get("intraday_news_alerts") or ()),
            intraday_rebalance_decisions=tuple(payload.get("intraday_rebalance_decisions") or ()),
            paper_orders=tuple(payload.get("paper_orders") or ()),
            paper_executions=tuple(payload.get("paper_executions") or ()),
            risk_snapshots=tuple(payload.get("risk_snapshots") or ()),
            risk_factor_exposures=tuple(payload.get("risk_factor_exposures") or ()),
            portfolio_snapshots=portfolio_snapshots,
            candidate_outcome_evaluations=tuple(payload.get("candidate_outcome_evaluations") or ()),
            benchmark_peer_returns=dict(payload.get("benchmark_peer_returns") or {}),
            paper_option_decisions=tuple(payload.get("paper_option_decisions") or ()),
            paper_option_positions=tuple(payload.get("paper_option_positions") or ()),
            option_risk_snapshots=tuple(payload.get("option_risk_snapshots") or ()),
            worst_case_assignment_snapshots=tuple(payload.get("worst_case_assignment_snapshots") or ()),
            risk_hedge_overlays=tuple(payload.get("risk_hedge_overlays") or ()),
            hedge_effectiveness=dict(payload.get("hedge_effectiveness") or {}),
            learning_factors_used=tuple(payload.get("learning_factors_used") or ()),
        )
        return ReflectionLoadResult(status="ready", request=request)


@dataclass(frozen=True)
class LiveReflectionDependencies:
    request_loader: Any
    reflection_pipeline: Any


class LiveReflectionRuntime:
    """Run the post-close reflection phase using persisted same-day artifacts."""

    def __init__(
        self,
        *,
        dependencies: LiveReflectionDependencies,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.dependencies = dependencies
        self.now = now or (lambda: datetime.now(timezone.utc))

    def run(self) -> dict[str, Any]:
        decision_time = self.now()
        trade_date = trade_date_for(decision_time, app_config.SCHEDULER_TIMEZONE)
        window = local_day_bounds_utc(trade_date, app_config.SCHEDULER_TIMEZONE)
        load_result = self.dependencies.request_loader.load(
            trade_date=trade_date,
            decision_time=decision_time,
            window=window,
        )
        if load_result.status != "ready" or load_result.request is None:
            return build_runtime_report(
                phase="reflection",
                as_of=decision_time,
                status="skipped",
                summary={"reasons": list(load_result.reasons)},
            )
        result = self.dependencies.reflection_pipeline.run(request=load_result.request)
        return build_runtime_report(
            phase="reflection",
            as_of=decision_time,
            summary={
                "daily_reflection_count": len(tuple(getattr(result, "daily_reflections", ()))),
                "learning_factor_count": len(tuple(getattr(result, "learning_factors", ()))),
            },
        )


def build_live_reflection_dependencies(session: Any | None = None) -> LiveReflectionDependencies:
    """Build the default production dependency graph for one live reflection run."""
    if session is None:
        raise RuntimeError("db_session_required_for_live_reflection_dependencies")
    from src.agents.prompt_registry import PromptRegistry
    from src.agents.reflection import _default_agent_runner
    from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository

    repository = SqlAlchemyTradingRepository(session)
    return LiveReflectionDependencies(
        request_loader=LiveReflectionRequestLoader(repository=repository),
        reflection_pipeline=ReflectionPipeline(
            repository=repository,
            prompt_registry=PromptRegistry.get_default(),
            model_name=app_config.REFLECTION_MODEL_NAME,
            agent_runner=_default_agent_runner,
        ),
    )


def run_live_reflection_once(
    *,
    dependencies: LiveReflectionDependencies | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Execute one live reflection run with injected dependencies."""
    return run_reflection_once(
        dependencies=dependencies,
        now=now,
    )


def run_reflection_once(
    *,
    dependencies: LiveReflectionDependencies | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Execute one live reflection run with injected dependencies."""
    if dependencies is not None:
        return LiveReflectionRuntime(dependencies=dependencies, now=now).run()

    from src.db.connection import get_session

    with get_session() as session:
        return LiveReflectionRuntime(
            dependencies=build_live_reflection_dependencies(session),
            now=now,
        ).run()
