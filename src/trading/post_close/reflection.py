"""PR09 reflection pipeline and learning-factor lifecycle handling."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from src.agents.reflection import ReflectionAgent
from src.agents.trading import PromptRunRecord, UsageEventRecord


_RISK_TIGHTENING_EFFECT_TAGS = {
    "reduce_exposure",
    "require_confirmation",
    "block_stale_data",
    "lower_confidence",
    "tighten_exit_rules",
}
_EXPANSIONARY_EFFECT_TAGS = {
    "increase_score",
    "expand_eligibility",
    "increase_size",
    "weaken_safety_rails",
    "broaden_universe",
    "increase_risk_budget",
}


def derive_learning_factor_status(*, activation_policy: str, effect_tags: tuple[str, ...] | list[str]) -> str:
    """Map reflection proposals into lifecycle states under PR09 policy."""
    tags = set(effect_tags)
    if activation_policy == "observation":
        return "observation"
    if activation_policy == "shadow":
        return "shadow"
    if tags & _EXPANSIONARY_EFFECT_TAGS:
        return "candidate"
    if activation_policy == "auto_risk_tightening" and tags and tags <= _RISK_TIGHTENING_EFFECT_TAGS:
        return "active"
    return "candidate"


@dataclass(frozen=True)
class ReflectionPipelineRequest:
    """Structured reflection input assembled from post-close artifacts."""

    trade_date: date
    decision_time: datetime
    available_for_decision_at: datetime
    portfolio_outcome: dict[str, Any]
    morning_macro_snapshot: dict[str, Any]
    strategy_candidates: tuple[dict[str, Any], ...] = ()
    manual_ticker_requests: tuple[dict[str, Any], ...] = ()
    trading_decisions: tuple[dict[str, Any], ...] = ()
    rejected_decisions: tuple[dict[str, Any], ...] = ()
    intraday_news_alerts: tuple[dict[str, Any], ...] = ()
    intraday_rebalance_decisions: tuple[dict[str, Any], ...] = ()
    paper_orders: tuple[dict[str, Any], ...] = ()
    paper_executions: tuple[dict[str, Any], ...] = ()
    risk_snapshots: tuple[dict[str, Any], ...] = ()
    risk_factor_exposures: tuple[dict[str, Any], ...] = ()
    portfolio_snapshots: tuple[dict[str, Any], ...] = ()
    candidate_outcome_evaluations: tuple[dict[str, Any], ...] = ()
    benchmark_peer_returns: dict[str, Any] = field(default_factory=dict)
    paper_option_decisions: tuple[dict[str, Any], ...] = ()
    paper_option_positions: tuple[dict[str, Any], ...] = ()
    option_risk_snapshots: tuple[dict[str, Any], ...] = ()
    worst_case_assignment_snapshots: tuple[dict[str, Any], ...] = ()
    learning_factors_used: tuple[dict[str, Any] | str, ...] = ()


@dataclass(frozen=True)
class DailyReflectionRecord:
    """Persistable post-close reflection artifact."""

    daily_reflection_id: str
    trade_date: date
    status: str
    prompt_template: Any
    prompt_run: PromptRunRecord
    usage_events: list[UsageEventRecord]
    reflection_json: dict[str, Any]
    strategy_proposal_hints: tuple[dict[str, Any], ...]
    metadata_json: dict[str, Any]


@dataclass(frozen=True)
class LearningFactorRecord:
    """Persistable structured learning factor."""

    learning_factor_id: str
    factor_key: str
    trade_date: date
    title: str
    factor_type: str
    scope: str
    status: str
    strategy_id: str | None
    condition: str
    recommendation: str
    confidence: float
    activation_policy: str
    effect_tags: tuple[str, ...]
    evidence: tuple[str, ...]
    source_daily_reflection_id: str
    metadata_json: dict[str, Any]


@dataclass(frozen=True)
class ReflectionPipelineResult:
    """Persisted PR09 reflection artifacts."""

    daily_reflections: tuple[DailyReflectionRecord, ...]
    learning_factors: tuple[LearningFactorRecord, ...]


class ReflectionPipeline:
    """Persist post-close reflections and approved learning-factor lifecycle states."""

    def __init__(
        self,
        *,
        repository: Any,
        prompt_registry: Any,
        model_name: str,
        agent_runner: Any,
    ) -> None:
        self.repository = repository
        self.agent = ReflectionAgent(
            tool_registry=None,
            prompt_registry=prompt_registry,
            model_name=model_name,
            agent_runner=agent_runner,
        )

    def run(self, *, request: ReflectionPipelineRequest) -> ReflectionPipelineResult:
        payload = {
            "trade_date": request.trade_date.isoformat(),
            "decision_time": request.decision_time.isoformat(),
            "available_for_decision_at": request.available_for_decision_at.isoformat(),
            "portfolio_outcome": request.portfolio_outcome,
            "morning_macro_snapshot": request.morning_macro_snapshot,
            "strategy_candidates": list(request.strategy_candidates),
            "manual_ticker_requests": list(request.manual_ticker_requests),
            "trading_decisions": list(request.trading_decisions),
            "rejected_decisions": list(request.rejected_decisions),
            "intraday_news_alerts": list(request.intraday_news_alerts),
            "intraday_rebalance_decisions": list(request.intraday_rebalance_decisions),
            "paper_orders": list(request.paper_orders),
            "paper_executions": list(request.paper_executions),
            "risk_snapshots": list(request.risk_snapshots),
            "risk_factor_exposures": list(request.risk_factor_exposures),
            "portfolio_snapshots": list(request.portfolio_snapshots),
            "candidate_outcome_evaluations": list(request.candidate_outcome_evaluations),
            "benchmark_peer_returns": dict(request.benchmark_peer_returns),
            "paper_option_decisions": list(request.paper_option_decisions),
            "paper_option_positions": list(request.paper_option_positions),
            "option_risk_snapshots": list(request.option_risk_snapshots),
            "worst_case_assignment_snapshots": list(request.worst_case_assignment_snapshots),
            "learning_factors_used": list(request.learning_factors_used),
        }
        result = self.agent.run(payload, context=None)
        prompt_template = result.metadata["prompt_template"]
        prompt_run = result.metadata["prompt_run"]
        usage_events = result.metadata["usage_events"]
        reflection_id = str(uuid.uuid4())
        reflection_json = dict(result.output_data or {})
        daily_reflection = DailyReflectionRecord(
            daily_reflection_id=reflection_id,
            trade_date=request.trade_date,
            status="succeeded" if result.success else "fallback",
            prompt_template=prompt_template,
            prompt_run=prompt_run,
            usage_events=list(usage_events),
            reflection_json=reflection_json,
            strategy_proposal_hints=tuple(reflection_json.get("strategy_proposal_hints", ())),
            metadata_json={
                "fallback_action": reflection_json.get("fallback_action"),
                "portfolio_outcome": request.portfolio_outcome,
            },
        )
        self.repository.save_prompt_template(prompt_template)
        self.repository.save_prompt_run(prompt_run)
        self.repository.save_usage_events(usage_events)
        self.repository.save_daily_reflection(daily_reflection)

        learning_factors: list[LearningFactorRecord] = []
        if result.success:
            for index, factor in enumerate(reflection_json.get("learning_factors", []), start=1):
                status = derive_learning_factor_status(
                    activation_policy=str(factor["activation_policy"]),
                    effect_tags=tuple(str(tag) for tag in factor.get("effect_tags", ())),
                )
                record = LearningFactorRecord(
                    learning_factor_id=str(uuid.uuid4()),
                    factor_key=f"lf_{request.trade_date.strftime('%Y_%m_%d')}_{index:02d}",
                    trade_date=request.trade_date,
                    title=str(factor["title"]),
                    factor_type=str(factor["factor_type"]),
                    scope=str(factor["scope"]),
                    status=status,
                    strategy_id=factor.get("strategy_id"),
                    condition=str(factor["condition"]),
                    recommendation=str(factor["recommendation"]),
                    confidence=float(factor["confidence"]),
                    activation_policy=str(factor["activation_policy"]),
                    effect_tags=tuple(str(tag) for tag in factor.get("effect_tags", ())),
                    evidence=tuple(str(item) for item in factor.get("evidence", ())),
                    source_daily_reflection_id=reflection_id,
                    metadata_json={},
                )
                self.repository.save_learning_factor(record)
                learning_factors.append(record)

        return ReflectionPipelineResult(
            daily_reflections=(daily_reflection,),
            learning_factors=tuple(learning_factors),
        )
