from __future__ import annotations

from datetime import date, datetime, timezone

from src.agents.prompt_registry import PromptRegistry
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.risk import PortfolioContext, PositionSizer, RiskConfigResolver, RiskDecisionRecord, TradeRiskRequest
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord
from src.trading.post_close.strategy_evolution import (
    StrategyEvolutionPipeline,
    StrategyEvolutionRequest,
    maybe_promote_strategy_from_outcomes,
)
from src.trading.workflows.trading_decision import TradingDecisionPipeline


def _strategy_prompt(tmp_path) -> PromptRegistry:
    prompt_dir = tmp_path / "prompts" / "trading"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "strategy_evolution_v1.yaml").write_text(
        "prompt_id: strategy_evolution\n"
        "prompt_version: v1\n"
        "pipeline_name: strategy_evolution\n"
        "output_schema_id: strategy_evolution\n"
        "output_schema_version: v1\n"
        "template: |\n"
        "  Synthesize strategy proposals for trade date {{ trade_date }}.\n"
        "  Input JSON: {{ input_payload_json }}\n",
        encoding="utf-8",
    )
    return PromptRegistry(root=tmp_path / "prompts")


def _decision_prompt(tmp_path) -> PromptRegistry:
    prompt_dir = tmp_path / "prompts" / "trading"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "trading_decision_v1.yaml").write_text(
        "prompt_id: trading_decision\n"
        "prompt_version: v1\n"
        "pipeline_name: trading\n"
        "output_schema_id: trading_decision\n"
        "output_schema_version: v1\n"
        "template: |\n"
        "  Decide what to do for {{ ticker }}.\n"
        "  Input JSON: {{ input_payload_json }}\n",
        encoding="utf-8",
    )
    return PromptRegistry(root=tmp_path / "prompts")


def _candidate(*, lifecycle_status: str) -> CandidateScoreRecord:
    now = datetime(2026, 6, 2, 14, 30, tzinfo=timezone.utc)
    return CandidateScoreRecord(
        candidate_score_id=f"candidate-{lifecycle_status}",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="AAPL",
        strategy_id="post_gap_vwap_reclaim_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.8,
        direction="bullish",
        action="enter_long",
        typical_horizon="intraday-3d",
        core_signal_evidence={"technical.vwap_reclaim": True},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["re-loses VWAP"],
        risk_tags=["gap_risk"],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="pattern matched",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
        strategy_lifecycle_status=lifecycle_status,
        strategy_source="reflection_learning",
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
        intended_horizon=candidate.typical_horizon,
        exit_policy="close_or_invalidator",
        result_status="actionable_trade",
        classification_reason="eligible",
        selected_strategy_context_json={},
        decision_time=candidate.decision_time,
    )


def _risk(candidate: CandidateScoreRecord) -> RiskDecisionRecord:
    return RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id=candidate.candidate_score_id,
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker=candidate.ticker,
        status="approved",
        reason_code="within_limits",
        approved_weight=0.03,
        approved_notional=3_000.0,
        approved_quantity=15.0,
        portfolio_risk_snapshot_id="portfolio-risk-1",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=candidate.decision_time,
        metadata_json={},
    )


def _strategy_definition(*, lifecycle_status: str = "shadow") -> StrategyDefinitionRecord:
    return StrategyDefinitionRecord(
        strategy_definition_id="definition-1",
        strategy_id="post_gap_vwap_reclaim_v1",
        version="v1",
        display_name="Post-Gap VWAP Reclaim",
        strategy_layer="tactical_pattern",
        typical_horizon="intraday-3d",
        config_json={
            "required_signals": ["opening_gap_pct", "vwap_reclaim", "relative_volume"],
            "risk_tags": ["gap_risk", "intraday_momentum"],
            "core_thesis": "Gap reclaim continuation.",
        },
        lifecycle_status=lifecycle_status,
        is_active=True,
        source="reflection_learning",
    )


