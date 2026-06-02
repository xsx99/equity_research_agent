from datetime import datetime, timedelta, timezone

from src.trading.replay.outcomes import OutcomeEvaluator, PricePoint
from src.trading.strategies.matching import CandidateScoreRecord
from src.trading.strategies.classifier import TradeClassificationRecord


def _candidate() -> CandidateScoreRecord:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.7,
        direction="bullish",
        action="enter_long",
        typical_horizon="2d-4w",
        core_signal_evidence={"events_news.catalyst_type": "analyst_upgrade"},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=[],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="relative strength",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )


def _classification(candidate: CandidateScoreRecord) -> TradeClassificationRecord:
    return TradeClassificationRecord(
        trade_classification_id="classification-1",
        candidate_score_id=candidate.candidate_score_id,
        strategy_run_id=candidate.strategy_run_id,
        ticker=candidate.ticker,
        selected_strategy_id=candidate.strategy_id,
        selected_strategy_version=candidate.strategy_version,
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2d-4w",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="actionable",
        selected_strategy_context_json={},
        decision_time=candidate.decision_time,
    )


def test_outcome_evaluator_computes_returns_alpha_mfe_and_mae():
    candidate = _candidate()
    classification = _classification(candidate)
    start = candidate.decision_time
    end = start + timedelta(days=5)
    evaluator = OutcomeEvaluator(
        price_points={
            "AAPL": [
                PricePoint(start, 100),
                PricePoint(start + timedelta(days=1), 96),
                PricePoint(start + timedelta(days=2), 112),
                PricePoint(end, 110),
            ],
            "QQQ": [PricePoint(start, 400), PricePoint(end, 412)],
            "SPY": [PricePoint(start, 500), PricePoint(end, 510)],
        }
    )

    outcome = evaluator.evaluate(
        candidate,
        classification,
        horizon_start_at=start,
        horizon_end_at=end,
        benchmark_symbols=("QQQ", "SPY"),
    )

    assert outcome.candidate_return == 0.1
    assert outcome.benchmark_returns == {"QQQ": 0.03, "SPY": 0.02}
    assert outcome.alpha == 0.07
    assert outcome.max_favorable_excursion == 0.12
    assert outcome.max_adverse_excursion == -0.04
    assert outcome.evaluation_status == "final"
    assert outcome.trade_identity == "tactical_stock_trade"
