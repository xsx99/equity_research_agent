from datetime import datetime, timezone

from src.trading.strategies.selector import PrimaryStrategySelector
from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord


def _candidate(strategy_id: str, score: float, *, rejection_reason: str | None = None) -> CandidateScoreRecord:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return CandidateScoreRecord(
        candidate_score_id=f"{strategy_id}-candidate",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="AAPL",
        strategy_id=strategy_id,
        strategy_version="v1",
        strategy_definition_id=f"{strategy_id}-definition",
        candidate_score=score,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"technical.rs_vs_spy_1d": 0.02},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["relative strength breaks"],
        risk_tags=["relative_strength"],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="relative strength confirmed",
        rejection_reason=rejection_reason,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )


def _expression(expression_id: str, default_trade_identity: str = "tactical_stock_trade") -> StrategyDefinitionRecord:
    return StrategyDefinitionRecord(
        strategy_definition_id=f"{expression_id}-uuid",
        strategy_id=expression_id,
        version="v1",
        display_name=expression_id,
        strategy_layer="expression_bucket",
        typical_horizon="intraday-3m",
        config_json={
            "default_trade_identity": default_trade_identity,
            "default_exit_policy": "strategy_invalidators_or_target_horizon",
        },
        lifecycle_status="active",
        is_active=True,
    )


def test_primary_strategy_selector_chooses_best_non_rejected_candidate_and_expression_bucket():
    selected = PrimaryStrategySelector().select(
        [
            _candidate("weaker_v1", 0.51),
            _candidate("blocked_v1", 0.95, rejection_reason="direct_negative_catalyst"),
            _candidate("stronger_v1", 0.78),
        ],
        [_expression("long_stock")],
    )

    assert len(selected) == 1
    primary = selected[0]
    assert primary.strategy_id == "stronger_v1"
    assert primary.expression_bucket_id == "long_stock"
    assert primary.expression_bucket_version == "v1"
    assert primary.selection_context["candidate_score_id"] == "stronger_v1-candidate"
    assert primary.selection_context["candidate_score"] == 0.78


def test_primary_strategy_selector_keeps_high_potential_manual_watch_when_no_actionable_candidate():
    selected = PrimaryStrategySelector().select(
        [
            _candidate("manual_watch_v1", 0.62, rejection_reason="no_clean_entry"),
        ],
        [_expression("long_stock")],
    )

    assert len(selected) == 1
    assert selected[0].strategy_id == "manual_watch_v1"
    assert selected[0].selection_context["rejection_reason"] == "no_clean_entry"
