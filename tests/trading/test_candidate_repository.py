from datetime import datetime, timezone

from src.trading.outcome_evaluator import CandidateOutcomeEvaluationRecord
from src.trading.repository import InMemoryTradingRepository
from src.trading.strategy_matching import CandidateScoreRecord, StrategyDefinitionRecord, StrategyRunRecord


def test_in_memory_repository_stores_pr3_artifacts_and_filters_active_definitions():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    repo = InMemoryTradingRepository()
    active = StrategyDefinitionRecord(
        strategy_definition_id="active-id",
        strategy_id="relative_strength_rotation_v1",
        version="v1",
        display_name="Relative Strength",
        strategy_layer="tactical_pattern",
        typical_horizon="2w-3m",
        config_json={},
        lifecycle_status="active",
        is_active=True,
    )
    retired = StrategyDefinitionRecord(
        strategy_definition_id="retired-id",
        strategy_id="old_v1",
        version="v1",
        display_name="Old",
        strategy_layer="tactical_pattern",
        typical_horizon="1d",
        config_json={},
        lifecycle_status="retired",
        is_active=False,
    )
    run = StrategyRunRecord(
        strategy_run_id="run-1",
        decision_time=now,
        snapshot_type="pre_open",
        status="succeeded",
        metadata_json={},
    )
    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="active-id",
        candidate_score=0.7,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=[],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="relative strength",
        rejection_reason=None,
        benchmark_context={},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )
    outcome = CandidateOutcomeEvaluationRecord(
        candidate_outcome_evaluation_id="outcome-1",
        historical_replay_run_id=None,
        candidate_score_id="candidate-1",
        trade_classification_id=None,
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        trade_identity="watch_only",
        direction="bullish",
        catalyst_type=None,
        confidence_bucket="bucket",
        decision_time=now,
        horizon_start_at=now,
        horizon_end_at=now,
        evaluation_status="final",
        candidate_return=0.04,
        benchmark_returns={"QQQ": 0.02},
        peer_basket_id=None,
        peer_basket_return=None,
        alpha=0.02,
        max_favorable_excursion=0.05,
        max_adverse_excursion=-0.01,
        regime=None,
        sector_theme=None,
        metadata_json={},
    )

    repo.save_strategy_definition(active)
    repo.save_strategy_definition(retired)
    repo.save_strategy_run(run)
    repo.save_candidate_scores([candidate])
    repo.save_candidate_outcome_evaluations([outcome])

    assert repo.load_active_strategy_definitions() == [active]
    assert repo.strategy_runs == [run]
    assert repo.candidate_scores == [candidate]
    assert repo.candidate_outcome_evaluations == [outcome]
