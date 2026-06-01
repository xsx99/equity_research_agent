from datetime import datetime, timedelta, timezone

from src.trading.historical_replay import HistoricalReplayRunner
from src.trading.outcome_evaluator import OutcomeEvaluator, PricePoint
from src.trading.repository import InMemoryTradingRepository
from src.trading.signals import SignalSnapshotResult
from src.trading.strategy_matching import StrategyDefinitionRecord


def _snapshot(snapshot_id: str, available_at: datetime, *, return_20d: float) -> SignalSnapshotResult:
    decision_time = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return SignalSnapshotResult(
        signal_snapshot_id=snapshot_id,
        ticker="AAPL",
        snapshot_type="pre_open",
        decision_time=decision_time,
        available_for_decision_at=available_at,
        max_input_available_for_decision_at=available_at,
        signal_json={
            "technical": {
                "return_20d": return_20d,
                "relative_volume": 1.6,
                "rs_vs_spy_1d": 0.02,
                "rs_vs_qqq_1d": 0.01,
                "dollar_volume": 90_000_000,
            },
            "fundamental": {"quality_score": 0.7},
            "events_news": {"sentiment_direction": "positive", "direct_negative_catalyst_type": None},
        },
        source_freshness_json={"technical": "fresh"},
        missing_signals_json=[],
        stale_signals_json=[],
        source_record_refs_json=[{"source_record_id": snapshot_id}],
        source_available_times_json={snapshot_id: available_at.isoformat()},
        excluded_future_source_count=0,
        point_in_time_passed=True,
    )


def _definition() -> StrategyDefinitionRecord:
    return StrategyDefinitionRecord(
        strategy_definition_id="relative-strength-definition",
        strategy_id="relative_strength_rotation_v1",
        version="v1",
        display_name="Relative Strength Rotation",
        strategy_layer="tactical_pattern",
        typical_horizon="2w-3m",
        config_json={"required_signals": []},
        lifecycle_status="active",
        is_active=True,
    )


def test_historical_replay_reconstructs_candidates_only_from_decision_available_snapshots():
    decision_time = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    repo = InMemoryTradingRepository()
    repo.save_signal_snapshot(_snapshot("old-snapshot", decision_time, return_20d=0.08))
    repo.save_signal_snapshot(_snapshot("future-snapshot", decision_time + timedelta(minutes=5), return_20d=0.30))
    repo.save_strategy_definition(_definition())
    evaluator = OutcomeEvaluator(
        price_points={
            "AAPL": [PricePoint(decision_time, 100), PricePoint(decision_time + timedelta(days=5), 108)],
            "QQQ": [PricePoint(decision_time, 400), PricePoint(decision_time + timedelta(days=5), 408)],
            "SPY": [PricePoint(decision_time, 500), PricePoint(decision_time + timedelta(days=5), 505)],
        }
    )

    result = HistoricalReplayRunner(repository=repo, outcome_evaluator=evaluator).run(
        decision_time=decision_time,
        horizon_end_at=decision_time + timedelta(days=5),
    )

    assert result.replay_run.decision_time == decision_time
    assert [candidate.signal_snapshot_id for candidate in result.candidates] == ["old-snapshot"]
    assert repo.historical_replay_runs == [result.replay_run]
    assert repo.candidate_outcome_evaluations == list(result.outcomes)
    assert result.outcomes[0].candidate_return == 0.08
