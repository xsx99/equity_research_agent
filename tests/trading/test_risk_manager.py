from datetime import datetime, timezone

from src.trading.risk import (
    PortfolioContext,
    PortfolioPosition,
    RiskAppetiteProfile,
    RiskConfigResolver,
    RiskManager,
    TradeRiskRequest,
)
from src.trading.risk.sizing import PositionSizer
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord


def _candidate(*, direction: str = "bullish") -> CandidateScoreRecord:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="TSLA",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="strategy-def-1",
        candidate_score=0.8,
        direction=direction,
        action="enter_long" if direction == "bullish" else "enter_short",
        typical_horizon="2w-3m",
        core_signal_evidence={},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=[],
        risk_tags=["relative_strength"],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="test",
        rejection_reason=None,
        benchmark_context={},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )


def _classification(*, trade_identity: str = "tactical_stock_trade") -> TradeClassificationRecord:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return TradeClassificationRecord(
        trade_classification_id="classification-1",
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        ticker="TSLA",
        selected_strategy_id="relative_strength_rotation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity=trade_identity,
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="test",
        selected_strategy_context_json={},
        decision_time=now,
    )


def _request(
    *,
    direction: str = "bullish",
    trade_identity: str = "tactical_stock_trade",
    sector: str = "Consumer Discretionary",
    direct_company_negative_evidence: bool = False,
    bearish_signal_sources: tuple[str, ...] = (),
) -> TradeRiskRequest:
    return TradeRiskRequest(
        candidate=_candidate(direction=direction),
        classification=_classification(trade_identity=trade_identity),
        instrument_type="stock",
        target_weight=0.08,
        confidence=0.75,
        sector=sector,
        beta_bucket="high",
        volatility_bucket="high",
        liquidity_bucket="liquid",
        event_type=None,
        macro_sensitivity="consumer_cycle",
        price=200,
        atr_pct=0.03,
        average_daily_dollar_volume=50_000_000,
        signal_freshness={"technical": "fresh", "fundamental": "fresh", "events_news": "fresh"},
        estimated_margin_requirement=4_000,
        estimated_buying_power_effect=8_000,
        estimated_initial_margin_requirement=4_000,
        estimated_maintenance_margin_requirement=3_000,
        direct_company_negative_evidence=direct_company_negative_evidence,
        bearish_signal_sources=bearish_signal_sources,
    )


def _portfolio(*positions: PortfolioPosition) -> PortfolioContext:
    return PortfolioContext(
        as_of=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        account_equity=100_000,
        cash_balance=30_000,
        buying_power=180_000,
        excess_liquidity=60_000,
        positions=positions,
        open_strategy_exposure={},
        current_factor_exposure=(),
        stock_margin_requirement=10_000,
        option_margin_requirement=0,
        total_margin_requirement=10_000,
        approved_core_tickers=("MSFT",),
    )


def _existing_position(ticker: str, *, sector: str, market_value: float) -> PortfolioPosition:
    return PortfolioPosition(
        ticker=ticker,
        quantity=100,
        market_value=market_value,
        notional_exposure=market_value,
        trade_identity="tactical_stock_trade",
        direction="long",
        sector=sector,
        strategy_id="relative_strength_rotation_v1",
        intended_horizon="2w-3m",
        beta_bucket="high",
        volatility_bucket="high",
        liquidity_bucket="liquid",
        event_type=None,
        macro_sensitivity="consumer_cycle",
        margin_requirement=market_value * 0.5,
    )


def test_risk_manager_rejects_core_holding_without_approved_portfolio_intent():
    portfolio = _portfolio()
    config = RiskConfigResolver().resolve(
        risk_appetite=RiskAppetiteProfile.BALANCED,
        portfolio_context=portfolio,
        macro_risk_budget_multiplier=1.0,
    )
    request = _request(trade_identity="core_holding")
    sizing = PositionSizer().size_position(request, portfolio, config)

    decision = RiskManager().evaluate(request, sizing, portfolio, config)

    assert decision.status == "rejected"
    assert decision.reason_code == "core_holding_requires_portfolio_intent"


def test_risk_manager_rejects_macro_only_bearish_single_name_short():
    portfolio = _portfolio()
    config = RiskConfigResolver().resolve(
        risk_appetite=RiskAppetiteProfile.AGGRESSIVE,
        portfolio_context=portfolio,
        macro_risk_budget_multiplier=1.0,
    )
    request = _request(
        direction="bearish",
        bearish_signal_sources=("macro", "valuation"),
        direct_company_negative_evidence=False,
    )
    sizing = PositionSizer().size_position(request, portfolio, config)

    decision = RiskManager().evaluate(request, sizing, portfolio, config)

    assert decision.status == "rejected"
    assert decision.reason_code == "macro_only_bearish_single_name_blocked"


def test_risk_manager_reduces_trade_when_sector_cap_would_be_exceeded():
    portfolio = _portfolio(
        _existing_position("AMZN", sector="Consumer Discretionary", market_value=26_000)
    )
    config = RiskConfigResolver().resolve(
        risk_appetite=RiskAppetiteProfile.BALANCED,
        portfolio_context=portfolio,
        macro_risk_budget_multiplier=1.0,
    )
    request = _request()
    sizing = PositionSizer().size_position(request, portfolio, config)

    decision = RiskManager().evaluate(request, sizing, portfolio, config)

    assert decision.status == "reduced"
    assert decision.approved_weight < sizing.final_weight
    assert decision.reason_code == "sector_concentration_cap"
