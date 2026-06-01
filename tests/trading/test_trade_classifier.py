from datetime import datetime, timezone

from src.trading.portfolio_intents import PortfolioIntentConfig
from src.trading.primary_strategy_selector import SelectedStrategyRecord
from src.trading.strategy_matching import CandidateScoreRecord
from src.trading.trade_classifier import TradeClassifier


def _candidate(
    *,
    ticker: str = "AAPL",
    score: float = 0.72,
    rejection_reason: str | None = None,
    evidence: dict | None = None,
) -> CandidateScoreRecord:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker=ticker,
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=score,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence=evidence or {"events_news.catalyst_quality_score": 0.9},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["price confirmation fails"],
        risk_tags=["catalyst_risk"],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="catalyst with confirmation",
        rejection_reason=rejection_reason,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )


def _selected(candidate: CandidateScoreRecord, expression_bucket_id: str = "long_stock") -> SelectedStrategyRecord:
    return SelectedStrategyRecord(
        candidate=candidate,
        expression_bucket_id=expression_bucket_id,
        expression_bucket_version="v1",
        expression_bucket_config={
            "default_trade_identity": "core_holding"
            if expression_bucket_id == "core_stock_accumulation"
            else "tactical_stock_trade",
            "default_exit_policy": "strategy_invalidators_or_target_horizon",
        },
        selection_context={"candidate_score_id": candidate.candidate_score_id},
    )


def test_trade_classifier_assigns_tactical_stock_identity_for_actionable_long_stock():
    classification = TradeClassifier().classify(_selected(_candidate()))

    assert classification.trade_identity == "tactical_stock_trade"
    assert classification.watch_type is None
    assert classification.result_status == "actionable_trade"
    assert classification.selected_strategy_id == "strong_theme_catalyst_continuation_v1"
    assert classification.expression_bucket_id == "long_stock"


def test_trade_classifier_requires_active_intent_for_core_holding_identity():
    intent = PortfolioIntentConfig(
        ticker="GOOGL",
        intent_type="core_growth",
        target_weight=0.08,
        max_weight=0.12,
        lifecycle_status="active",
        add_rules=("add_on_pullback",),
    )

    classification = TradeClassifier(portfolio_intents=[intent]).classify(
        _selected(_candidate(ticker="GOOGL"), expression_bucket_id="core_stock_accumulation")
    )

    assert classification.trade_identity == "core_holding"
    assert classification.result_status == "actionable_trade"
    assert classification.exit_policy == "strategy_invalidators_or_target_horizon"


def test_trade_classifier_downgrades_high_potential_no_entry_to_catalyst_watch():
    classification = TradeClassifier().classify(
        _selected(
            _candidate(
                score=0.64,
                rejection_reason="no_clean_entry",
                evidence={"events_news.catalyst_quality_score": 0.95},
            )
        )
    )

    assert classification.trade_identity == "watch_only"
    assert classification.watch_type == "catalyst_watch"
    assert classification.result_status == "catalyst_watch"
