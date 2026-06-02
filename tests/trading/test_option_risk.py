from __future__ import annotations

from datetime import date, datetime, timezone

from src.trading.risk.options import OptionLegRiskInput, OptionRiskInput, OptionRiskManager
from src.trading.risk import (
    PortfolioContext,
    PortfolioPosition,
    RiskAppetiteProfile,
    RiskConfigResolver,
)


def _portfolio() -> PortfolioContext:
    return PortfolioContext(
        as_of=datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc),
        account_equity=100_000,
        cash_balance=40_000,
        buying_power=180_000,
        excess_liquidity=75_000,
        positions=(
            PortfolioPosition(
                ticker="NVDA",
                quantity=100,
                market_value=12_000,
                notional_exposure=12_000,
                trade_identity="tactical_stock_trade",
                direction="long",
                sector="Technology",
                strategy_id="relative_strength_rotation_v1",
                intended_horizon="2w-3m",
                beta_bucket="high",
                volatility_bucket="high",
                liquidity_bucket="liquid",
                event_type=None,
                macro_sensitivity="ai_capex",
                margin_requirement=6_000,
            ),
        ),
        open_strategy_exposure={},
        current_factor_exposure=(),
        stock_margin_requirement=6_000,
        option_margin_requirement=0.0,
        total_margin_requirement=6_000,
    )


def test_option_risk_manager_rejects_assignment_concentration_breach():
    portfolio = _portfolio()
    config = RiskConfigResolver().resolve(
        risk_appetite=RiskAppetiteProfile.CONSERVATIVE,
        portfolio_context=portfolio,
        macro_risk_budget_multiplier=1.0,
    )
    manager = OptionRiskManager()

    assessment = manager.evaluate_assignment_risk(
        OptionRiskInput(
            ticker="NVDA",
            trade_identity="tactical_option_trade",
            option_strategy_type="put_credit_spread",
            underlying_price=118.0,
            sector="Technology",
            event_type="earnings",
            event_through_expiry=True,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            max_loss=500.0,
            max_profit=150.0,
            net_debit_or_credit=-150.0,
            legs=(
                OptionLegRiskInput(
                    option_type="put",
                    side="sell",
                    quantity=1,
                    strike=110.0,
                    expiry=date(2026, 7, 17),
                    delta=-0.28,
                    gamma=0.02,
                    theta=0.01,
                    vega=-0.07,
                    premium=1.5,
                ),
                OptionLegRiskInput(
                    option_type="put",
                    side="buy",
                    quantity=1,
                    strike=105.0,
                    expiry=date(2026, 7, 17),
                    delta=-0.17,
                    gamma=0.01,
                    theta=-0.01,
                    vega=0.04,
                    premium=0.9,
                ),
            ),
        ),
        portfolio_context=portfolio,
        config=config,
    )

    assert assessment.status == "rejected"
    assert assessment.reason_code == "assignment_concentration_cap"
    assert assessment.worst_case_assignment_notional == 11_000.0
