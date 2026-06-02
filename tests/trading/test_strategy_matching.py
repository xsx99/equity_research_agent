from datetime import datetime, timezone

from src.trading.signals import SignalSnapshotResult
from src.trading.strategies.matching import StrategyDefinitionRecord, StrategyMatcher


def _snapshot(
    *,
    ticker: str = "AAPL",
    selection_source: str = "scanner",
    manual_request_id: str | None = None,
    technical: dict | None = None,
    fundamental: dict | None = None,
    events_news: dict | None = None,
    missing: list[str] | None = None,
) -> SignalSnapshotResult:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return SignalSnapshotResult(
        signal_snapshot_id=f"{ticker}-snapshot",
        ticker=ticker,
        snapshot_type="pre_open",
        decision_time=now,
        available_for_decision_at=now,
        max_input_available_for_decision_at=now,
        signal_json={
            "technical": technical or {},
            "fundamental": fundamental or {},
            "events_news": events_news or {},
        },
        source_freshness_json={"technical": "fresh", "fundamental": "fresh", "events_news": "fresh"},
        missing_signals_json=missing or ["option_chain_availability", "full_transcript_interpretation"],
        stale_signals_json=[],
        source_record_refs_json=[{"source_record_id": "bars-1", "source_family": "technical"}],
        source_available_times_json={"bars-1": now.isoformat()},
        excluded_future_source_count=0,
        point_in_time_passed=True,
        selection_source=selection_source,
        manual_request_id=manual_request_id,
    )


def _definition(strategy_id: str, *, required_signals: list[str] | None = None) -> StrategyDefinitionRecord:
    return StrategyDefinitionRecord(
        strategy_definition_id=f"{strategy_id}-uuid",
        strategy_id=strategy_id,
        version="v1",
        display_name=strategy_id,
        strategy_layer="tactical_pattern",
        typical_horizon="2w-3m",
        config_json={
            "required_signals": required_signals or [],
            "risk_tags": ["relative_strength"],
            "invalidators": ["relative strength breaks"],
        },
        lifecycle_status="active",
        is_active=True,
    )


def test_strategy_matcher_scores_supported_pr2_signal_families_without_lookahead():
    snapshot = _snapshot(
        selection_source="manual_request",
        manual_request_id="request-1",
        technical={
            "return_20d": 0.12,
            "relative_volume": 1.8,
            "dollar_volume": 90_000_000,
            "rs_vs_spy_1d": 0.018,
            "rs_vs_qqq_1d": 0.011,
            "price_vs_sma_20": 0.04,
        },
        fundamental={"quality_score": 0.82, "revenue_growth_score": 0.72, "valuation_percentile": 0.48},
        events_news={
            "sentiment_direction": "positive",
            "high_signal_news_count_24h": 1,
            "catalyst_quality_score": 0.9,
            "direct_negative_catalyst_type": None,
        },
    )

    candidates = StrategyMatcher().match_snapshot(
        snapshot,
        [_definition("strong_theme_catalyst_continuation_v1")],
        strategy_run_id="run-1",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.ticker == "AAPL"
    assert candidate.strategy_id == "strong_theme_catalyst_continuation_v1"
    assert candidate.selection_source == "manual_request"
    assert candidate.manual_request_id == "request-1"
    assert candidate.rejection_reason is None
    assert 0.5 <= candidate.candidate_score <= 1
    assert candidate.core_signal_evidence["events_news.catalyst_quality_score"] == 0.9
    assert candidate.source_record_refs_json == [{"source_record_id": "bars-1", "source_family": "technical"}]


def test_strategy_matcher_preserves_rejection_for_company_level_negative_catalyst():
    snapshot = _snapshot(
        technical={"return_20d": 0.07, "relative_volume": 1.4, "rs_vs_spy_1d": 0.02},
        events_news={
            "sentiment_direction": "negative",
            "direct_negative_catalyst_type": "regulatory_investigation",
            "high_signal_news_count_24h": 1,
            "catalyst_quality_score": 0.8,
        },
    )

    candidates = StrategyMatcher().match_snapshot(
        snapshot,
        [_definition("relative_strength_rotation_v1")],
        strategy_run_id="run-1",
    )

    assert len(candidates) == 1
    assert candidates[0].rejection_reason == "direct_negative_catalyst"
    assert candidates[0].direction == "risk_warning"


def test_strategy_matcher_marks_deferred_source_family_strategies_as_unsupported():
    snapshot = _snapshot(
        events_news={
            "own_earnings_event_type": "own_earnings_beat_raise",
            "sentiment_direction": "positive",
            "catalyst_quality_score": 0.9,
        },
        missing=["full_transcript_interpretation"],
    )
    definition = _definition(
        "earnings_drift_v1",
        required_signals=["own_transcript_sentiment_score", "own_post_earnings_analyst_revision_count"],
    )

    candidates = StrategyMatcher().match_snapshot(snapshot, [definition], strategy_run_id="run-1")

    assert len(candidates) == 1
    assert candidates[0].rejection_reason == "unsupported_missing_signal_family"
    assert candidates[0].unsupported_missing_signal_families == [
        "full_transcript_interpretation",
    ]