def _outcome(
    outcome_id: str,
    *,
    ticker: str,
    decision_time: datetime,
    alpha: float,
) -> CandidateOutcomeEvaluationRecord:
    return CandidateOutcomeEvaluationRecord(
        candidate_outcome_evaluation_id=outcome_id,
        historical_replay_run_id=None,
        candidate_score_id=f"candidate-{outcome_id}",
        trade_classification_id=None,
        ticker=ticker,
        strategy_id="post_gap_vwap_reclaim_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        trade_identity="watch_only",
        direction="bullish",
        catalyst_type="earnings",
        confidence_bucket="bucket",
        decision_time=decision_time,
        horizon_start_at=decision_time,
        horizon_end_at=decision_time,
        evaluation_status="final",
        candidate_return=0.04,
        benchmark_returns={"QQQ": 0.01},
        peer_basket_id=None,
        peer_basket_return=None,
        alpha=alpha,
        max_favorable_excursion=0.05,
        max_adverse_excursion=-0.01,
        regime="neutral",
        sector_theme="software",
        metadata_json={},
    )


def _positive_outcomes() -> tuple[CandidateOutcomeEvaluationRecord, ...]:
    return (
        _outcome("outcome-1", ticker="AAPL", decision_time=datetime(2026, 5, 29, 22, 0, tzinfo=timezone.utc), alpha=0.03),
        _outcome("outcome-2", ticker="MSFT", decision_time=datetime(2026, 6, 1, 22, 0, tzinfo=timezone.utc), alpha=0.03),
        _outcome("outcome-3", ticker="NVDA", decision_time=datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc), alpha=-0.01),
    )


def _lifecycle_request(
    outcomes: tuple[CandidateOutcomeEvaluationRecord, ...] | None = None,
) -> StrategyEvolutionRequest:
    now = datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc)
    return StrategyEvolutionRequest(
        trade_date=date(2026, 6, 2),
        decision_time=now,
        available_for_decision_at=now,
        daily_reflections=(),
        learning_factors=(),
        rejected_candidates=(),
        candidate_outcome_evaluations=outcomes or _positive_outcomes(),
    )


def test_shadow_strategy_promotes_to_experimental_after_positive_evidence(tmp_path):
    repository = InMemoryTradingRepository()
    repository.save_strategy_definition(_strategy_definition(lifecycle_status="shadow"))
    pipeline = StrategyEvolutionPipeline(
        repository=repository,
        prompt_registry=_strategy_prompt(tmp_path),
        model_name="gpt-5",
        agent_runner=lambda prompt, model_name: {
            "content": {
                "proposals": [],
                "schema_version": "v1",
                "generated_at": "2026-06-02T22:00:00+00:00",
            }
        },
    )

    result = pipeline.run(request=_lifecycle_request())

    assert result.lifecycle_updates[0].new_lifecycle_status == "experimental"
    assert result.strategy_definitions[0].lifecycle_status == "experimental"


def test_lifecycle_promotion_requires_distinct_trade_dates():
    same_day = datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc)

    transition = maybe_promote_strategy_from_outcomes(
        definition=_strategy_definition(lifecycle_status="shadow"),
        outcomes=(
            _outcome("outcome-1", ticker="AAPL", decision_time=same_day, alpha=0.03),
            _outcome("outcome-2", ticker="MSFT", decision_time=same_day, alpha=0.03),
            _outcome("outcome-3", ticker="NVDA", decision_time=same_day, alpha=0.02),
        ),
        decision_time=same_day,
    )

    assert transition is None


def test_lifecycle_promotion_requires_distinct_tickers():
    decision_time = datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc)

    transition = maybe_promote_strategy_from_outcomes(
        definition=_strategy_definition(lifecycle_status="shadow"),
        outcomes=(
            _outcome("outcome-1", ticker="AAPL", decision_time=datetime(2026, 5, 29, 22, 0, tzinfo=timezone.utc), alpha=0.03),
            _outcome("outcome-2", ticker="AAPL", decision_time=datetime(2026, 6, 1, 22, 0, tzinfo=timezone.utc), alpha=0.03),
            _outcome("outcome-3", ticker="AAPL", decision_time=decision_time, alpha=0.02),
        ),
        decision_time=decision_time,
    )

    assert transition is None


def test_lifecycle_promotion_requires_win_rate_threshold():
    decision_time = datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc)

    transition = maybe_promote_strategy_from_outcomes(
        definition=_strategy_definition(lifecycle_status="shadow"),
        outcomes=(
            _outcome("outcome-1", ticker="AAPL", decision_time=datetime(2026, 5, 29, 22, 0, tzinfo=timezone.utc), alpha=0.03),
            _outcome("outcome-2", ticker="MSFT", decision_time=datetime(2026, 6, 1, 22, 0, tzinfo=timezone.utc), alpha=-0.02),
            _outcome("outcome-3", ticker="NVDA", decision_time=decision_time, alpha=-0.01),
        ),
        decision_time=decision_time,
    )

    assert transition is None


