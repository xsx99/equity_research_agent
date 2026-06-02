from datetime import datetime, timezone

from src.trading.risk import (
    PortfolioContext,
    RiskAppetiteProfile,
    RiskConfigResolver,
    TradeRiskRequest,
)
from src.trading.risk.sizing import PositionSizer
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord


def _candidate(score: float = 0.8) -> CandidateScoreRecord:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="strategy-def-1",
        candidate_score=score,
        direction="bullish",
        action="enter_long",
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


def _classification() -> TradeClassificationRecord:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return TradeClassificationRecord(
        trade_classification_id="classification-1",
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        ticker="AAPL",
        selected_strategy_id="relative_strength_rotation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="test",
        selected_strategy_context_json={},
        decision_time=now,
    )


def test_position_sizer_applies_volatility_and_liquidity_caps():
    portfolio = PortfolioContext(
        as_of=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        account_equity=100_000,
        cash_balance=50_000,
        buying_power=180_000,
        excess_liquidity=90_000,
        positions=(),
        open_strategy_exposure={},
        current_factor_exposure=(),
        stock_margin_requirement=0,
        option_margin_requirement=0,
        total_margin_requirement=0,
    )
    config = RiskConfigResolver().resolve(
        risk_appetite=RiskAppetiteProfile.BALANCED,
        portfolio_context=portfolio,
        macro_risk_budget_multiplier=1.0,
    )
    request = TradeRiskRequest(
        candidate=_candidate(),
        classification=_classification(),
        instrument_type="stock",
        target_weight=0.08,
        confidence=0.75,
        sector="Technology",
        beta_bucket="high",
        volatility_bucket="high",
        liquidity_bucket="thin",
        event_type=None,
        macro_sensitivity="rates_sensitive",
        price=100,
        atr_pct=0.08,
        average_daily_dollar_volume=250_000,
        signal_freshness={"technical": "fresh", "fundamental": "fresh", "events_news": "fresh"},
        estimated_margin_requirement=4_000,
        estimated_buying_power_effect=8_000,
        estimated_initial_margin_requirement=4_000,
        estimated_maintenance_margin_requirement=3_000,
    )

    decision = PositionSizer().size_position(request, portfolio, config)

    assert decision.base_weight > decision.final_weight
    assert decision.final_weight <= config.max_liquidity_weight
    assert "volatility_cap" in decision.applied_caps
    assert "liquidity_cap" in decision.applied_caps
    assert decision.final_notional == decision.final_weight * portfolio.account_equity
