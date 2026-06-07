from datetime import datetime, timezone

from src.trading.strategies.selector import PrimaryStrategySelector, PrimarySelectionResult
from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord


def _candidate(
    strategy_id: str,
    score: float,
    *,
    action: str = "enter_long",
    direction: str = "bullish",
    candidate_status: str = "actionable",
    evidence: dict | None = None,
    rejection_reason: str | None = None,
) -> CandidateScoreRecord:
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
        direction=direction,
        action=action,
        typical_horizon="2w-3m",
        core_signal_evidence=evidence or {"technical.rs_vs_spy_1d": 0.02},
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
        candidate_status=candidate_status,
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


def _strategy(
    strategy_id: str,
    *,
    eligible_expression_bucket_ids: list[str] | None = None,
) -> StrategyDefinitionRecord:
    return StrategyDefinitionRecord(
        strategy_definition_id=f"{strategy_id}-definition",
        strategy_id=strategy_id,
        version="v1",
        display_name=strategy_id,
        strategy_layer="tactical_pattern",
        typical_horizon="2w-3m",
        config_json={
            "selection_policy": {
                "eligible_expression_bucket_ids": eligible_expression_bucket_ids or [],
            }
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
        [
            _strategy("weaker_v1", eligible_expression_bucket_ids=["long_stock"]),
            _strategy("blocked_v1", eligible_expression_bucket_ids=["long_stock"]),
            _strategy("stronger_v1", eligible_expression_bucket_ids=["long_stock"]),
            _expression("long_stock"),
        ],
    )

    assert isinstance(selected, PrimarySelectionResult)
    assert len(selected.selected_trades) == 1
    assert selected.watch_candidates == ()
    primary = selected.selected_trades[0]
    assert primary.strategy_id == "stronger_v1"
    assert primary.expression_bucket_id == "long_stock"
    assert primary.expression_bucket_version == "v1"
    assert primary.selection_context["candidate_score_id"] == "stronger_v1-candidate"
    assert primary.selection_context["candidate_score"] == 0.78


def test_selector_returns_selected_trades_and_watch_candidates_separately():
    selected = PrimaryStrategySelector().select(
        [
            _candidate("trade_v1", 0.81),
            _candidate(
                "watch_v1",
                0.64,
                action="no_trade",
                direction="neutral",
                candidate_status="watch",
                evidence={"events_news.catalyst_quality_score": 0.92},
                rejection_reason="no_clean_entry",
            ),
        ],
        [
            _strategy("trade_v1", eligible_expression_bucket_ids=["long_stock"]),
            _strategy("watch_v1", eligible_expression_bucket_ids=["defined_risk_income_spread"]),
            _expression("long_stock"),
            _expression("defined_risk_income_spread", default_trade_identity="tactical_option_trade"),
        ],
    )

    assert len(selected.selected_trades) == 1
    assert selected.selected_trades[0].strategy_id == "trade_v1"
    assert len(selected.watch_candidates) == 1
    assert selected.watch_candidates[0].watch_strategy_id == "watch_v1"
    assert selected.watch_candidates[0].result_status == "catalyst_watch"


def test_selector_does_not_assign_long_stock_to_watch_candidates():
    selected = PrimaryStrategySelector().select(
        [
            _candidate(
                "manual_watch_v1",
                0.62,
                action="no_trade",
                direction="neutral",
                candidate_status="watch",
                evidence={"events_news.catalyst_quality_score": 0.91},
                rejection_reason="no_clean_entry",
            ),
        ],
        [
            _strategy("manual_watch_v1", eligible_expression_bucket_ids=["defined_risk_income_spread"]),
            _expression("long_stock"),
            _expression("defined_risk_income_spread", default_trade_identity="tactical_option_trade"),
        ],
    )

    assert selected.selected_trades == ()
    assert len(selected.watch_candidates) == 1
    assert not hasattr(selected.watch_candidates[0], "expression_bucket_id")
    assert selected.watch_candidates[0].watch_strategy_id == "manual_watch_v1"
    assert selected.watch_candidates[0].watch_type == "catalyst_watch"


def test_selector_requires_explicit_expression_bucket_mapping():
    selected = PrimaryStrategySelector().select(
        [_candidate("unmapped_v1", 0.78)],
        [
            _strategy("unmapped_v1", eligible_expression_bucket_ids=[]),
            _expression("long_stock"),
        ],
    )

    assert selected.selected_trades == ()
    assert len(selected.watch_candidates) == 1
    assert selected.watch_candidates[0].watch_strategy_id == "unmapped_v1"
    assert selected.watch_candidates[0].result_status == "ordinary_watch"
