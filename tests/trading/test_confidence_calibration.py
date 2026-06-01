from datetime import datetime, timezone

from src.trading.confidence_calibration import ConfidenceCalibrator
from src.trading.outcome_evaluator import CandidateOutcomeEvaluationRecord
from src.trading.trade_classifier import TradeClassificationRecord


def _classification() -> TradeClassificationRecord:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return TradeClassificationRecord(
        trade_classification_id="classification-1",
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        ticker="AAPL",
        selected_strategy_id="strong_theme_catalyst_continuation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="actionable long stock",
        selected_strategy_context_json={"catalyst_type": "analyst_upgrade"},
        decision_time=now,
    )


def _outcome(alpha: float) -> CandidateOutcomeEvaluationRecord:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    return CandidateOutcomeEvaluationRecord(
        candidate_outcome_evaluation_id=f"eval-{alpha}",
        historical_replay_run_id=None,
        candidate_score_id="candidate-old",
        trade_classification_id="classification-old",
        ticker="AAPL",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        trade_identity="tactical_stock_trade",
        direction="bullish",
        catalyst_type="analyst_upgrade",
        confidence_bucket="strong_theme_catalyst_continuation_v1|long_stock|tactical_stock_trade|bullish|analyst_upgrade",
        decision_time=now,
        horizon_start_at=now,
        horizon_end_at=now,
        evaluation_status="final",
        candidate_return=0.04 + alpha,
        benchmark_returns={"QQQ": 0.04},
        peer_basket_id=None,
        peer_basket_return=None,
        alpha=alpha,
        max_favorable_excursion=0.07,
        max_adverse_excursion=-0.02,
        regime=None,
        sector_theme=None,
        metadata_json={},
    )


def test_confidence_calibrator_builds_bucket_and_uses_historical_outcomes():
    result = ConfidenceCalibrator([_outcome(0.03), _outcome(-0.01)]).calibrate(_classification())

    assert result.confidence_bucket == (
        "strong_theme_catalyst_continuation_v1|long_stock|"
        "tactical_stock_trade|bullish|analyst_upgrade"
    )
    assert result.sample_count == 2
    assert result.win_rate == 0.5
    assert result.average_alpha == 0.01
    assert 0 <= result.calibrated_confidence <= 1
