from datetime import datetime, timezone
from types import SimpleNamespace

from src.trading.risk import (
    HedgeActionRecord,
    PortfolioContext,
    PortfolioRiskIntentRecord,
    RiskAppetiteProfile,
    RiskConfigResolver,
    RiskDecisionRecord,
)
from src.trading.runtime.lookahead_risk import LookaheadRiskWorkflowHelper


def _risk_decision(
    *,
    ticker: str,
    approved_notional: float,
    metadata_json: dict[str, object] | None = None,
) -> RiskDecisionRecord:
    return RiskDecisionRecord.create(
        candidate_score_id=f"candidate-{ticker}",
        trade_classification_id=f"classification-{ticker}",
        position_sizing_decision_id=f"sizing-{ticker}",
        ticker=ticker,
        status="approved",
        reason_code="within_limits",
        approved_weight=0.05,
        approved_notional=approved_notional,
        approved_quantity=1.0,
        portfolio_risk_snapshot_id="snapshot-1",
        applied_rules=["single_name_limit_ok"],
        decision_time=datetime(2026, 6, 14, 13, 0, tzinfo=timezone.utc),
        metadata_json=metadata_json,
    )


def test_lookahead_helper_prefers_option_exposure_metadata_for_protected_notional():
    helper = LookaheadRiskWorkflowHelper()
    option_decision = _risk_decision(
        ticker="NVDA",
        approved_notional=2_500.0,
        metadata_json={
            "approved_capital_notional": 2_500.0,
            "approved_margin_exposure": 4_321.0,
            "approved_assignment_notional": 10_000.0,
        },
    )
    stock_decision = _risk_decision(
        ticker="AAPL",
        approved_notional=3_000.0,
        metadata_json={"approved_capital_notional": 3_000.0},
    )
    intent = PortfolioRiskIntentRecord.create(
        decision_time=datetime(2026, 6, 14, 13, 0, tzinfo=timezone.utc),
        risk_window="1-5d",
        aggregate_risk_state="macro_high_risk",
        hedge_actions=(
            HedgeActionRecord(
                action="open_hedge",
                risk_source="macro",
                severity="high",
                target_underlier="QQQ",
                target_exposure_type="broad_market",
                coverage_ratio=0.5,
                reason_code="macro_high_overlay",
            ),
        ),
    )

    materialized = helper.materialize_generated_hedges(
        risk_decisions=(option_decision, stock_decision),
        portfolio_risk_intent=intent,
    )

    assert materialized[0].generated_hedge_action is not None
    assert materialized[0].generated_hedge_action["protected_exposure_basis"] == "approved_margin_exposure"
    assert materialized[0].generated_hedge_action["protected_notional"] == 3660.5


def test_lookahead_helper_uses_assignment_exposure_when_target_exposure_type_is_assignment():
    helper = LookaheadRiskWorkflowHelper()
    option_decision = _risk_decision(
        ticker="NVDA",
        approved_notional=2_500.0,
        metadata_json={
            "approved_capital_notional": 2_500.0,
            "approved_margin_exposure": 4_321.0,
            "approved_assignment_notional": 12_000.0,
        },
    )
    intent = PortfolioRiskIntentRecord.create(
        decision_time=datetime(2026, 6, 14, 13, 0, tzinfo=timezone.utc),
        risk_window="1-5d",
        aggregate_risk_state="assignment_risk",
        hedge_actions=(
            HedgeActionRecord(
                action="open_hedge",
                risk_source="assignment",
                severity="high",
                target_underlier="NVDA",
                target_exposure_type="assignment",
                coverage_ratio=0.5,
                reason_code="assignment_overlay",
            ),
        ),
    )

    materialized = helper.materialize_generated_hedges(
        risk_decisions=(option_decision,),
        portfolio_risk_intent=intent,
    )

    assert materialized[0].generated_hedge_action is not None
    assert materialized[0].generated_hedge_action["protected_exposure_basis"] == "approved_assignment_notional"
    assert materialized[0].generated_hedge_action["protected_notional"] == 6000.0


def test_lookahead_helper_materializes_close_hedge_for_assignment_target_without_positive_assignment_exposure():
    helper = LookaheadRiskWorkflowHelper()
    stock_decision = _risk_decision(
        ticker="AAPL",
        approved_notional=3_000.0,
        metadata_json={"approved_capital_notional": 3_000.0},
    )
    intent = PortfolioRiskIntentRecord.create(
        decision_time=datetime(2026, 6, 14, 13, 0, tzinfo=timezone.utc),
        risk_window="1-5d",
        aggregate_risk_state="risk_normalized",
        hedge_actions=(
            HedgeActionRecord(
                action="close_hedge",
                risk_source="assignment",
                severity="watch",
                target_underlier="QQQ",
                target_exposure_type="assignment",
                coverage_ratio=1.0,
                reason_code="assignment_overlay_normalized",
                metadata_json={
                    "option_strategy_type": "long_call",
                    "existing_protected_notional": 15_000.0,
                },
            ),
        ),
    )

    materialized = helper.materialize_generated_hedges(
        risk_decisions=(stock_decision,),
        portfolio_risk_intent=intent,
    )

    assert materialized[0].generated_hedge_action is not None
    assert materialized[0].generated_hedge_action["action"] == "close_hedge"
    assert materialized[0].generated_hedge_action["option_strategy_type"] == "long_call"
    assert materialized[0].generated_hedge_action["protected_notional"] == 15000.0


def test_lookahead_helper_blocks_tactical_open_from_events_news_earnings_proximity():
    decision_time = datetime(2026, 6, 14, 13, 0, tzinfo=timezone.utc)
    portfolio_context = PortfolioContext(
        as_of=decision_time,
        account_equity=100_000,
        cash_balance=40_000,
        buying_power=180_000,
        excess_liquidity=70_000,
        positions=(),
        open_strategy_exposure={},
        current_factor_exposure=(),
        stock_margin_requirement=0,
        option_margin_requirement=0,
        total_margin_requirement=0,
    )
    config = RiskConfigResolver().resolve(
        risk_appetite=RiskAppetiteProfile.BALANCED,
        portfolio_context=portfolio_context,
        macro_risk_budget_multiplier=1.0,
    )
    helper = LookaheadRiskWorkflowHelper()

    intent = helper.build_preopen_portfolio_risk_intent(
        candidates=(
            SimpleNamespace(
                candidate_score_id="candidate-ASAN",
                signal_snapshot_id="snapshot-ASAN",
                ticker="ASAN",
            ),
        ),
        classifications=(
            SimpleNamespace(
                candidate_score_id="candidate-ASAN",
                trade_identity="tactical_stock_trade",
            ),
        ),
        signal_by_id={
            "snapshot-ASAN": SimpleNamespace(
                signal_json={
                    "events_news": {"earnings_in_days": 2},
                    "fundamental": {"sector": "Technology"},
                }
            )
        },
        portfolio_context=portfolio_context,
        config=config,
        decision_time=decision_time,
        portfolio_risk_snapshot_id="risk-snapshot-1",
    )

    assert intent.position_actions[0].ticker == "ASAN"
    assert intent.position_actions[0].action == "block_open"
    assert intent.position_actions[0].reason_code == "own_event_block"
