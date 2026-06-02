"""Generated PR04 risk appetite configuration."""
from __future__ import annotations

from dataclasses import dataclass

from src.trading.risk.context import PortfolioContext


class RiskAppetiteProfile:
    """Operator-facing risk appetite presets."""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"

    ALL = (CONSERVATIVE, BALANCED, AGGRESSIVE)


@dataclass(frozen=True)
class RiskLimitConfig:
    """Deterministic generated risk limits for one decision window."""

    risk_appetite: str
    resolver_version: str
    margin_model_profile: str
    margin_model_version: str
    macro_risk_budget_multiplier: float
    max_single_name_weight: float
    max_sector_weight: float
    max_total_margin_ratio: float
    max_buying_power_usage_ratio: float
    max_liquidity_weight: float
    strategy_budget_weight: float
    target_volatility: float
    option_defined_risk_preferred: bool
    assignment_concentration_limit: float
    allow_short_stock: bool = False


class RiskConfigResolver:
    """Resolve a simple operator preset into deterministic effective risk limits."""

    resolver_version = "risk_config_resolver_v1"
    margin_model_profile = "estimated_fidelity_like_conservative_v1"
    margin_model_version = "v1"

    def resolve(
        self,
        *,
        risk_appetite: str,
        portfolio_context: PortfolioContext,
        macro_risk_budget_multiplier: float,
    ) -> RiskLimitConfig:
        if risk_appetite not in RiskAppetiteProfile.ALL:
            raise ValueError(f"Unsupported risk appetite: {risk_appetite}")

        preset = {
            RiskAppetiteProfile.CONSERVATIVE: {
                "max_single_name_weight": 0.05,
                "max_sector_weight": 0.22,
                "max_total_margin_ratio": 0.35,
                "max_buying_power_usage_ratio": 0.45,
                "max_liquidity_weight": 0.015,
                "strategy_budget_weight": 0.08,
                "target_volatility": 0.03,
                "assignment_concentration_limit": 0.10,
                "option_defined_risk_preferred": True,
            },
            RiskAppetiteProfile.BALANCED: {
                "max_single_name_weight": 0.08,
                "max_sector_weight": 0.30,
                "max_total_margin_ratio": 0.50,
                "max_buying_power_usage_ratio": 0.60,
                "max_liquidity_weight": 0.025,
                "strategy_budget_weight": 0.10,
                "target_volatility": 0.04,
                "assignment_concentration_limit": 0.15,
                "option_defined_risk_preferred": True,
            },
            RiskAppetiteProfile.AGGRESSIVE: {
                "max_single_name_weight": 0.12,
                "max_sector_weight": 0.38,
                "max_total_margin_ratio": 0.65,
                "max_buying_power_usage_ratio": 0.75,
                "max_liquidity_weight": 0.04,
                "strategy_budget_weight": 0.14,
                "target_volatility": 0.05,
                "assignment_concentration_limit": 0.22,
                "option_defined_risk_preferred": False,
            },
        }[risk_appetite]
        effective_macro = max(0.25, min(1.25, macro_risk_budget_multiplier))
        current_margin_ratio = (
            portfolio_context.total_margin_requirement / portfolio_context.account_equity
            if portfolio_context.account_equity > 0
            else 1.0
        )
        margin_penalty = 1.0 if current_margin_ratio <= 0.5 else max(0.5, 1.0 - (current_margin_ratio - 0.5))

        return RiskLimitConfig(
            risk_appetite=risk_appetite,
            resolver_version=self.resolver_version,
            margin_model_profile=portfolio_context.margin_model_profile or self.margin_model_profile,
            margin_model_version=portfolio_context.margin_model_version or self.margin_model_version,
            macro_risk_budget_multiplier=effective_macro * margin_penalty,
            max_single_name_weight=preset["max_single_name_weight"],
            max_sector_weight=preset["max_sector_weight"],
            max_total_margin_ratio=preset["max_total_margin_ratio"],
            max_buying_power_usage_ratio=preset["max_buying_power_usage_ratio"],
            max_liquidity_weight=preset["max_liquidity_weight"],
            strategy_budget_weight=preset["strategy_budget_weight"],
            target_volatility=preset["target_volatility"],
            option_defined_risk_preferred=bool(preset["option_defined_risk_preferred"]),
            assignment_concentration_limit=preset["assignment_concentration_limit"],
        )
