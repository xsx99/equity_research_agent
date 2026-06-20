from datetime import datetime, timezone

from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.signals.event_news import build_event_news_signals
from src.trading.signals.source_ingestion import SourceIngestionService
from src.trading.signals.sources import InMemorySignalSourceRepository, source_record_from_event_news_item
from src.trading.signals import SignalSnapshotResult
from src.trading.learning.apply import LearningAdjustments
from src.trading.strategies.matching import StrategyDefinitionRecord, StrategyMatcher


def _snapshot(
    *,
    ticker: str = "AAPL",
    selection_source: str = "scanner",
    manual_request_id: str | None = None,
    technical: dict | None = None,
    fundamental: dict | None = None,
    events_news: dict | None = None,
    insider: dict | None = None,
    social_macro: dict | None = None,
    macro: dict | None = None,
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
            "insider": insider or {},
            "social_macro": social_macro or {},
            "macro": macro or {},
        },
        source_freshness_json={
            "technical": "fresh",
            "fundamental": "fresh",
            "events_news": "fresh",
            "insider": "fresh",
            "social_macro": "fresh",
        },
        missing_signals_json=missing or ["option_chain_availability", "full_transcript_interpretation"],
        stale_signals_json=[],
        source_record_refs_json=[{"source_record_id": "bars-1", "source_family": "technical"}],
        source_available_times_json={"bars-1": now.isoformat()},
        excluded_future_source_count=0,
        point_in_time_passed=True,
        selection_source=selection_source,
        manual_request_id=manual_request_id,
    )


def _definition(
    strategy_id: str,
    *,
    required_signals: list[str] | None = None,
    selection_policy: dict | None = None,
    macro_blocked_regimes: list[str] | None = None,
) -> StrategyDefinitionRecord:
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
            "selection_policy": selection_policy or {},
            "macro_blocked_regimes": macro_blocked_regimes or [],
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


def test_candidate_is_not_actionable_when_missing_required_signals():
    snapshot = _snapshot(
        technical={"rs_vs_spy_1d": 0.02},
        events_news={
            "sentiment_direction": "positive",
            "high_signal_news_count_24h": 1,
            "catalyst_quality_score": 0.9,
        },
    )

    candidates = StrategyMatcher().match_snapshot(
        snapshot,
        [_definition("strong_theme_catalyst_continuation_v1")],
        strategy_run_id="run-1",
    )

    assert len(candidates) == 1
    assert candidates[0].missing_required_signals == ["technical.relative_volume"]
    assert candidates[0].candidate_status == "watch"
    assert candidates[0].is_actionable is False


def test_strategy_matcher_preserves_falsey_required_signal_values():
    snapshot = _snapshot(technical={"relative_volume": 0.0})
    definition = _definition(
        "zero_is_valid_signal_v1",
        required_signals=["technical.relative_volume"],
    )

    candidates = StrategyMatcher().match_snapshot(snapshot, [definition], strategy_run_id="run-1")

    assert len(candidates) == 1
    assert candidates[0].core_signal_evidence["technical.relative_volume"] == 0.0
    assert candidates[0].missing_required_signals == []


def test_strategy_matcher_uses_configured_default_action_and_direction():
    snapshot = _snapshot(technical={"relative_volume": 1.5})
    definition = _definition(
        "risk_reduction_v1",
        required_signals=["technical.relative_volume"],
        selection_policy={
            "default_candidate_action": "trim",
            "default_candidate_direction": "risk_warning",
            "actionable_score_threshold": 0.5,
        },
    )

    candidates = StrategyMatcher().match_snapshot(snapshot, [definition], strategy_run_id="run-1")

    assert len(candidates) == 1
    assert candidates[0].action == "trim"
    assert candidates[0].direction == "risk_warning"


