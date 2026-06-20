from __future__ import annotations

from datetime import date

from src.trading.learning.apply import build_learning_adjustments
from src.trading.post_close.reflection import LearningFactorRecord


def _factor(
    factor_key: str,
    *,
    scope: str,
    status: str,
    effect_tags: tuple[str, ...],
    strategy_id: str | None = None,
) -> LearningFactorRecord:
    return LearningFactorRecord(
        learning_factor_id=f"{factor_key}-id",
        factor_key=factor_key,
        trade_date=date(2026, 6, 5),
        title=factor_key,
        factor_type="candidate_filter",
        scope=scope,
        status=status,
        strategy_id=strategy_id,
        condition="condition",
        recommendation="recommendation",
        confidence=0.7,
        activation_policy=status,
        effect_tags=effect_tags,
        evidence=("evidence",),
        source_daily_reflection_id="reflection-1",
        metadata_json={},
    )


def test_build_learning_adjustments_applies_active_strategy_and_risk_factors():
    adjustments = build_learning_adjustments(
        (
            _factor(
                "lf-score",
                scope="strategy",
                status="active",
                strategy_id="relative_strength_rotation_v1",
                effect_tags=("increase_score",),
            ),
            _factor(
                "lf-risk",
                scope="risk",
                status="active",
                effect_tags=("reduce_exposure",),
            ),
            _factor(
                "lf-shadow",
                scope="risk",
                status="shadow",
                effect_tags=("increase_risk_budget",),
            ),
        )
    )

    assert adjustments.strategy_score_multiplier["relative_strength_rotation_v1"] == 1.1
    assert adjustments.risk_budget_multiplier == 0.85
    assert adjustments.applied_factor_keys == ("lf-score", "lf-risk")
    assert adjustments.shadow_factor_keys == ("lf-shadow",)


def test_build_learning_adjustments_clamps_risk_budget_multiplier():
    adjustments = build_learning_adjustments(
        (
            _factor("lf-down-1", scope="risk", status="active", effect_tags=("reduce_exposure",)),
            _factor("lf-down-2", scope="risk", status="active", effect_tags=("reduce_exposure",)),
            _factor("lf-down-3", scope="risk", status="active", effect_tags=("reduce_exposure",)),
            _factor("lf-down-4", scope="risk", status="active", effect_tags=("reduce_exposure",)),
            _factor("lf-down-5", scope="risk", status="active", effect_tags=("reduce_exposure",)),
        )
    )

    assert adjustments.risk_budget_multiplier == 0.5
