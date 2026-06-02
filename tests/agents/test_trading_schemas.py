from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.agents.trading_schemas import TradingDecisionOutput, TradingDecisionOutputFallback


def test_trading_decision_output_accepts_actionable_stock_trade():
    decision = TradingDecisionOutput.model_validate(
        {
            "ticker": "NVDA",
            "decision": "enter_long",
            "strategy_id": "relative_strength_rotation_v1",
            "expression_bucket_id": "long_stock",
            "trade_identity": "tactical_stock_trade",
            "instrument_type": "stock",
            "selection_source": "scanner",
            "manual_request_id": None,
            "confidence": 0.72,
            "confidence_basis": {
                "calibration_bucket": "bullish_catalyst_relative_strength",
                "historical_win_rate": 0.58,
            },
            "benchmark_context": {
                "primary_benchmark": "QQQ",
                "peer_basket_id": "semis_ai_large_mid_2026_05_29",
            },
            "target_weight": 0.05,
            "max_loss_pct": 0.025,
            "time_horizon": "2w-3m",
            "entry_plan": "market_open",
            "exit_plan": "close_or_invalidator",
            "thesis": "Strong relative momentum with confirming volume.",
            "key_signals": ["sector_relative_strength", "relative_volume"],
            "risk_checks": ["liquidity_ok", "macro_budget_ok"],
            "invalidators": ["relative volume fades below 0.8x"],
            "learning_factors_used": ["lf_2026_05_01_momentum_chasing_filter"],
            "schema_version": "v1",
            "generated_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        }
    )

    assert decision.decision == "enter_long"
    assert decision.instrument_type == "stock"
    assert decision.trade_identity == "tactical_stock_trade"


def test_trading_decision_output_requires_valid_confidence_range():
    with pytest.raises(ValidationError):
        TradingDecisionOutput.model_validate(
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "strategy_id": "relative_strength_rotation_v1",
                "expression_bucket_id": "long_stock",
                "trade_identity": "tactical_stock_trade",
                "instrument_type": "stock",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 1.2,
                "confidence_basis": {},
                "benchmark_context": {},
                "target_weight": 0.05,
                "max_loss_pct": 0.025,
                "time_horizon": "2w-3m",
                "entry_plan": "market_open",
                "exit_plan": "close_or_invalidator",
                "thesis": "Invalid confidence should fail.",
                "key_signals": [],
                "risk_checks": [],
                "invalidators": [],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
            }
        )


def test_trading_decision_fallback_records_reason_and_action():
    fallback = TradingDecisionOutputFallback.model_validate(
        {
            "ticker": "NVDA",
            "decision": "no_trade",
            "fallback_action": "no_trade",
            "fallback_reason": "validation_failed_after_retry",
            "schema_version": "v1",
            "generated_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        }
    )

    assert fallback.fallback_action == "no_trade"
    assert fallback.fallback_reason == "validation_failed_after_retry"