def test_strategy_matcher_blocks_candidate_when_macro_regime_is_disallowed():
    snapshot = _snapshot(
        technical={"relative_volume": 1.5},
        macro={"regime": "stressed"},
    )
    definition = _definition(
        "macro_sensitive_v1",
        required_signals=["technical.relative_volume"],
        macro_blocked_regimes=["stressed"],
    )

    candidates = StrategyMatcher().match_snapshot(snapshot, [definition], strategy_run_id="run-1")

    assert len(candidates) == 1
    assert candidates[0].macro_compatibility == "blocked"
    assert candidates[0].candidate_status == "blocked"
    assert candidates[0].is_actionable is False


def test_strategy_matcher_scores_insider_accumulation_momentum_candidates():
    snapshot = _snapshot(
        technical={"relative_volume": 1.7, "rs_vs_spy_1d": 0.022, "return_20d": 0.11},
        insider={
            "purchase_count_30d": 2,
            "sale_count_30d": 0,
            "insider_net_buy_value_30d": 350000.0,
            "insider_net_buy_value_90d": 350000.0,
            "insider_cluster_buy_count_90d": 2,
            "officer_buy_flag": True,
            "director_buy_flag": True,
            "sale_concentration_score": 0.0,
            "recent_form4_filing_at": "2026-06-01T12:00:00+00:00",
        },
    )

    candidates = StrategyMatcher().match_snapshot(
        snapshot,
        [_definition("insider_accumulation_momentum_v1")],
        strategy_run_id="run-1",
    )

    assert len(candidates) == 1
    assert candidates[0].strategy_id == "insider_accumulation_momentum_v1"
    assert candidates[0].candidate_score >= 0.55
    assert candidates[0].rejection_reason is None
    assert candidates[0].core_signal_evidence["insider.insider_cluster_buy_count_90d"] == 2


def test_strategy_matcher_uses_insider_confirmation_as_bounded_modifier():
    base_snapshot = _snapshot(
        technical={"relative_volume": 1.6, "rs_vs_spy_1d": 0.018, "rs_vs_qqq_1d": 0.011},
        fundamental={"quality_score": 0.8},
        events_news={"sentiment_direction": "positive", "high_signal_news_count_24h": 1, "catalyst_quality_score": 0.8},
    )
    insider_snapshot = _snapshot(
        technical={"relative_volume": 1.6, "rs_vs_spy_1d": 0.018, "rs_vs_qqq_1d": 0.011},
        fundamental={"quality_score": 0.8},
        events_news={"sentiment_direction": "positive", "high_signal_news_count_24h": 1, "catalyst_quality_score": 0.8},
        insider={"insider_net_buy_value_30d": 300000.0, "insider_cluster_buy_count_90d": 2, "officer_buy_flag": True},
    )

    base_candidate = StrategyMatcher().match_snapshot(
        base_snapshot,
        [_definition("strong_theme_catalyst_continuation_v1")],
        strategy_run_id="run-1",
    )[0]
    insider_candidate = StrategyMatcher().match_snapshot(
        insider_snapshot,
        [_definition("strong_theme_catalyst_continuation_v1")],
        strategy_run_id="run-1",
    )[0]

    assert insider_candidate.candidate_score > base_candidate.candidate_score
    assert insider_candidate.candidate_score - base_candidate.candidate_score <= 0.15


def test_social_macro_headwind_downgrades_candidate_without_creating_macro_only_short():
    base_snapshot = _snapshot(
        technical={"relative_volume": 1.7, "rs_vs_spy_1d": 0.02, "rs_vs_qqq_1d": 0.013},
        fundamental={"quality_score": 0.8},
        events_news={"sentiment_direction": "positive", "high_signal_news_count_24h": 1, "catalyst_quality_score": 0.85},
    )
    headwind_snapshot = _snapshot(
        technical={"relative_volume": 1.7, "rs_vs_spy_1d": 0.02, "rs_vs_qqq_1d": 0.013},
        fundamental={"quality_score": 0.8},
        events_news={"sentiment_direction": "positive", "high_signal_news_count_24h": 1, "catalyst_quality_score": 0.85},
        social_macro={
            "policy_headwind_flag": True,
            "policy_tailwind_flag": False,
            "social_macro_importance_score": 0.95,
            "social_macro_sentiment_direction": "negative",
            "explicit_ticker_mention_flag": True,
        },
    )

    base_candidate = StrategyMatcher().match_snapshot(
        base_snapshot,
        [_definition("strong_theme_catalyst_continuation_v1")],
        strategy_run_id="run-1",
    )[0]
    headwind_candidate = StrategyMatcher().match_snapshot(
        headwind_snapshot,
        [_definition("strong_theme_catalyst_continuation_v1")],
        strategy_run_id="run-1",
    )[0]

    assert headwind_candidate.candidate_score < base_candidate.candidate_score
    assert headwind_candidate.direction != "bearish"
    assert headwind_candidate.action in {"enter_long", "no_trade"}


