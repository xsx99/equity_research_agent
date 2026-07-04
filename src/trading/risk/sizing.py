"""Deterministic PR04 position sizing."""
from __future__ import annotations

from src.trading.strategies.policy import experimental_strategy_weight_cap
from src.trading.risk.config import RiskLimitConfig
from src.trading.risk.context import PortfolioContext, PositionSizingDecisionRecord, TradeRiskRequest


class PositionSizer:
    """Apply deterministic sizing inputs and caps."""

    def size_position(
        self,
        request: TradeRiskRequest,
        portfolio_context: PortfolioContext,
        config: RiskLimitConfig,
    ) -> PositionSizingDecisionRecord:
        base_weight = min(
            request.target_weight,
            config.strategy_budget_weight
            * request.candidate.candidate_score
            * max(0.0, min(1.0, request.confidence))
            * config.macro_risk_budget_multiplier,
        )
        if request.candidate.strategy_lifecycle_status == "experimental":
            base_weight = min(base_weight, experimental_strategy_weight_cap(config.strategy_budget_weight))
        volatility_adjusted_weight = base_weight
        if request.atr_pct > 0:
            volatility_adjusted_weight = min(
                base_weight,
                base_weight * (config.target_volatility / request.atr_pct),
            )

        liquidity_capped_weight = min(volatility_adjusted_weight, config.max_liquidity_weight)
        final_weight = min(liquidity_capped_weight, config.max_single_name_weight)
        final_notional = final_weight * portfolio_context.account_equity

        applied_caps: list[str] = []
        if volatility_adjusted_weight < base_weight:
            applied_caps.append("volatility_cap")
        if liquidity_capped_weight < volatility_adjusted_weight:
            applied_caps.append("liquidity_cap")
        if final_weight < liquidity_capped_weight:
            applied_caps.append("single_name_cap")
        binding_constraint = applied_caps[-1] if applied_caps else None

        return PositionSizingDecisionRecord.create(
            candidate_score_id=request.candidate.candidate_score_id,
            trade_classification_id=request.classification.trade_classification_id,
            ticker=request.candidate.ticker,
            risk_appetite=config.risk_appetite,
            base_weight=base_weight,
            volatility_adjusted_weight=volatility_adjusted_weight,
            liquidity_capped_weight=liquidity_capped_weight,
            final_weight=final_weight,
            final_notional=final_notional,
            applied_caps=applied_caps,
            binding_constraint=binding_constraint,
            decision_time=request.candidate.decision_time,
            metadata_json={
                "atr_pct": request.atr_pct,
                "target_volatility": config.target_volatility,
                "average_daily_dollar_volume": request.average_daily_dollar_volume,
                "strategy_lifecycle_status": request.candidate.strategy_lifecycle_status,
            },
        )
