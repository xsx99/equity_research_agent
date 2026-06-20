"""Translate persisted learning factors into runtime scoring and risk adjustments."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from src.trading.post_close.reflection import LearningFactorRecord

_RISK_TIGHTENING_EFFECT_TAGS = frozenset(
    {
        "reduce_exposure",
        "require_confirmation",
        "block_stale_data",
        "lower_confidence",
        "tighten_exit_rules",
    }
)


@dataclass(frozen=True)
class LearningAdjustments:
    strategy_score_multiplier: dict[str, float]
    risk_budget_multiplier: float
    applied_factor_keys: tuple[str, ...]
    shadow_factor_keys: tuple[str, ...]


def build_learning_adjustments(factors: Iterable["LearningFactorRecord"]) -> LearningAdjustments:
    strategy_score_multiplier: dict[str, float] = {}
    risk_budget_multiplier = 1.0
    applied_factor_keys: list[str] = []
    shadow_factor_keys: list[str] = []
    for factor in factors:
        if factor.status == "shadow":
            shadow_factor_keys.append(factor.factor_key)
            continue
        if factor.status != "active":
            continue

        applied = False
        if factor.scope == "strategy" and factor.strategy_id:
            if "increase_score" in factor.effect_tags:
                current = strategy_score_multiplier.get(factor.strategy_id, 1.0)
                strategy_score_multiplier[factor.strategy_id] = min(1.25, current * 1.10)
                applied = True

        if factor.scope in {"risk", "portfolio"}:
            if any(tag in _RISK_TIGHTENING_EFFECT_TAGS for tag in factor.effect_tags):
                risk_budget_multiplier *= 0.85
                applied = True
            if "increase_risk_budget" in factor.effect_tags:
                risk_budget_multiplier *= 1.10
                applied = True

        if applied:
            applied_factor_keys.append(factor.factor_key)

    return LearningAdjustments(
        strategy_score_multiplier=strategy_score_multiplier,
        risk_budget_multiplier=max(0.5, min(1.25, risk_budget_multiplier)),
        applied_factor_keys=tuple(applied_factor_keys),
        shadow_factor_keys=tuple(shadow_factor_keys),
    )