class _DuplicateNewsProvider:
    def fetch_recent(self, ticker: str, limit: int):
        return [
            {
                "title": "Morgan Stanley upgrades Apple to Overweight, target to $180",
                "summary": "The analyst cited stronger iPhone demand.",
                "published_at": "2026-06-01T10:00:00+00:00",
                "source": "Reuters",
                "url": "https://example.test/reuters-upgrade",
                "signal_type": "analyst_rating",
            },
            {
                "title": "Apple upgraded to Overweight at Morgan Stanley; PT raised to $180",
                "summary": "Demand checks improved and the broker lifted its target.",
                "published_at": "2026-06-01T10:05:00+00:00",
                "source": "Dow Jones",
                "url": "https://example.test/dj-upgrade",
                "signal_type": "analyst_rating",
            },
        ]


class _NoopMarketProvider:
    def fetch_daily_bars(self, ticker: str, lookback_days: int):
        return []

    def fetch_context(self, ticker: str):
        return {}


def test_strategy_matcher_score_is_not_inflated_by_duplicate_news_volume_after_condensation():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    source_repository = InMemorySignalSourceRepository()
    artifact_repository = InMemoryTradingRepository()
    ingestion = SourceIngestionService(
        market_provider=_NoopMarketProvider(),
        news_provider=_DuplicateNewsProvider(),
        source_repository=source_repository,
        artifact_repository=artifact_repository,
        provider_name="fixture",
        now=lambda: now,
        sleeper=lambda seconds: None,
    )
    result = ingestion.refresh_tickers(("AAPL",), as_of=now, run_type="targeted", source_families=("events_news",))
    signals = build_event_news_signals(
        tuple(source_record_from_event_news_item(item) for item in result.event_news_items),
        decision_time=now,
    )
    snapshot = _snapshot(
        events_news=signals.values,
        technical={"rs_vs_spy_1d": 0.018, "relative_volume": 1.8},
        fundamental={"quality_score": 0.82},
    )

    candidates = StrategyMatcher().match_snapshot(
        snapshot,
        [_definition("strong_theme_catalyst_continuation_v1")],
        strategy_run_id="run-1",
    )

    assert len(result.event_news_items) == 1
    assert signals.values["high_signal_news_count_24h"] == 1
    assert candidates[0].core_signal_evidence["events_news.high_signal_news_count_24h"] == 1


def test_strategy_matcher_applies_learning_factor_score_multiplier():
    snapshot = _snapshot(
        technical={"relative_volume": 1.8, "rs_vs_spy_1d": 0.022, "return_20d": 0.11},
        events_news={
            "sentiment_direction": "positive",
            "high_signal_news_count_24h": 1,
            "catalyst_quality_score": 0.9,
            "direct_negative_catalyst_type": None,
        },
    )
    definition = _definition("relative_strength_rotation_v1")

    base_candidate = StrategyMatcher().match_snapshot(snapshot, [definition], strategy_run_id="run-1")[0]
    adjusted_candidate = StrategyMatcher(
        learning_adjustments=LearningAdjustments(
            strategy_score_multiplier={"relative_strength_rotation_v1": 1.1},
            risk_budget_multiplier=1.0,
            applied_factor_keys=("lf-1",),
            shadow_factor_keys=(),
        )
    ).match_snapshot(snapshot, [definition], strategy_run_id="run-2")[0]

    assert adjusted_candidate.candidate_score > base_candidate.candidate_score
