from datetime import datetime, timezone

from src.trading.risk import (
    PendingTradeRiskRecord,
    PortfolioContext,
    PortfolioEventRiskAssessmentRecord,
    PortfolioHedgePlanner,
    PortfolioHedgePlannerRequest,
    PortfolioPosition,
    RiskAppetiteProfile,
    RiskConfigResolver,
)


def _position(
    ticker: str,
    *,
    trade_identity: str,
    sector: str,
    event_type: str | None = None,
    macro_sensitivity: str | None = None,
    market_value: float = 20_000,
) -> PortfolioPosition:
    return PortfolioPosition(
        ticker=ticker,
        quantity=100,
        market_value=market_value,
        notional_exposure=market_value,
        trade_identity=trade_identity,
        direction="long",
        sector=sector,
        strategy_id="relative_strength_rotation_v1",
        intended_horizon="2w-3m",
        beta_bucket="high",
        volatility_bucket="high",
        liquidity_bucket="liquid",
        event_type=event_type,
        macro_sensitivity=macro_sensitivity,
        margin_requirement=market_value * 0.5,
    )


def _portfolio_context(*positions: PortfolioPosition) -> PortfolioContext:
    return PortfolioContext(
        as_of=datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc),
        account_equity=100_000,
        cash_balance=40_000,
        buying_power=180_000,
        excess_liquidity=70_000,
        positions=positions,
        open_strategy_exposure={},
        current_factor_exposure=(),
        stock_margin_requirement=10_000,
        option_margin_requirement=0,
        total_margin_requirement=10_000,
    )


def _risk_config(portfolio_context: PortfolioContext):
    return RiskConfigResolver().resolve(
        risk_appetite=RiskAppetiteProfile.BALANCED,
        portfolio_context=portfolio_context,
        macro_risk_budget_multiplier=1.0,
    )


def test_planner_opens_sector_hedge_for_cluster_risk_without_blocking_core_holding():
    portfolio_context = _portfolio_context(
        _position(
            "NVDA",
            trade_identity="core_holding",
            sector="Technology",
            event_type="earnings",
            macro_sensitivity="rates_sensitive",
        )
    )
    request = PortfolioHedgePlannerRequest(
        decision_time=portfolio_context.as_of,
        risk_window="1-5d",
        portfolio_context=portfolio_context,
        risk_limit_config=_risk_config(portfolio_context),
        event_assessments=(
            PortfolioEventRiskAssessmentRecord(
                ticker="NVDA",
                risk_source="sector_event_cluster",
                severity="high",
                event_type="earnings",
                days_until_event=2,
                affects_existing_position=True,
                affects_pending_trade=False,
                metadata_json={},
            ),
        ),
        pending_trades=(),
    )

    intent = PortfolioHedgePlanner().plan(request)

    assert intent.aggregate_risk_state == "event_cluster_risk"
    assert any(action.action == "allow" and action.ticker == "NVDA" for action in intent.position_actions)
    assert all(action.action != "block_open" for action in intent.position_actions)
    assert intent.hedge_actions[0].action == "open_hedge"
    assert intent.hedge_actions[0].target_underlier == "XLK"
    assert intent.hedge_actions[0].coverage_ratio == 0.5


def test_planner_blocks_tactical_open_for_near_term_own_event():
    portfolio_context = _portfolio_context()
    request = PortfolioHedgePlannerRequest(
        decision_time=portfolio_context.as_of,
        risk_window="1-5d",
        portfolio_context=portfolio_context,
        risk_limit_config=_risk_config(portfolio_context),
        event_assessments=(
            PortfolioEventRiskAssessmentRecord(
                ticker="ASAN",
                risk_source="own_event",
                severity="high",
                event_type="earnings",
                days_until_event=1,
                affects_existing_position=False,
                affects_pending_trade=True,
                metadata_json={},
            ),
        ),
        pending_trades=(
            PendingTradeRiskRecord(
                ticker="ASAN",
                trade_identity="tactical_stock_trade",
                sector="Technology",
                event_type="earnings",
                macro_sensitivity="rates_sensitive",
            ),
        ),
    )

    intent = PortfolioHedgePlanner().plan(request)

    assert intent.aggregate_risk_state == "mixed_risk"
    assert intent.position_actions[0].ticker == "ASAN"
    assert intent.position_actions[0].action == "block_open"
    assert intent.position_actions[0].reason_code == "own_event_block"
    assert intent.hedge_actions == ()


def test_planner_applies_single_name_rules_before_macro_hedge_for_mixed_risk():
    portfolio_context = _portfolio_context(
        _position(
            "MSFT",
            trade_identity="core_holding",
            sector="Technology",
            macro_sensitivity="rates_sensitive",
            market_value=25_000,
        )
    )
    request = PortfolioHedgePlannerRequest(
        decision_time=portfolio_context.as_of,
        risk_window="1-5d",
        portfolio_context=portfolio_context,
        risk_limit_config=_risk_config(portfolio_context),
        macro_risk_state="high",
        event_assessments=(
            PortfolioEventRiskAssessmentRecord(
                ticker="NVDA",
                risk_source="own_event",
                severity="high",
                event_type="earnings",
                days_until_event=2,
                affects_existing_position=False,
                affects_pending_trade=True,
                metadata_json={},
            ),
        ),
        pending_trades=(
            PendingTradeRiskRecord(
                ticker="NVDA",
                trade_identity="tactical_stock_trade",
                sector="Technology",
                event_type="earnings",
                macro_sensitivity="rates_sensitive",
            ),
        ),
    )

    intent = PortfolioHedgePlanner().plan(request)

    assert intent.aggregate_risk_state == "mixed_risk"
    assert intent.binding_constraints[0] == "own_event_block"
    assert intent.position_actions[0].action == "block_open"
    assert intent.hedge_actions[0].action == "open_hedge"
    assert intent.hedge_actions[0].target_underlier == "QQQ"
    assert intent.hedge_actions[0].coverage_ratio == 0.5


def test_planner_surfaces_canonical_macro_and_risk_source_metadata():
    portfolio_context = _portfolio_context()
    request = PortfolioHedgePlannerRequest(
        decision_time=portfolio_context.as_of,
        risk_window="1-5d",
        portfolio_context=portfolio_context,
        risk_limit_config=_risk_config(portfolio_context),
        event_assessments=(
            PortfolioEventRiskAssessmentRecord(
                ticker="ASAN",
                risk_source="own_event",
                severity="high",
                event_type="earnings",
                days_until_event=1,
                affects_existing_position=False,
                affects_pending_trade=True,
                metadata_json={},
            ),
        ),
        pending_trades=(
            PendingTradeRiskRecord(
                ticker="ASAN",
                trade_identity="tactical_stock_trade",
                sector="Technology",
                event_type="earnings",
                macro_sensitivity="rates_sensitive",
            ),
        ),
        macro_snapshot=type(
            "_MacroSnapshot",
            (),
            {
                "macro_snapshot_id": "macro-1",
                "regime": "risk_off",
                "metadata_json": {"availability_issues": ["global_context_stale"]},
            },
        )(),
    )

    intent = PortfolioHedgePlanner().plan(request)

    assert intent.metadata_json["macro_snapshot_id"] == "macro-1"
    assert intent.metadata_json["top_risk_sources"] == ("own_event", "macro")
    assert intent.metadata_json["hedge_posture"]["target_underlier"] == "QQQ"
    assert intent.metadata_json["data_availability_issues"] == ("global_context_stale",)
