"""Portfolio-pool trade identity policies for the V2 trading workflow."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradeIdentityPolicy:
    """Static policy for one portfolio-pool identity."""

    trade_identity: str
    instrument: str
    portfolio_pool: str
    default_horizon: str
    sizing_policy: str
    exit_policy: str
    generated_by: str
    requires_option_legs: bool = False
    requires_max_loss: bool = False
    requires_assignment_plan_when_short_options: bool = False
    counts_toward_strategy_win_rate: bool = True
    can_be_sold_by_short_term_signal: bool = True


TRADE_IDENTITIES: dict[str, TradeIdentityPolicy] = {
    "core_holding": TradeIdentityPolicy(
        trade_identity="core_holding",
        instrument="stock",
        portfolio_pool="core",
        default_horizon="multi-month+",
        sizing_policy="core_portfolio_intent_budget",
        exit_policy="thesis_invalidation_or_core_risk_budget",
        generated_by="trade_classifier",
        counts_toward_strategy_win_rate=False,
        can_be_sold_by_short_term_signal=False,
    ),
    "tactical_stock_trade": TradeIdentityPolicy(
        trade_identity="tactical_stock_trade",
        instrument="stock",
        portfolio_pool="tactical_stock",
        default_horizon="intraday-3m",
        sizing_policy="strategy_budget_with_volatility_and_liquidity_caps",
        exit_policy="strategy_invalidators_or_target_horizon",
        generated_by="trade_classifier",
    ),
    "tactical_option_trade": TradeIdentityPolicy(
        trade_identity="tactical_option_trade",
        instrument="paper_option_strategy",
        portfolio_pool="tactical_option",
        default_horizon="intraday-8w",
        sizing_policy="defined_risk_option_budget_with_buying_power_caps",
        exit_policy="option_plan_profit_loss_event_or_expiry_rules",
        generated_by="trade_classifier",
        requires_option_legs=True,
        requires_max_loss=True,
        requires_assignment_plan_when_short_options=True,
    ),
    "risk_hedge_overlay": TradeIdentityPolicy(
        trade_identity="risk_hedge_overlay",
        instrument="paper_option_hedge",
        portfolio_pool="risk_hedge",
        default_horizon="while_risk_condition_active",
        sizing_policy="risk_manager_hedge_budget",
        exit_policy="close_when_hedged_risk_normalizes_or_cost_limit_hits",
        generated_by="risk_manager",
        requires_option_legs=True,
        requires_max_loss=True,
        requires_assignment_plan_when_short_options=True,
        counts_toward_strategy_win_rate=False,
    ),
    "watch_only": TradeIdentityPolicy(
        trade_identity="watch_only",
        instrument="none",
        portfolio_pool="watch",
        default_horizon="event_window_or_na",
        sizing_policy="no_order",
        exit_policy="dismiss_or_reclassify_after_new_signal",
        generated_by="trade_classifier",
        counts_toward_strategy_win_rate=False,
    ),
}


def get_trade_identity_policy(trade_identity: str) -> TradeIdentityPolicy:
    """Return the static policy for a trade identity."""
    try:
        return TRADE_IDENTITIES[trade_identity]
    except KeyError as exc:
        raise KeyError(f"Unknown trade identity: {trade_identity}") from exc
