from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.trading.options.strategy import OptionLegDefinition, OptionStrategyDecisionInput, OptionsStrategyLayer


def _leg(*, side: str, option_type: str, strike: float) -> OptionLegDefinition:
    return OptionLegDefinition(
        option_type=option_type,
        side=side,
        quantity=1,
        strike=strike,
        expiry=date(2026, 7, 17),
        dte=45,
        delta=0.32,
        gamma=0.04,
        theta=-0.03,
        vega=0.12,
        iv_rank=0.61,
        bid=2.4,
        ask=2.6,
        mid=2.5,
        chosen_price=2.5,
    )


def test_options_strategy_layer_builds_whitelisted_credit_spread():
    layer = OptionsStrategyLayer()

    decision = layer.build_strategy(
        OptionStrategyDecisionInput(
            trading_decision_id="decision-1",
            ticker="NVDA",
            trade_identity="tactical_option_trade",
            option_strategy_type="put_credit_spread",
            decision_action="open_option_strategy",
            strategy_id="earnings_drift_v1",
            strategy_version="v1",
            expression_bucket_id="defined_risk_income_spread",
            expression_bucket_version="v1",
            decision_time=datetime(2026, 6, 2, 13, 30, tzinfo=timezone.utc),
            expiry=date(2026, 7, 17),
            underlying_price=118.0,
            earnings_date=date(2026, 6, 20),
            event_through_expiry=True,
            profit_target_pct=0.5,
            max_loss_rule="close_at_2x_credit",
            roll_conditions=["7_dte_if_otm"],
            close_conditions=["take_profit_50pct"],
            margin_model_profile="estimated_fidelity_like_conservative_v1",
            margin_model_version="v1",
            margin_requirement_source="simulated_formula",
            strategy_pairing_method="vertical_by_expiry_and_width",
            assignment_plan="close_or_roll_before_expiry_if_itm",
            legs=(
                _leg(side="sell", option_type="put", strike=110.0),
                _leg(side="buy", option_type="put", strike=105.0),
            ),
        )
    )

    assert decision.status == "ready"
    assert decision.option_strategy_type == "put_credit_spread"
    assert decision.net_debit_or_credit == pytest.approx(-0.0, abs=5.0)
    assert decision.max_loss > 0
    assert decision.assignment_notional == 11000.0


def test_options_strategy_layer_rejects_non_whitelisted_structure():
    layer = OptionsStrategyLayer()

    decision = layer.build_strategy(
        OptionStrategyDecisionInput(
            trading_decision_id="decision-1",
            ticker="AAPL",
            trade_identity="tactical_option_trade",
            option_strategy_type="covered_call",
            decision_action="open_option_strategy",
            strategy_id="relative_strength_rotation_v1",
            strategy_version="v1",
            expression_bucket_id="defined_risk_income_spread",
            expression_bucket_version="v1",
            decision_time=datetime(2026, 6, 2, 13, 30, tzinfo=timezone.utc),
            expiry=date(2026, 7, 17),
            underlying_price=210.0,
            earnings_date=None,
            event_through_expiry=False,
            profit_target_pct=0.5,
            max_loss_rule="close",
            roll_conditions=[],
            close_conditions=[],
            margin_model_profile="estimated_fidelity_like_conservative_v1",
            margin_model_version="v1",
            margin_requirement_source="simulated_formula",
            strategy_pairing_method="single_leg",
            assignment_plan=None,
            legs=(_leg(side="sell", option_type="call", strike=220.0),),
        )
    )

    assert decision.status == "rejected"
    assert decision.rejection_reason == "unsupported_option_strategy_type"
