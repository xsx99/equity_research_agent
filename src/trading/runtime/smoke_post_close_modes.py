"""Fixture-backed smoke handlers for post-close reflection and learning paths."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from src.agents.prompt_registry import PromptRegistry
from src.trading.post_close.reflection import ReflectionPipeline, ReflectionPipelineRequest
from src.trading.post_close.strategy_evolution import StrategyEvolutionPipeline, StrategyEvolutionRequest
from src.trading.repositories.in_memory import InMemoryTradingRepository

from .smoke_support import (
    _fixed_now,
    _reflection_agent_runner,
    _seed_strategy_definitions,
    _strategy_evolution_agent_runner,
)


def run_trading_reflection_once() -> dict[str, Any]:
    """Run the post-close reflection path with a fixed fixture payload."""
    return _run_reflection_fixture()


def run_strategy_evolution_once() -> dict[str, Any]:
    """Run the strategy-evolution phase with fixed reflection fixtures."""
    return _run_strategy_evolution_fixture()


def _run_reflection_fixture() -> dict[str, Any]:
    decision_time = _fixed_now() + timedelta(hours=8)
    repository = InMemoryTradingRepository()
    result = ReflectionPipeline(
        repository=repository,
        prompt_registry=PromptRegistry.get_default(),
        model_name="gpt-5-mini",
        agent_runner=_reflection_agent_runner,
    ).run(
        request=ReflectionPipelineRequest(
            trade_date=decision_time.date(),
            decision_time=decision_time,
            available_for_decision_at=decision_time,
            portfolio_outcome={"realized_pnl": 125.0, "unrealized_pnl": -10.0},
            morning_macro_snapshot={"regime": "neutral"},
            benchmark_peer_returns={"QQQ": 0.01},
        )
    )
    return {
        "status": "passed",
        "mode": "reflection_fixture",
        "summary": {
            "reflection_count": len(result.daily_reflections),
            "learning_factor_count": len(result.learning_factors),
            "reflection_status": result.daily_reflections[0].status,
        },
    }


def _run_strategy_evolution_fixture() -> dict[str, Any]:
    decision_time = _fixed_now() + timedelta(hours=8)
    repository = InMemoryTradingRepository()
    _seed_strategy_definitions(repository)
    reflection_result = ReflectionPipeline(
        repository=repository,
        prompt_registry=PromptRegistry.get_default(),
        model_name="gpt-5-mini",
        agent_runner=_reflection_agent_runner,
    ).run(
        request=ReflectionPipelineRequest(
            trade_date=decision_time.date(),
            decision_time=decision_time,
            available_for_decision_at=decision_time,
            portfolio_outcome={"realized_pnl": 125.0, "unrealized_pnl": -10.0},
            morning_macro_snapshot={"regime": "neutral"},
            benchmark_peer_returns={"QQQ": 0.01},
        )
    )
    evolution = StrategyEvolutionPipeline(
        repository=repository,
        prompt_registry=PromptRegistry.get_default(),
        model_name="gpt-5-mini",
        agent_runner=_strategy_evolution_agent_runner,
    ).run(
        request=StrategyEvolutionRequest(
            trade_date=decision_time.date(),
            decision_time=decision_time,
            available_for_decision_at=decision_time,
            daily_reflections=reflection_result.daily_reflections,
            learning_factors=reflection_result.learning_factors,
            rejected_candidates=(
                {
                    "ticker": "PLTR",
                    "strategy_id": "relative_strength_rotation_v1",
                    "rejection_reason": "late_entry",
                    "core_signal_evidence": {"technical.relative_volume": 1.7},
                },
            ),
            candidate_outcome_evaluations=(),
        )
    )
    return {
        "status": "passed",
        "mode": "strategy_evolution_fixture",
        "summary": {
            "proposal_count": len(evolution.strategy_proposals),
            "definition_count": len(evolution.strategy_definitions),
            "proposal_statuses": [proposal.proposal_status for proposal in evolution.strategy_proposals],
        },
    }


__all__ = [
    "_run_reflection_fixture",
    "_run_strategy_evolution_fixture",
    "run_strategy_evolution_once",
    "run_trading_reflection_once",
]
