from datetime import datetime, timezone

from src.trading.risk import HedgeActionRecord, PortfolioRiskIntentRecord, RiskDecisionRecord
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