def test_lifecycle_promotion_requires_positive_mean_alpha():
    decision_time = datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc)

    transition = maybe_promote_strategy_from_outcomes(
        definition=_strategy_definition(lifecycle_status="shadow"),
        outcomes=(
            _outcome("outcome-1", ticker="AAPL", decision_time=datetime(2026, 5, 29, 22, 0, tzinfo=timezone.utc), alpha=0.001),
            _outcome("outcome-2", ticker="MSFT", decision_time=datetime(2026, 6, 1, 22, 0, tzinfo=timezone.utc), alpha=0.001),
            _outcome("outcome-3", ticker="NVDA", decision_time=decision_time, alpha=-0.01),
        ),
        decision_time=decision_time,
    )

    assert transition is None


def test_shadow_strategies_are_not_paper_trade_authorized_and_experimental_are_capped(tmp_path):
    shadow_candidate = _candidate(lifecycle_status="shadow")
    experimental_candidate = _candidate(lifecycle_status="experimental")
    classification = _classification(shadow_candidate)
    decision_pipeline = TradingDecisionPipeline(
        repository=InMemoryTradingRepository(),
        prompt_registry=_decision_prompt(tmp_path),
        model_name="gpt-5-mini",
        agent_runner=lambda prompt, model_name: {
            "content": {
                "ticker": "AAPL",
                "decision": "enter_long",
                "strategy_id": "post_gap_vwap_reclaim_v1",
                "expression_bucket_id": "long_stock",
                "trade_identity": "tactical_stock_trade",
                "instrument_type": "stock",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.75,
                "confidence_basis": {},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.05,
                "max_loss_pct": 0.02,
                "time_horizon": "intraday-3d",
                "entry_plan": "market_open",
                "exit_plan": "close_or_invalidator",
                "thesis": "Pattern matched.",
                "key_signals": ["vwap_reclaim"],
                "risk_checks": ["liquidity_ok"],
                "invalidators": ["re-loses VWAP"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-02T14:30:00+00:00",
            }
        },
    )

    shadow_result = decision_pipeline.run(
        candidates=(shadow_candidate,),
        classifications=(classification,),
        risk_decisions=(_risk(shadow_candidate),),
        decision_time=shadow_candidate.decision_time,
    )

    assert shadow_result.decisions[0].metadata_json["paper_trade_authorized"] is False

    resolver = RiskConfigResolver()
    portfolio_context = PortfolioContext(
        as_of=experimental_candidate.decision_time,
        account_equity=100_000.0,
        cash_balance=20_000.0,
        buying_power=180_000.0,
        excess_liquidity=50_000.0,
        positions=(),
        open_strategy_exposure={},
        current_factor_exposure=(),
        stock_margin_requirement=0.0,
        option_margin_requirement=0.0,
        total_margin_requirement=0.0,
    )
    config = resolver.resolve(
        risk_appetite="balanced",
        portfolio_context=portfolio_context,
        macro_risk_budget_multiplier=1.0,
    )
    sizing = PositionSizer().size_position(
        TradeRiskRequest(
            candidate=experimental_candidate,
            classification=_classification(experimental_candidate),
            instrument_type="stock",
            target_weight=0.08,
            confidence=0.8,
            sector="Technology",
            beta_bucket="medium",
            volatility_bucket="medium",
            liquidity_bucket="deep",
            event_type=None,
            macro_sensitivity="medium",
            price=200.0,
            atr_pct=0.03,
            average_daily_dollar_volume=50_000_000.0,
            signal_freshness={"technical": "fresh"},
            estimated_margin_requirement=4_000.0,
            estimated_buying_power_effect=4_000.0,
            estimated_initial_margin_requirement=4_000.0,
            estimated_maintenance_margin_requirement=2_000.0,
        ),
        portfolio_context=portfolio_context,
        config=config,
    )

    assert sizing.final_weight < config.strategy_budget_weight
    assert sizing.metadata_json["strategy_lifecycle_status"] == "experimental"
