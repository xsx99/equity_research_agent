from datetime import datetime, timezone

from src.trading.portfolio.intents import PortfolioIntentConfig
from src.trading.strategies.selector import SelectedTradeRecord, advance_selected_trade_expression
from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord
from src.trading.strategies.classifier import TradeClassifier


def _candidate(
    *,
    ticker: str = "AAPL",
    score: float = 0.72,
    action: str = "enter_long",
    direction: str = "bullish",
    candidate_status: str = "actionable",
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
        direction=direction,
        action=action,
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
        candidate_status=candidate_status,
    )


def _selected(candidate: CandidateScoreRecord, expression_bucket_id: str = "long_stock") -> SelectedTradeRecord:
    if expression_bucket_id == "core_stock_accumulation":
        default_trade_identity = "core_holding"
    elif expression_bucket_id in {
        "defined_risk_directional_option",
        "defined_risk_income_spread",
        "volatility_event_option",
    }:
        default_trade_identity = "tactical_option_trade"
    else:
        default_trade_identity = "tactical_stock_trade"
    return SelectedTradeRecord(
        candidate=candidate,
        selected_expression_bucket_id=expression_bucket_id,
        selected_expression_bucket_version="v1",
        selected_expression_bucket_config={
            "default_trade_identity": default_trade_identity,
            "default_exit_policy": "strategy_invalidators_or_target_horizon",
        },
        fallback_expression_bucket_ids=("defined_risk_directional_option",)
        if expression_bucket_id == "long_stock"
        else ("long_stock",),
        expression_selection_context={
            "selected_expression_bucket_id": expression_bucket_id,
            "fallback_expression_bucket_ids": ["defined_risk_directional_option"]
            if expression_bucket_id == "long_stock"
            else ["long_stock"],
        },
        selection_context={"candidate_score_id": candidate.candidate_score_id},
    )


def _expression_definition(expression_bucket_id: str, trade_identity: str) -> StrategyDefinitionRecord:
    return StrategyDefinitionRecord(
        strategy_definition_id=f"{expression_bucket_id}-definition",
        strategy_id=expression_bucket_id,
        version="v1",
        display_name=expression_bucket_id,
        strategy_layer="expression_bucket",
        typical_horizon="2w-3m",
        config_json={
            "default_trade_identity": trade_identity,
            "default_exit_policy": "strategy_invalidators_or_target_horizon",
        },
        lifecycle_status="active",
        is_active=True,
    )


def test_trade_classifier_assigns_tactical_stock_identity_for_actionable_long_stock():
    classification = TradeClassifier().classify(_selected(_candidate()))

    assert classification.trade_identity == "tactical_stock_trade"
    assert classification.watch_type is None
    assert classification.result_status == "actionable_trade"
    assert classification.selected_strategy_id == "strong_theme_catalyst_continuation_v1"
    assert classification.expression_bucket_id == "long_stock"
    assert classification.selected_strategy_context_json["selected_expression_bucket_id"] == "long_stock"
    assert classification.selected_strategy_context_json["fallback_expression_bucket_ids"] == [
        "defined_risk_directional_option"
    ]


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


def test_trade_classifier_rejects_watch_candidate_inputs():
    selected = _selected(
        _candidate(
            score=0.64,
            action="no_trade",
            direction="neutral",
            candidate_status="watch",
            rejection_reason="no_clean_entry",
            evidence={"events_news.catalyst_quality_score": 0.95},
        )
    )

    try:
        TradeClassifier().classify(selected)
    except ValueError as exc:
        assert str(exc) == "trade_classifier_requires_actionable_selected_trade"
    else:
        raise AssertionError("expected watch-path candidate to be rejected")


def test_trade_classifier_can_reclassify_after_same_strategy_expression_fallback():
    fallback_selected = advance_selected_trade_expression(
        _selected(_candidate(), expression_bucket_id="defined_risk_directional_option"),
        [
            _expression_definition("defined_risk_directional_option", "tactical_option_trade"),
            _expression_definition("long_stock", "tactical_stock_trade"),
        ],
    )

    assert fallback_selected is not None
    classification = TradeClassifier().classify(fallback_selected)

    assert classification.trade_identity == "tactical_stock_trade"
    assert classification.expression_bucket_id == "long_stock"
    assert classification.selected_strategy_context_json["selected_expression_bucket_id"] == "long_stock"
