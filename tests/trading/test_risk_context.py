from datetime import datetime, timezone

from src.trading.risk import (
    PortfolioContext,
    PortfolioPosition,
    RiskAppetiteProfile,
    RiskConfigResolver,
    RiskFactorExposureRecord,
    RiskManager,
)


def _position(
    ticker: str,
    *,
    market_value: float,
    sector: str,
    strategy_id: str,
    horizon: str,
    direction: str = "long",
    beta_bucket: str = "high",
    volatility_bucket: str = "high",
    liquidity_bucket: str = "liquid",
    event_type: str | None = None,
    macro_sensitivity: str | None = None,
    trade_identity: str = "tactical_stock_trade",
) -> PortfolioPosition:
    return PortfolioPosition(
        ticker=ticker,
        quantity=100,
        market_value=market_value,
        notional_exposure=market_value,
        trade_identity=trade_identity,
        direction=direction,
        sector=sector,
        strategy_id=strategy_id,
        intended_horizon=horizon,
        beta_bucket=beta_bucket,
        volatility_bucket=volatility_bucket,
        liquidity_bucket=liquidity_bucket,
        event_type=event_type,
        macro_sensitivity=macro_sensitivity,
        margin_requirement=market_value * 0.5,
    )


def test_risk_config_resolver_builds_generated_limits_from_appetite_and_account_state():
    portfolio = PortfolioContext(
        as_of=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        account_equity=100_000,
        cash_balance=40_000,
        buying_power=180_000,
        excess_liquidity=70_000,
        positions=(),
        open_strategy_exposure={},
        current_factor_exposure=(),
        stock_margin_requirement=10_000,
        option_margin_requirement=0,
        total_margin_requirement=10_000,
    )

    conservative = RiskConfigResolver().resolve(
        risk_appetite=RiskAppetiteProfile.CONSERVATIVE,
        portfolio_context=portfolio,
        macro_risk_budget_multiplier=0.8,
    )
    aggressive = RiskConfigResolver().resolve(
        risk_appetite=RiskAppetiteProfile.AGGRESSIVE,
        portfolio_context=portfolio,
        macro_risk_budget_multiplier=1.0,
    )

    assert conservative.risk_appetite == "conservative"
    assert conservative.margin_model_profile == "estimated_fidelity_like_conservative_v1"
    assert conservative.max_single_name_weight < aggressive.max_single_name_weight
    assert conservative.max_total_margin_ratio < aggressive.max_total_margin_ratio
    assert conservative.resolver_version == "risk_config_resolver_v1"


def test_risk_manager_computes_factor_exposures_from_portfolio_context():
    portfolio = PortfolioContext(
        as_of=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        account_equity=100_000,
        cash_balance=20_000,
        buying_power=150_000,
        excess_liquidity=40_000,
        positions=(
            _position(
                "NVDA",
                market_value=20_000,
                sector="Technology",
                strategy_id="relative_strength_rotation_v1",
                horizon="2w-3m",
                event_type="earnings",
                macro_sensitivity="rates_sensitive",
            ),
            _position(
                "AMD",
                market_value=10_000,
                sector="Technology",
                strategy_id="gap_and_go_v1",
                horizon="1d-3d",
                volatility_bucket="medium",
                beta_bucket="high",
                macro_sensitivity="rates_sensitive",
            ),
        ),
        open_strategy_exposure={},
        current_factor_exposure=(),
        stock_margin_requirement=15_000,
        option_margin_requirement=0,
        total_margin_requirement=15_000,
    )

    exposures = RiskManager().compute_factor_exposures(portfolio)

    assert RiskFactorExposureRecord(factor_type="sector", factor_value="Technology", gross_exposure=30_000, net_exposure=30_000, long_exposure=30_000, short_exposure=0, position_count=2, metadata_json={}) in exposures
    assert any(item.factor_type == "strategy" and item.factor_value == "relative_strength_rotation_v1" for item in exposures)
    assert any(item.factor_type == "event_type" and item.factor_value == "earnings" for item in exposures)
    assert any(item.factor_type == "macro_sensitivity" and item.factor_value == "rates_sensitive" and item.position_count == 2 for item in exposures)
