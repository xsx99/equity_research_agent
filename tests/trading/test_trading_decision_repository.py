from datetime import date, datetime, timezone

from src.agents.prompt_registry import PromptRegistry
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.risk import RiskDecisionRecord
from src.trading.signals import SignalSnapshotResult, build_signal_snapshot
from src.trading.signals.sources import EventNewsItemRecord, InMemorySignalSourceRepository, SourceRecord
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord
from src.trading.workflows.trading_decision import TradingDecisionPipeline


def _write_prompt(tmp_path):
    prompt_dir = tmp_path / "prompts" / "trading"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "trading_decision_v1.yaml"
    prompt_file.write_text(
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


def _snapshot(
    now: datetime,
    *,
    ticker: str = "NVDA",
    manual_request_id: str | None = None,
    signal_json: dict[str, dict[str, object]] | None = None,
    source_record_refs_json: list[dict[str, str]] | None = None,
    source_available_times_json: dict[str, str] | None = None,
) -> SignalSnapshotResult:
    return SignalSnapshotResult(
        signal_snapshot_id="snapshot-1",
        ticker=ticker,
        snapshot_type="pre_open",
        decision_time=now,
        available_for_decision_at=now,
        max_input_available_for_decision_at=now,
        signal_json=signal_json
        or {
            "technical": {"rs_vs_spy_1d": 0.02, "relative_volume": 1.8},
            "fundamental": {"quality_score": 0.91},
            "events_news": {"catalyst_quality_score": 0.88},
        },
        source_freshness_json={"technical": "fresh", "fundamental": "fresh", "events_news": "fresh"},
        missing_signals_json=[],
        stale_signals_json=[],
        source_record_refs_json=source_record_refs_json or [{"source_record_id": "market_bars:NVDA"}],
        source_available_times_json=source_available_times_json or {"market_bars:NVDA": now.isoformat()},
        excluded_future_source_count=0,
        point_in_time_passed=True,
        selection_source="manual_request" if manual_request_id is not None else "scanner",
        manual_request_id=manual_request_id,
    )


def _expression_definition(
    expression_bucket_id: str,
    *,
    trade_identity: str,
    allowed_instruments: tuple[str, ...],
    allowed_option_strategy_types: tuple[str, ...] = (),
    option_policy: dict[str, object] | None = None,
    earnings_policy: str | None = None,
) -> StrategyDefinitionRecord:
    return StrategyDefinitionRecord(
        strategy_definition_id=f"{expression_bucket_id}-definition",
        strategy_id=expression_bucket_id,
        version="v1",
        display_name=expression_bucket_id,
        strategy_layer="expression_bucket",
        typical_horizon="2w-3m",
        config_json={
            "default_trade_identity": trade_identity,
            "allowed_instruments": list(allowed_instruments),
            "allowed_option_strategy_types": list(allowed_option_strategy_types),
            "option_policy": dict(option_policy or {}),
            "earnings_policy": earnings_policy,
            "default_exit_policy": "strategy_invalidators_or_target_horizon",
        },
        lifecycle_status="active",
        is_active=True,
    )


def test_trading_decision_pipeline_persists_decisions_and_manual_request_status(tmp_path):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    manual_service = ManualTickerRequestService(now=lambda: now)
    request = manual_service.create("NVDA", "please review", "review_only")
    repository.save_signal_snapshot(_snapshot(now, manual_request_id=request.request_id))

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="NVDA",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.81,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"technical.trend_slope": 1.2},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["QQQ breaks trend"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="manual_request",
        manual_request_id=request.request_id,
        selection_reason="relative strength",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-1",
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="relative_strength_rotation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="close_or_invalidator",
        result_status="actionable_trade",
        classification_reason="eligible",
        selected_strategy_context_json={"benchmark_context": {"primary_benchmark": "QQQ"}},
        decision_time=now,
    )
    risk = RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="NVDA",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.04,
        approved_notional=4_000,
        approved_quantity=20,
        portfolio_risk_snapshot_id="snapshot-risk-1",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )

    def runner(prompt: str, model_name: str):
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "enter_long",
                "strategy_id": "relative_strength_rotation_v1",
                "expression_bucket_id": "long_stock",
                "trade_identity": "tactical_stock_trade",
                "instrument_type": "stock",
                "selection_source": "manual_request",
                "manual_request_id": request.request_id,
                "confidence": 0.74,
                "confidence_basis": {"calibration_bucket": "bullish_relative_strength"},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.04,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": "market_open",
                "exit_plan": "close_or_invalidator",
                "thesis": "Relative strength remains intact.",
                "key_drivers": ["sector_relative_strength"],
                "counterarguments": ["valuation is elevated versus peers"],
                "risk_checks": ["liquidity_ok"],
                "invalidators": ["QQQ closes below prior close"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    pipeline = TradingDecisionPipeline(
        repository=repository,
        prompt_registry=registry,
        manual_request_service=manual_service,
        model_name="gpt-5-mini",
        agent_runner=runner,
    )

    result = pipeline.run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(risk,),
        decision_time=now,
    )

    assert len(result.decisions) == 1
    assert result.decisions[0].decision == "no_trade"
    assert result.decisions[0].manual_request_id == request.request_id
    assert result.decisions[0].key_drivers == ["sector_relative_strength"]
    assert result.decisions[0].counterarguments == ["valuation is elevated versus peers"]
    assert result.decisions[0].context_snapshot_json["signal_snapshot"]["signal_snapshot_id"] == "snapshot-1"
    assert result.decisions[0].metadata_json["paper_trade_authorized"] is False
    assert result.decisions[0].metadata_json["entry_plan"] == "market_open"
    assert result.decisions[0].metadata_json["exit_plan"] == "close_or_invalidator"
    assert repository.trading_decisions == list(result.decisions)
    assert len(repository.llm_prompt_runs) == 1
    assert len(repository.llm_usage_events) == 1
    assert manual_service.load_active()[0].latest_result_status == "actionable_trade"


def test_trading_decision_pipeline_persists_resolved_expression_fallback_plan(tmp_path):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    repository.save_signal_snapshot(_snapshot(now))
    repository.save_strategy_definition(
        _expression_definition(
            "defined_risk_directional_option",
            trade_identity="tactical_option_trade",
            allowed_instruments=("paper_option_strategy",),
            allowed_option_strategy_types=("long_call", "long_put"),
            option_policy={
                "profit_target_pct": 0.65,
                "non_event_dte_days": 28,
                "long_call_strike_pct_above_spot": 0.02,
                "long_call_target_delta": 0.42,
                "close_conditions": ["take_profit_65pct", "time_stop_10d"],
            },
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "long_stock",
            trade_identity="tactical_stock_trade",
            allowed_instruments=("common_stock",),
        )
    )

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-option-1",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="NVDA",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.84,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"risk_shape.defined_risk_preferred": True},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["price confirmation fails"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="defined risk preferred",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-option-1",
        candidate_score_id="candidate-option-1",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="strong_theme_catalyst_continuation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="eligible option expression selected",
        selected_strategy_context_json={
            "selected_expression_bucket_id": "defined_risk_directional_option",
            "fallback_expression_bucket_ids": ["long_stock"],
        },
        decision_time=now,
    )

    def runner(prompt: str, model_name: str):
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "open_option_strategy",
                "strategy_id": "strong_theme_catalyst_continuation_v1",
                "expression_bucket_id": "defined_risk_directional_option",
                "trade_identity": "tactical_option_trade",
                "instrument_type": "option",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.78,
                "confidence_basis": {},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.03,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": "buy defined risk call exposure",
                "exit_plan": "close_or_invalidator",
                "thesis": "Defined risk is preferable while keeping bullish exposure.",
                "key_drivers": ["defined_risk_preferred"],
                "counterarguments": ["stock follow-through could be clean enough for common shares"],
                "risk_checks": ["defined_max_loss"],
                "invalidators": ["price confirmation fails"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    result = TradingDecisionPipeline(
        repository=repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    ).run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(),
        decision_time=now,
    )

    decision = result.decisions[0]
    plan = decision.context_snapshot_json["classification_context"]["expression_fallback_plan"]
    assert [item["expression_bucket_id"] for item in plan] == [
        "defined_risk_directional_option",
        "long_stock",
    ]
    assert plan[0]["trade_identity"] == "tactical_option_trade"
    assert plan[0]["instrument_type"] == "option"
    assert plan[0]["decision_action"] == "open_option_strategy"
    assert plan[1]["trade_identity"] == "tactical_stock_trade"
    assert plan[1]["instrument_type"] == "stock"
    assert plan[1]["decision_action"] == "enter_long"


def test_trading_decision_pipeline_persists_option_strategy_payloads_for_option_fallbacks(tmp_path):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    repository.save_signal_snapshot(
        _snapshot(
            now,
            signal_json={
                "technical": {
                    "rs_vs_spy_1d": 0.02,
                    "relative_volume": 1.8,
                    "last_price": 118.0,
                },
                "fundamental": {"quality_score": 0.91},
                "events_news": {
                    "catalyst_quality_score": 0.88,
                    "own_earnings_event_type": "earnings",
                },
            },
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "defined_risk_directional_option",
            trade_identity="tactical_option_trade",
            allowed_instruments=("paper_option_strategy",),
            allowed_option_strategy_types=("long_call", "long_put"),
            option_policy={
                "profit_target_pct": 0.65,
                "non_event_dte_days": 28,
                "long_call_strike_pct_above_spot": 0.02,
                "long_call_target_delta": 0.42,
                "close_conditions": ["take_profit_65pct", "time_stop_10d"],
            },
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "volatility_event_option",
            trade_identity="tactical_option_trade",
            allowed_instruments=("paper_option_strategy",),
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "long_stock",
            trade_identity="tactical_stock_trade",
            allowed_instruments=("common_stock",),
        )
    )

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-option-2",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="NVDA",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.84,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"risk_shape.defined_risk_preferred": True},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["price confirmation fails"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="defined risk preferred",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-option-2",
        candidate_score_id="candidate-option-2",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="strong_theme_catalyst_continuation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="eligible option expression selected",
        selected_strategy_context_json={
            "selected_expression_bucket_id": "defined_risk_directional_option",
            "fallback_expression_bucket_ids": ["volatility_event_option", "long_stock"],
        },
        decision_time=now,
    )

    def runner(prompt: str, model_name: str):
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "open_option_strategy",
                "strategy_id": "strong_theme_catalyst_continuation_v1",
                "expression_bucket_id": "defined_risk_directional_option",
                "trade_identity": "tactical_option_trade",
                "instrument_type": "option",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.78,
                "confidence_basis": {},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.03,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": "buy defined risk call exposure",
                "exit_plan": "close_or_invalidator",
                "thesis": "Defined risk is preferable while keeping bullish exposure.",
                "key_drivers": ["defined_risk_preferred"],
                "counterarguments": ["stock follow-through could be clean enough for common shares"],
                "risk_checks": ["defined_max_loss"],
                "invalidators": ["price confirmation fails"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    decision = TradingDecisionPipeline(
        repository=repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    ).run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(),
        decision_time=now,
    ).decisions[0]

    selected_payload = decision.metadata_json["option_strategy"]
    fallback_payloads = decision.metadata_json["option_strategy_fallbacks"]

    assert selected_payload["option_strategy_type"] == "long_call"
    assert selected_payload["status"] == "rejected"
    assert selected_payload["rejection_reason"] == "earnings_policy_blocked"
    assert selected_payload["underlying_price"] == 118.0
    assert len(selected_payload["metadata_json"]["legs"]) == 1
    assert fallback_payloads["volatility_event_option"]["option_strategy_type"] == "long_straddle"
    assert fallback_payloads["volatility_event_option"]["status"] == "ready"
    assert fallback_payloads["volatility_event_option"]["event_through_expiry"] is True
    assert len(fallback_payloads["volatility_event_option"]["metadata_json"]["legs"]) == 2
    assert "long_stock" not in fallback_payloads


def test_trading_decision_pipeline_uses_last_price_from_built_technical_snapshot(tmp_path):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    repository.save_signal_snapshot(
        build_signal_snapshot(
            ticker="NVDA",
            decision_time=now,
            snapshot_type="pre_open",
            source_records=[
                SourceRecord(
                    ticker="NVDA",
                    source_family="technical",
                    source="fixture",
                    source_table="market_bars",
                    source_record_id="bars-1",
                    event_time=available_at,
                    published_at=available_at,
                    ingested_at=available_at,
                    available_for_decision_at=available_at,
                    payload={
                        "bars": [
                            {
                                "date": date(2026, 5, 29),
                                "open": 113.0,
                                "high": 115.0,
                                "low": 112.0,
                                "close": 114.0,
                                "volume": 1_100_000,
                            },
                            {
                                "date": date(2026, 5, 30),
                                "open": 114.0,
                                "high": 118.0,
                                "low": 113.0,
                                "close": 117.5,
                                "volume": 1_500_000,
                            },
                        ],
                        "benchmark_returns": {"SPY": 0.01},
                    },
                ),
                SourceRecord(
                    ticker="NVDA",
                    source_family="fundamental",
                    source="fixture",
                    source_table="fundamental_snapshots",
                    source_record_id="fund-1",
                    event_time=available_at,
                    published_at=available_at,
                    ingested_at=available_at,
                    available_for_decision_at=available_at,
                    payload={"market_cap": 2_500_000_000_000, "revenue_growth_score": 0.7},
                ),
                SourceRecord(
                    ticker="NVDA",
                    source_family="events_news",
                    source="fixture",
                    source_table="event_news_items",
                    source_record_id="event-1",
                    event_time=available_at,
                    published_at=available_at,
                    ingested_at=available_at,
                    available_for_decision_at=available_at,
                    payload={"event_type": "analyst_upgrade", "sentiment": "positive", "importance": "high"},
                ),
            ],
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "defined_risk_directional_option",
            trade_identity="tactical_option_trade",
            allowed_instruments=("paper_option_strategy",),
        )
    )

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-option-3",
        strategy_run_id="run-1",
        signal_snapshot_id=repository.signal_snapshots[0].signal_snapshot_id,
        ticker="NVDA",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.84,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"risk_shape.defined_risk_preferred": True},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["price confirmation fails"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="defined risk preferred",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=available_at,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-option-3",
        candidate_score_id="candidate-option-3",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="strong_theme_catalyst_continuation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="eligible option expression selected",
        selected_strategy_context_json={
            "selected_expression_bucket_id": "defined_risk_directional_option",
            "fallback_expression_bucket_ids": [],
        },
        decision_time=now,
    )

    def runner(prompt: str, model_name: str):
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "open_option_strategy",
                "strategy_id": "strong_theme_catalyst_continuation_v1",
                "expression_bucket_id": "defined_risk_directional_option",
                "trade_identity": "tactical_option_trade",
                "instrument_type": "option",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.78,
                "confidence_basis": {},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.03,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": "buy defined risk call exposure",
                "exit_plan": "close_or_invalidator",
                "thesis": "Defined risk is preferable while keeping bullish exposure.",
                "key_drivers": ["defined_risk_preferred"],
                "counterarguments": [],
                "risk_checks": ["defined_max_loss"],
                "invalidators": ["price confirmation fails"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    decision = TradingDecisionPipeline(
        repository=repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    ).run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(),
        decision_time=now,
    ).decisions[0]

    assert decision.context_snapshot_json["signal_snapshot"]["signal_json"]["technical"]["last_price"] == 117.5
    assert decision.metadata_json["option_strategy"]["underlying_price"] == 117.5
    assert decision.metadata_json["option_strategy"]["profit_target_pct"] == 0.65
    assert decision.metadata_json["option_strategy"]["close_conditions"] == ["take_profit_65pct", "time_stop_10d"]
    leg = decision.metadata_json["option_strategy"]["metadata_json"]["legs"][0]
    assert leg["dte"] == 28
    assert leg["delta"] == 0.42
    assert leg["strike"] == 119.85


def test_trading_decision_pipeline_prefers_point_in_time_option_chain_legs_when_available(tmp_path):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    source_repository = InMemorySignalSourceRepository(
        (
            SourceRecord(
                ticker="NVDA",
                source_family="option_chain",
                source="fixture",
                source_table="option_chain_snapshots",
                source_record_id="chain-1",
                event_time=available_at,
                published_at=available_at,
                ingested_at=available_at,
                available_for_decision_at=available_at,
                payload={
                    "contracts": [
                        {
                            "contract_symbol": "NVDA260629C00120000",
                            "option_type": "call",
                            "strike": 120.0,
                            "expiry": "2026-06-29",
                            "dte": 28,
                            "delta": 0.41,
                            "gamma": 0.05,
                            "theta": -0.04,
                            "vega": 0.15,
                            "iv_rank": 0.58,
                            "bid": 3.1,
                            "ask": 3.3,
                            "mid": 3.2,
                            "chosen_price": 3.2,
                            "open_interest": 2400,
                            "volume": 180,
                        },
                        {
                            "contract_symbol": "NVDA260629C00123000",
                            "option_type": "call",
                            "strike": 123.0,
                            "expiry": "2026-06-29",
                            "dte": 28,
                            "delta": 0.34,
                            "gamma": 0.04,
                            "theta": -0.03,
                            "vega": 0.13,
                            "iv_rank": 0.6,
                            "bid": 2.4,
                            "ask": 2.6,
                            "mid": 2.5,
                            "chosen_price": 2.5,
                            "open_interest": 1200,
                            "volume": 95,
                        },
                    ]
                },
            ),
        )
    )
    repository.save_signal_snapshot(
        build_signal_snapshot(
            ticker="NVDA",
            decision_time=now,
            snapshot_type="pre_open",
            source_records=[
                SourceRecord(
                    ticker="NVDA",
                    source_family="technical",
                    source="fixture",
                    source_table="market_bars",
                    source_record_id="bars-1",
                    event_time=available_at,
                    published_at=available_at,
                    ingested_at=available_at,
                    available_for_decision_at=available_at,
                    payload={
                        "bars": [
                            {
                                "date": date(2026, 5, 29),
                                "open": 113.0,
                                "high": 115.0,
                                "low": 112.0,
                                "close": 114.0,
                                "volume": 1_100_000,
                            },
                            {
                                "date": date(2026, 5, 30),
                                "open": 114.0,
                                "high": 118.0,
                                "low": 113.0,
                                "close": 117.5,
                                "volume": 1_500_000,
                            },
                        ],
                        "benchmark_returns": {"SPY": 0.01},
                    },
                ),
                SourceRecord(
                    ticker="NVDA",
                    source_family="fundamental",
                    source="fixture",
                    source_table="fundamental_snapshots",
                    source_record_id="fund-1",
                    event_time=available_at,
                    published_at=available_at,
                    ingested_at=available_at,
                    available_for_decision_at=available_at,
                    payload={"market_cap": 2_500_000_000_000, "revenue_growth_score": 0.7},
                ),
                SourceRecord(
                    ticker="NVDA",
                    source_family="events_news",
                    source="fixture",
                    source_table="event_news_items",
                    source_record_id="event-1",
                    event_time=available_at,
                    published_at=available_at,
                    ingested_at=available_at,
                    available_for_decision_at=available_at,
                    payload={"event_type": "analyst_upgrade", "sentiment": "positive", "importance": "high"},
                ),
            ],
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "defined_risk_directional_option",
            trade_identity="tactical_option_trade",
            allowed_instruments=("paper_option_strategy",),
            allowed_option_strategy_types=("long_call", "long_put"),
            option_policy={
                "profit_target_pct": 0.65,
                "non_event_dte_days": 28,
                "long_call_strike_pct_above_spot": 0.02,
                "long_call_target_delta": 0.42,
                "close_conditions": ["take_profit_65pct", "time_stop_10d"],
            },
        )
    )

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-option-chain-1",
        strategy_run_id="run-1",
        signal_snapshot_id=repository.signal_snapshots[0].signal_snapshot_id,
        ticker="NVDA",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.84,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"risk_shape.defined_risk_preferred": True},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["price confirmation fails"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="defined risk preferred",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=available_at,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-option-chain-1",
        candidate_score_id="candidate-option-chain-1",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="strong_theme_catalyst_continuation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="eligible option expression selected",
        selected_strategy_context_json={
            "selected_expression_bucket_id": "defined_risk_directional_option",
            "fallback_expression_bucket_ids": [],
        },
        decision_time=now,
    )

    def runner(prompt: str, model_name: str):
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "open_option_strategy",
                "strategy_id": "strong_theme_catalyst_continuation_v1",
                "expression_bucket_id": "defined_risk_directional_option",
                "trade_identity": "tactical_option_trade",
                "instrument_type": "option",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.78,
                "confidence_basis": {},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.03,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": "buy defined risk call exposure",
                "exit_plan": "close_or_invalidator",
                "thesis": "Defined risk is preferable while keeping bullish exposure.",
                "key_drivers": ["defined_risk_preferred"],
                "counterarguments": [],
                "risk_checks": ["defined_max_loss"],
                "invalidators": ["price confirmation fails"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    decision = TradingDecisionPipeline(
        repository=repository,
        source_repository=source_repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    ).run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(),
        decision_time=now,
    ).decisions[0]

    payload = decision.metadata_json["option_strategy"]
    leg = payload["metadata_json"]["legs"][0]
    assert payload["metadata_json"]["payload_generation_mode"] == "option_chain_snapshot"
    assert leg["contract_symbol"] == "NVDA260629C00120000"
    assert leg["strike"] == 120.0
    assert leg["delta"] == 0.41
    assert leg["bid"] == 3.1
    assert leg["ask"] == 3.3
    assert leg["chosen_price"] == 3.2


def test_trading_decision_pipeline_uses_selected_option_chain_expiry_when_it_differs_from_target_dte(tmp_path):
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    source_repository = InMemorySignalSourceRepository(
        (
            SourceRecord(
                ticker="QQQ",
                source_family="option_chain",
                source="fixture",
                source_table="option_chain_snapshots",
                source_record_id="chain-live-like",
                event_time=available_at,
                published_at=available_at,
                ingested_at=available_at,
                available_for_decision_at=available_at,
                payload={
                    "contracts": [
                        {
                            "contract_symbol": "QQQ260617C00750000",
                            "option_type": "call",
                            "strike": 750.0,
                            "expiry": "2026-06-17",
                            "dte": 2,
                            "delta": 0.35,
                            "gamma": 0.05,
                            "theta": -0.04,
                            "vega": 0.15,
                            "iv_rank": 0.58,
                            "bid": 2.2,
                            "ask": 2.4,
                            "mid": 2.3,
                            "chosen_price": 2.3,
                            "volume": 13,
                        },
                    ]
                },
            ),
        )
    )
    repository.save_signal_snapshot(
        build_signal_snapshot(
            ticker="QQQ",
            decision_time=now,
            snapshot_type="pre_open",
            source_records=[
                SourceRecord(
                    ticker="QQQ",
                    source_family="technical",
                    source="fixture",
                    source_table="market_bars",
                    source_record_id="bars-1",
                    event_time=available_at,
                    published_at=available_at,
                    ingested_at=available_at,
                    available_for_decision_at=available_at,
                    payload={
                        "bars": [
                            {
                                "date": date(2026, 6, 12),
                                "open": 738.0,
                                "high": 744.0,
                                "low": 736.0,
                                "close": 742.97,
                                "volume": 1_500_000,
                            },
                        ],
                        "benchmark_returns": {"SPY": 0.01},
                    },
                ),
            ],
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "defined_risk_directional_option",
            trade_identity="tactical_option_trade",
            allowed_instruments=("paper_option_strategy",),
            allowed_option_strategy_types=("long_call", "long_put"),
            option_policy={
                "non_event_dte_days": 21,
                "long_call_target_delta": 0.35,
            },
        )
    )

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-live-like",
        strategy_run_id="run-1",
        signal_snapshot_id=repository.signal_snapshots[0].signal_snapshot_id,
        ticker="QQQ",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.84,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"risk_shape.defined_risk_preferred": True},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["price confirmation fails"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="defined risk preferred",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "SPY"},
        decision_time=now,
        available_for_decision_at=available_at,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-live-like",
        candidate_score_id="candidate-live-like",
        strategy_run_id="run-1",
        ticker="QQQ",
        selected_strategy_id="strong_theme_catalyst_continuation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="eligible option expression selected",
        selected_strategy_context_json={
            "selected_expression_bucket_id": "defined_risk_directional_option",
            "fallback_expression_bucket_ids": [],
        },
        decision_time=now,
    )

    def runner(prompt: str, model_name: str):
        return {
            "content": {
                "ticker": "QQQ",
                "decision": "open_option_strategy",
                "strategy_id": "strong_theme_catalyst_continuation_v1",
                "expression_bucket_id": "defined_risk_directional_option",
                "trade_identity": "tactical_option_trade",
                "instrument_type": "option",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.78,
                "confidence_basis": {},
                "benchmark_context": {"primary_benchmark": "SPY"},
                "target_weight": 0.03,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": "buy defined risk call exposure",
                "exit_plan": "close_or_invalidator",
                "thesis": "Defined risk is preferable while keeping bullish exposure.",
                "key_drivers": ["defined_risk_preferred"],
                "counterarguments": [],
                "risk_checks": ["defined_max_loss"],
                "invalidators": ["price confirmation fails"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-15T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    decision = TradingDecisionPipeline(
        repository=repository,
        source_repository=source_repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    ).run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(),
        decision_time=now,
    ).decisions[0]

    payload = decision.metadata_json["option_strategy"]
    assert payload["status"] == "ready"
    assert payload["rejection_reason"] is None
    assert payload["metadata_json"]["legs"][0]["expiry"] == "2026-06-17"


def test_trading_decision_pipeline_skips_illiquid_option_chain_contracts(tmp_path):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    source_repository = InMemorySignalSourceRepository(
        (
            SourceRecord(
                ticker="NVDA",
                source_family="option_chain",
                source="fixture",
                source_table="option_chain_snapshots",
                source_record_id="chain-illiquid",
                event_time=available_at,
                published_at=available_at,
                ingested_at=available_at,
                available_for_decision_at=available_at,
                payload={
                    "contracts": [
                        {
                            "contract_symbol": "NVDA260629C00120000",
                            "option_type": "call",
                            "strike": 120.0,
                            "expiry": "2026-06-29",
                            "dte": 28,
                            "delta": 0.41,
                            "gamma": 0.05,
                            "theta": -0.04,
                            "vega": 0.15,
                            "iv_rank": 0.58,
                            "bid": 0.0,
                            "ask": 3.3,
                            "mid": 1.65,
                            "chosen_price": 1.65,
                            "open_interest": 0,
                            "volume": 0,
                        },
                        {
                            "contract_symbol": "NVDA260629C00123000",
                            "option_type": "call",
                            "strike": 123.0,
                            "expiry": "2026-06-29",
                            "dte": 28,
                            "delta": 0.34,
                            "gamma": 0.04,
                            "theta": -0.03,
                            "vega": 0.13,
                            "iv_rank": 0.6,
                            "bid": 2.4,
                            "ask": 2.6,
                            "mid": 2.5,
                            "chosen_price": 2.5,
                            "open_interest": 1200,
                            "volume": 95,
                        },
                    ]
                },
            ),
        )
    )
    repository.save_signal_snapshot(
        build_signal_snapshot(
            ticker="NVDA",
            decision_time=now,
            snapshot_type="pre_open",
            source_records=[
                SourceRecord(
                    ticker="NVDA",
                    source_family="technical",
                    source="fixture",
                    source_table="market_bars",
                    source_record_id="bars-1",
                    event_time=available_at,
                    published_at=available_at,
                    ingested_at=available_at,
                    available_for_decision_at=available_at,
                    payload={
                        "bars": [
                            {
                                "date": date(2026, 5, 29),
                                "open": 113.0,
                                "high": 115.0,
                                "low": 112.0,
                                "close": 114.0,
                                "volume": 1_100_000,
                            },
                            {
                                "date": date(2026, 5, 30),
                                "open": 114.0,
                                "high": 118.0,
                                "low": 113.0,
                                "close": 117.5,
                                "volume": 1_500_000,
                            },
                        ],
                        "benchmark_returns": {"SPY": 0.01},
                    },
                ),
                SourceRecord(
                    ticker="NVDA",
                    source_family="fundamental",
                    source="fixture",
                    source_table="fundamental_snapshots",
                    source_record_id="fund-1",
                    event_time=available_at,
                    published_at=available_at,
                    ingested_at=available_at,
                    available_for_decision_at=available_at,
                    payload={"market_cap": 2_500_000_000_000, "revenue_growth_score": 0.7},
                ),
                SourceRecord(
                    ticker="NVDA",
                    source_family="events_news",
                    source="fixture",
                    source_table="event_news_items",
                    source_record_id="event-1",
                    event_time=available_at,
                    published_at=available_at,
                    ingested_at=available_at,
                    available_for_decision_at=available_at,
                    payload={"event_type": "analyst_upgrade", "sentiment": "positive", "importance": "high"},
                ),
            ],
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "defined_risk_directional_option",
            trade_identity="tactical_option_trade",
            allowed_instruments=("paper_option_strategy",),
            allowed_option_strategy_types=("long_call", "long_put"),
            option_policy={
                "profit_target_pct": 0.65,
                "non_event_dte_days": 28,
                "long_call_strike_pct_above_spot": 0.02,
                "long_call_target_delta": 0.42,
                "close_conditions": ["take_profit_65pct", "time_stop_10d"],
            },
        )
    )

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-option-chain-2",
        strategy_run_id="run-1",
        signal_snapshot_id=repository.signal_snapshots[0].signal_snapshot_id,
        ticker="NVDA",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.84,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"risk_shape.defined_risk_preferred": True},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["price confirmation fails"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="defined risk preferred",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=available_at,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-option-chain-2",
        candidate_score_id="candidate-option-chain-2",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="strong_theme_catalyst_continuation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="eligible option expression selected",
        selected_strategy_context_json={
            "selected_expression_bucket_id": "defined_risk_directional_option",
            "fallback_expression_bucket_ids": [],
        },
        decision_time=now,
    )

    def runner(prompt: str, model_name: str):
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "open_option_strategy",
                "strategy_id": "strong_theme_catalyst_continuation_v1",
                "expression_bucket_id": "defined_risk_directional_option",
                "trade_identity": "tactical_option_trade",
                "instrument_type": "option",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.78,
                "confidence_basis": {},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.03,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": "buy defined risk call exposure",
                "exit_plan": "close_or_invalidator",
                "thesis": "Defined risk is preferable while keeping bullish exposure.",
                "key_drivers": ["defined_risk_preferred"],
                "counterarguments": [],
                "risk_checks": ["defined_max_loss"],
                "invalidators": ["price confirmation fails"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    decision = TradingDecisionPipeline(
        repository=repository,
        source_repository=source_repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    ).run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(),
        decision_time=now,
    ).decisions[0]

    leg = decision.metadata_json["option_strategy"]["metadata_json"]["legs"][0]
    assert leg["strike"] == 123.0
    assert leg["bid"] == 2.4


def test_trading_decision_pipeline_marks_directional_option_payload_as_iv_degraded_when_chain_iv_is_missing(tmp_path):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    source_repository = InMemorySignalSourceRepository(
        (
            SourceRecord(
                ticker="NVDA",
                source_family="option_chain",
                source="fixture",
                source_table="option_chain_snapshots",
                source_record_id="chain-directional-no-iv",
                event_time=available_at,
                published_at=available_at,
                ingested_at=available_at,
                available_for_decision_at=available_at,
                payload={
                    "contracts": [
                        {
                            "contract_symbol": "NVDA260629C00120000",
                            "option_type": "call",
                            "strike": 120.0,
                            "expiry": "2026-06-29",
                            "dte": 28,
                            "delta": 0.41,
                            "gamma": 0.05,
                            "theta": -0.04,
                            "vega": 0.15,
                            "implied_volatility": None,
                            "iv_rank": None,
                            "bid": 3.1,
                            "ask": 3.3,
                            "mid": 3.2,
                            "chosen_price": 3.2,
                            "open_interest": 2400,
                            "volume": 180,
                        },
                    ]
                },
            ),
        )
    )
    repository.save_signal_snapshot(
        _snapshot(
            now,
            signal_json={
                "technical": {"rs_vs_spy_1d": 0.02, "relative_volume": 1.8, "last_price": 118.0},
                "fundamental": {"quality_score": 0.91},
                "events_news": {"catalyst_quality_score": 0.88},
            },
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "defined_risk_directional_option",
            trade_identity="tactical_option_trade",
            allowed_instruments=("paper_option_strategy",),
            allowed_option_strategy_types=("long_call", "long_put"),
            option_policy={
                "profit_target_pct": 0.65,
                "non_event_dte_days": 28,
                "long_call_strike_pct_above_spot": 0.02,
                "long_call_target_delta": 0.42,
                "close_conditions": ["take_profit_65pct", "time_stop_10d"],
            },
        )
    )

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-directional-no-iv",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="NVDA",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.84,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"risk_shape.defined_risk_preferred": True},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["price confirmation fails"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="defined risk preferred",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=available_at,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-directional-no-iv",
        candidate_score_id="candidate-directional-no-iv",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="strong_theme_catalyst_continuation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="eligible option expression selected",
        selected_strategy_context_json={
            "selected_expression_bucket_id": "defined_risk_directional_option",
            "fallback_expression_bucket_ids": [],
        },
        decision_time=now,
    )

    def runner(prompt: str, model_name: str):
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "open_option_strategy",
                "strategy_id": "strong_theme_catalyst_continuation_v1",
                "expression_bucket_id": "defined_risk_directional_option",
                "trade_identity": "tactical_option_trade",
                "instrument_type": "option",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.78,
                "confidence_basis": {},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.03,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": "buy defined risk call exposure",
                "exit_plan": "close_or_invalidator",
                "thesis": "Defined risk is preferable while keeping bullish exposure.",
                "key_drivers": ["defined_risk_preferred"],
                "counterarguments": [],
                "risk_checks": ["defined_max_loss"],
                "invalidators": ["price confirmation fails"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    decision = TradingDecisionPipeline(
        repository=repository,
        source_repository=source_repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    ).run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(),
        decision_time=now,
    ).decisions[0]

    payload = decision.metadata_json["option_strategy"]
    assert payload["status"] == "ready"
    assert payload["metadata_json"]["iv_context"]["mode"] == "degraded_missing_implied_volatility"
    assert payload["metadata_json"]["iv_context"]["iv_required"] is False
    assert payload["metadata_json"]["legs"][0]["implied_volatility"] is None


def test_trading_decision_pipeline_rejects_volatility_event_option_when_chain_iv_is_missing(tmp_path):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    source_repository = InMemorySignalSourceRepository(
        (
            SourceRecord(
                ticker="NVDA",
                source_family="option_chain",
                source="fixture",
                source_table="option_chain_snapshots",
                source_record_id="chain-vol-no-iv",
                event_time=available_at,
                published_at=available_at,
                ingested_at=available_at,
                available_for_decision_at=available_at,
                payload={
                    "contracts": [
                        {
                            "contract_symbol": "NVDA260608C00122000",
                            "option_type": "call",
                            "strike": 122.0,
                            "expiry": "2026-06-08",
                            "dte": 7,
                            "delta": 0.26,
                            "gamma": 0.03,
                            "theta": -0.01,
                            "vega": 0.08,
                            "implied_volatility": None,
                            "iv_rank": None,
                            "bid": 1.4,
                            "ask": 1.6,
                            "mid": 1.5,
                            "chosen_price": 1.5,
                            "open_interest": 1200,
                            "volume": 95,
                        },
                        {
                            "contract_symbol": "NVDA260608P00114000",
                            "option_type": "put",
                            "strike": 114.0,
                            "expiry": "2026-06-08",
                            "dte": 7,
                            "delta": -0.14,
                            "gamma": 0.02,
                            "theta": -0.01,
                            "vega": 0.07,
                            "implied_volatility": None,
                            "iv_rank": None,
                            "bid": 1.4,
                            "ask": 1.6,
                            "mid": 1.5,
                            "chosen_price": 1.5,
                            "open_interest": 1300,
                            "volume": 102,
                        },
                    ]
                },
            ),
        )
    )
    repository.save_signal_snapshot(
        _snapshot(
            now,
            signal_json={
                "technical": {"rs_vs_spy_1d": 0.02, "relative_volume": 1.8, "last_price": 118.0},
                "fundamental": {"quality_score": 0.91},
                "events_news": {
                    "catalyst_quality_score": 0.88,
                    "own_earnings_event_type": "earnings",
                },
            },
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "volatility_event_option",
            trade_identity="tactical_option_trade",
            allowed_instruments=("paper_option_strategy",),
            allowed_option_strategy_types=("long_strangle",),
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "long_stock",
            trade_identity="tactical_stock_trade",
            allowed_instruments=("common_stock",),
        )
    )

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-vol-no-iv",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="NVDA",
        strategy_id="strong_theme_no_clear_near_term_entry_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.79,
        direction="neutral",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"event_context.event_volatility_matters": True},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["event reaction fails"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="event volatility setup",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=available_at,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-vol-no-iv",
        candidate_score_id="candidate-vol-no-iv",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="strong_theme_no_clear_near_term_entry_v1",
        selected_strategy_version="v1",
        expression_bucket_id="volatility_event_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        watch_type=None,
        direction="neutral",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="event volatility expression selected",
        selected_strategy_context_json={
            "selected_expression_bucket_id": "volatility_event_option",
            "fallback_expression_bucket_ids": ["long_stock"],
        },
        decision_time=now,
    )

    def runner(prompt: str, model_name: str):
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "open_option_strategy",
                "strategy_id": "strong_theme_no_clear_near_term_entry_v1",
                "expression_bucket_id": "volatility_event_option",
                "trade_identity": "tactical_option_trade",
                "instrument_type": "option",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.7,
                "confidence_basis": {},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.02,
                "max_loss_pct": 0.02,
                "time_horizon": "1w-2w",
                "entry_plan": "buy event volatility expression",
                "exit_plan": "event_exit_after_reaction",
                "thesis": "Event volatility is the preferred expression.",
                "key_drivers": ["event_volatility_setup"],
                "counterarguments": [],
                "risk_checks": ["defined_max_loss"],
                "invalidators": ["event reaction fails"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    decision = TradingDecisionPipeline(
        repository=repository,
        source_repository=source_repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    ).run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(),
        decision_time=now,
    ).decisions[0]

    payload = decision.metadata_json["option_strategy"]
    assert payload["status"] == "rejected"
    assert payload["rejection_reason"] == "iv_data_required"
    assert payload["metadata_json"]["iv_context"]["mode"] == "rejected_missing_implied_volatility"
    assert payload["metadata_json"]["iv_context"]["iv_required"] is True


def test_trading_decision_pipeline_prefers_higher_vega_event_contracts_for_volatility_expression(tmp_path):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    source_repository = InMemorySignalSourceRepository(
        (
            SourceRecord(
                ticker="NVDA",
                source_family="option_chain",
                source="fixture",
                source_table="option_chain_snapshots",
                source_record_id="chain-vol-high-vega",
                event_time=available_at,
                published_at=available_at,
                ingested_at=available_at,
                available_for_decision_at=available_at,
                payload={
                    "contracts": [
                        {
                            "contract_symbol": "NVDA260608C00123000",
                            "option_type": "call",
                            "strike": 123.0,
                            "expiry": "2026-06-08",
                            "dte": 7,
                            "delta": 0.26,
                            "gamma": 0.03,
                            "theta": -0.01,
                            "vega": 0.08,
                            "implied_volatility": 0.35,
                            "iv_rank": 0.32,
                            "bid": 1.4,
                            "ask": 1.6,
                            "mid": 1.5,
                            "chosen_price": 1.5,
                            "open_interest": 1200,
                            "volume": 95,
                        },
                        {
                            "contract_symbol": "NVDA260608P00114000",
                            "option_type": "put",
                            "strike": 114.0,
                            "expiry": "2026-06-08",
                            "dte": 7,
                            "delta": -0.14,
                            "gamma": 0.02,
                            "theta": -0.01,
                            "vega": 0.07,
                            "implied_volatility": 0.34,
                            "iv_rank": 0.3,
                            "bid": 1.4,
                            "ask": 1.6,
                            "mid": 1.5,
                            "chosen_price": 1.5,
                            "open_interest": 1300,
                            "volume": 102,
                        },
                        {
                            "contract_symbol": "NVDA260608C00124000",
                            "option_type": "call",
                            "strike": 124.0,
                            "expiry": "2026-06-08",
                            "dte": 7,
                            "delta": 0.24,
                            "gamma": 0.05,
                            "theta": -0.02,
                            "vega": 0.22,
                            "implied_volatility": 0.72,
                            "iv_rank": 0.71,
                            "bid": 1.7,
                            "ask": 1.9,
                            "mid": 1.8,
                            "chosen_price": 1.8,
                            "open_interest": 2100,
                            "volume": 180,
                        },
                        {
                            "contract_symbol": "NVDA260608P00113000",
                            "option_type": "put",
                            "strike": 113.0,
                            "expiry": "2026-06-08",
                            "dte": 7,
                            "delta": -0.12,
                            "gamma": 0.04,
                            "theta": -0.02,
                            "vega": 0.2,
                            "implied_volatility": 0.7,
                            "iv_rank": 0.68,
                            "bid": 1.7,
                            "ask": 1.9,
                            "mid": 1.8,
                            "chosen_price": 1.8,
                            "open_interest": 2400,
                            "volume": 205,
                        },
                    ]
                },
            ),
        )
    )
    repository.save_signal_snapshot(
        _snapshot(
            now,
            signal_json={
                "technical": {"rs_vs_spy_1d": 0.02, "relative_volume": 1.8, "last_price": 118.0},
                "fundamental": {"quality_score": 0.91},
                "events_news": {
                    "catalyst_quality_score": 0.88,
                    "own_earnings_event_type": "earnings",
                },
            },
        )
    )
    repository.save_strategy_definition(
        _expression_definition(
            "volatility_event_option",
            trade_identity="tactical_option_trade",
            allowed_instruments=("paper_option_strategy",),
            allowed_option_strategy_types=("long_strangle",),
        )
    )

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-vol-high-vega",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="NVDA",
        strategy_id="strong_theme_no_clear_near_term_entry_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.79,
        direction="neutral",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"event_context.event_volatility_matters": True},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["event reaction fails"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="event volatility setup",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=available_at,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-vol-high-vega",
        candidate_score_id="candidate-vol-high-vega",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="strong_theme_no_clear_near_term_entry_v1",
        selected_strategy_version="v1",
        expression_bucket_id="volatility_event_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        watch_type=None,
        direction="neutral",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="event volatility expression selected",
        selected_strategy_context_json={
            "selected_expression_bucket_id": "volatility_event_option",
            "fallback_expression_bucket_ids": [],
        },
        decision_time=now,
    )

    def runner(prompt: str, model_name: str):
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "open_option_strategy",
                "strategy_id": "strong_theme_no_clear_near_term_entry_v1",
                "expression_bucket_id": "volatility_event_option",
                "trade_identity": "tactical_option_trade",
                "instrument_type": "option",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.7,
                "confidence_basis": {},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.02,
                "max_loss_pct": 0.02,
                "time_horizon": "1w-2w",
                "entry_plan": "buy event volatility expression",
                "exit_plan": "event_exit_after_reaction",
                "thesis": "Event volatility is the preferred expression.",
                "key_drivers": ["event_volatility_setup"],
                "counterarguments": [],
                "risk_checks": ["defined_max_loss"],
                "invalidators": ["event reaction fails"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    decision = TradingDecisionPipeline(
        repository=repository,
        source_repository=source_repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    ).run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(),
        decision_time=now,
    ).decisions[0]

    legs = decision.metadata_json["option_strategy"]["metadata_json"]["legs"]
    assert [leg["strike"] for leg in legs] == [124.0, 113.0]
    assert [leg["implied_volatility"] for leg in legs] == [0.72, 0.7]


def test_trading_decision_pipeline_builds_readable_news_evidence_items_for_llm_input(tmp_path):
    previous_scan = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    now = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    old_news_id = "d8e368ec-7912-538e-bb54-740481024fc0"
    new_news_ids = (
        "3fd6cffe-07a8-4970-b8c9-112233445501",
        "3fd6cffe-07a8-4970-b8c9-112233445502",
        "3fd6cffe-07a8-4970-b8c9-112233445503",
    )
    repository.save_signal_snapshot(
        SignalSnapshotResult(
            signal_snapshot_id="snapshot-prev",
            ticker="NVDA",
            snapshot_type="pre_open",
            decision_time=previous_scan,
            available_for_decision_at=previous_scan,
            max_input_available_for_decision_at=previous_scan,
            signal_json={
                "technical": {"rs_vs_spy_1d": 0.01, "relative_volume": 1.2},
                "fundamental": {"quality_score": 0.9},
                "events_news": {"catalyst_quality_score": 0.5, "sentiment_direction": "negative"},
            },
            source_freshness_json={"technical": "fresh", "fundamental": "fresh", "events_news": "fresh"},
            missing_signals_json=[],
            stale_signals_json=[],
            source_record_refs_json=[],
            source_available_times_json={},
            excluded_future_source_count=0,
            point_in_time_passed=True,
        )
    )
    repository.save_event_news_item(
        EventNewsItemRecord(
            event_news_item_id=old_news_id,
            ticker="NVDA",
            source_ticker="NVDA",
            event_type="regulatory_probe",
            direction="bearish",
            sentiment="negative",
            importance="high",
            headline="Old regulatory headline",
            summary="This one should be excluded because it was already visible last scan.",
            provider="alpaca_live",
            source_refs_json=[],
            dedupe_key="nvda-old-news",
            event_time=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            ingested_at=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            available_for_decision_at=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            raw_payload_ref=None,
            metadata_json={},
        )
    )
    repository.save_event_news_item(
        EventNewsItemRecord(
            event_news_item_id=new_news_ids[0],
            ticker="NVDA",
            source_ticker="NVDA",
            event_type="earnings_beat_raise",
            direction="bullish",
            sentiment="positive",
            importance="high",
            headline="NVIDIA raises guidance after AI demand accelerates",
            summary="Management said datacenter demand remained ahead of expectations.",
            provider="alpaca_live",
            source_refs_json=[],
            dedupe_key="nvda-new-news-1",
            event_time=datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc),
            ingested_at=datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc),
            available_for_decision_at=datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc),
            raw_payload_ref=None,
            metadata_json={},
        )
    )
    repository.save_event_news_item(
        EventNewsItemRecord(
            event_news_item_id=new_news_ids[1],
            ticker="NVDA",
            source_ticker="NVDA",
            event_type="analyst_upgrade",
            direction="bullish",
            sentiment="positive",
            importance="high",
            headline="Analyst lifts target after demand checks improve",
            summary="Channel checks pointed to sustained acceleration.",
            provider="alpaca_live",
            source_refs_json=[],
            dedupe_key="nvda-new-news-2",
            event_time=datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc),
            ingested_at=datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc),
            available_for_decision_at=datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc),
            raw_payload_ref=None,
            metadata_json={},
        )
    )
    repository.save_event_news_item(
        EventNewsItemRecord(
            event_news_item_id=new_news_ids[2],
            ticker="NVDA",
            source_ticker="NVDA",
            event_type="general_news",
            direction="bullish",
            sentiment="positive",
            importance="medium",
            headline="Follow-through demand remains healthy",
            summary="No new material negatives surfaced in supplier checks.",
            provider="alpaca_live",
            source_refs_json=[],
            dedupe_key="nvda-new-news-3",
            event_time=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
            ingested_at=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
            available_for_decision_at=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
            raw_payload_ref=None,
            metadata_json={},
        )
    )
    repository.save_signal_snapshot(
        _snapshot(
            now,
            source_record_refs_json=[
                {
                    "source": "alpaca_live",
                    "source_table": "event_news_items",
                    "source_record_id": old_news_id,
                },
                {
                    "source": "alpaca_live",
                    "source_table": "event_news_items",
                    "source_record_id": new_news_ids[0],
                },
                {
                    "source": "alpaca_live",
                    "source_table": "event_news_items",
                    "source_record_id": new_news_ids[1],
                },
                {
                    "source": "alpaca_live",
                    "source_table": "event_news_items",
                    "source_record_id": new_news_ids[2],
                },
                {"source_record_id": "market_bars:NVDA"},
            ],
            source_available_times_json={
                old_news_id: datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc).isoformat(),
                new_news_ids[0]: datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc).isoformat(),
                new_news_ids[1]: datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc).isoformat(),
                new_news_ids[2]: datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc).isoformat(),
                "market_bars:NVDA": now.isoformat(),
            },
        )
    )

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="NVDA",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.81234,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"events_news.catalyst_quality_score": 0.87654},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["QQQ breaks trend"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="catalyst confirmed",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ", "alpha_vs_peer_basket": 0.012345},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-1",
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="relative_strength_rotation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="close_or_invalidator",
        result_status="actionable_trade",
        classification_reason="eligible",
        selected_strategy_context_json={"benchmark_context": {"primary_benchmark": "QQQ"}},
        decision_time=now,
    )
    risk = RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="NVDA",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.04123,
        approved_notional=4_000,
        approved_quantity=20,
        portfolio_risk_snapshot_id="snapshot-risk-1",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )

    def runner(prompt: str, model_name: str):
        del prompt, model_name
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "enter_long",
                "strategy_id": "relative_strength_rotation_v1",
                "expression_bucket_id": "long_stock",
                "trade_identity": "tactical_stock_trade",
                "instrument_type": "stock",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.74,
                "confidence_basis": {"calibration_bucket": "bullish_relative_strength"},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.04,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": "market_open",
                "exit_plan": "close_or_invalidator",
                "thesis": "Relative strength remains intact.",
                "key_drivers": ["sector_relative_strength"],
                "counterarguments": ["valuation is elevated versus peers"],
                "risk_checks": ["liquidity_ok"],
                "invalidators": ["QQQ closes below prior close"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": "gpt-5-mini",
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    pipeline = TradingDecisionPipeline(
        repository=repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    )

    result = pipeline.run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(risk,),
        decision_time=now,
    )

    signal_snapshot = result.decisions[0].context_snapshot_json["signal_snapshot"]
    assert "source_record_refs_json" not in signal_snapshot
    assert "source_available_times_json" not in signal_snapshot
    assert signal_snapshot["signal_json"]["technical"]["rs_vs_spy_1d"] == 0.02
    assert result.decisions[0].context_snapshot_json["candidate_context"]["candidate_score"] == 0.812
    assert result.decisions[0].context_snapshot_json["candidate_context"]["benchmark_context"]["alpha_vs_peer_basket"] == 0.012
    assert result.decisions[0].context_snapshot_json["candidate_context"]["core_signal_evidence"]["events_news.catalyst_quality_score"] == 0.877
    assert result.decisions[0].context_snapshot_json["risk_context"]["approved_weight"] == 0.041
    assert signal_snapshot["signal_json"]["events_news"]["sentiment_direction"] == "positive"
    assert signal_snapshot["signal_json"]["events_news"]["catalyst_quality_score"] == 0.667
    assert signal_snapshot["signal_json"]["events_news"]["high_signal_news_count_24h"] == 2
    assert signal_snapshot["signal_json"]["events_news"]["high_signal_news_count_7d"] == 2
    assert signal_snapshot["evidence_items"] == [
        {
            "source": "alpaca_live",
            "source_table": "event_news_items",
            "source_record_id": new_news_ids[0],
            "source_text": (
                "NVIDIA raises guidance after AI demand accelerates\n\n"
                "Management said datacenter demand remained ahead of expectations."
            ),
            "available_time": datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc).isoformat(),
        },
        {
            "source": "alpaca_live",
            "source_table": "event_news_items",
            "source_record_id": new_news_ids[1],
            "source_text": (
                "Analyst lifts target after demand checks improve\n\n"
                "Channel checks pointed to sustained acceleration."
            ),
            "available_time": datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc).isoformat(),
        },
        {
            "source": "alpaca_live",
            "source_table": "event_news_items",
            "source_record_id": new_news_ids[2],
            "source_text": (
                "Follow-through demand remains healthy\n\n"
                "No new material negatives surfaced in supplier checks."
            ),
            "available_time": datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc).isoformat(),
        },
    ]


def test_trading_decision_pipeline_limits_news_evidence_to_representative_budget(tmp_path):
    now = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    news_rows = [
        EventNewsItemRecord(
            event_news_item_id="event-earnings-primary",
            ticker="NVDA",
            source_ticker="NVDA",
            event_type="earnings_beat_raise",
            direction="bullish",
            sentiment="positive",
            importance="high",
            headline="NVIDIA beats and raises guidance",
            summary="The company cited stronger datacenter demand.",
            provider="alpaca_live",
            source_refs_json=[],
            dedupe_key="nvda-earnings-primary",
            event_time=datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc),
            ingested_at=now,
            available_for_decision_at=datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc),
            raw_payload_ref=None,
            metadata_json={"duplicate_group_key": "group-earnings", "specificity_score": 8},
        ),
        EventNewsItemRecord(
            event_news_item_id="event-earnings-rewrite",
            ticker="NVDA",
            source_ticker="NVDA",
            event_type="earnings_beat_raise",
            direction="bullish",
            sentiment="positive",
            importance="high",
            headline="NVIDIA rallies after beat-and-raise quarter",
            summary="A syndicated rewrite of the same earnings event.",
            provider="alpaca_live",
            source_refs_json=[],
            dedupe_key="nvda-earnings-rewrite",
            event_time=datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc),
            ingested_at=now,
            available_for_decision_at=datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc),
            raw_payload_ref=None,
            metadata_json={"duplicate_group_key": "group-earnings", "specificity_score": 5},
        ),
        EventNewsItemRecord(
            event_news_item_id="event-offering",
            ticker="NVDA",
            source_ticker="NVDA",
            event_type="offering",
            direction="bearish",
            sentiment="negative",
            importance="critical",
            headline="NVIDIA announces convertible note offering",
            summary="The company disclosed a new financing transaction.",
            provider="alpaca_live",
            source_refs_json=[],
            dedupe_key="nvda-offering",
            event_time=datetime(2026, 6, 5, 7, 30, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 5, 7, 30, tzinfo=timezone.utc),
            ingested_at=now,
            available_for_decision_at=datetime(2026, 6, 5, 7, 30, tzinfo=timezone.utc),
            raw_payload_ref=None,
            metadata_json={"duplicate_group_key": "group-offering", "specificity_score": 9},
        ),
        EventNewsItemRecord(
            event_news_item_id="event-analyst",
            ticker="NVDA",
            source_ticker="NVDA",
            event_type="analyst_upgrade",
            direction="bullish",
            sentiment="positive",
            importance="high",
            headline="Analyst upgrades NVIDIA after channel checks",
            summary="The broker raised its target price.",
            provider="alpaca_live",
            source_refs_json=[],
            dedupe_key="nvda-analyst",
            event_time=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
            ingested_at=now,
            available_for_decision_at=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
            raw_payload_ref=None,
            metadata_json={"duplicate_group_key": "group-analyst", "specificity_score": 7},
        ),
        EventNewsItemRecord(
            event_news_item_id="event-customer",
            ticker="NVDA",
            source_ticker="NVDA",
            event_type="customer_order",
            direction="bullish",
            sentiment="positive",
            importance="medium",
            headline="Cloud customer expands NVIDIA order commitment",
            summary="The customer expanded a multi-year deployment.",
            provider="alpaca_live",
            source_refs_json=[],
            dedupe_key="nvda-customer",
            event_time=datetime(2026, 6, 5, 10, 30, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 5, 10, 30, tzinfo=timezone.utc),
            ingested_at=now,
            available_for_decision_at=datetime(2026, 6, 5, 10, 30, tzinfo=timezone.utc),
            raw_payload_ref=None,
            metadata_json={"duplicate_group_key": "group-customer", "specificity_score": 6},
        ),
        EventNewsItemRecord(
            event_news_item_id="event-general",
            ticker="NVDA",
            source_ticker="NVDA",
            event_type="general_news",
            direction=None,
            sentiment=None,
            importance="low",
            headline="NVIDIA remains in focus among AI names",
            summary="Generic market recap without a new catalyst.",
            provider="alpaca_live",
            source_refs_json=[],
            dedupe_key="nvda-general",
            event_time=datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc),
            ingested_at=now,
            available_for_decision_at=datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc),
            raw_payload_ref=None,
            metadata_json={"duplicate_group_key": "group-general", "specificity_score": 2},
        ),
    ]
    for row in news_rows:
        repository.save_event_news_item(row)
    repository.save_signal_snapshot(
        _snapshot(
            now,
            source_record_refs_json=[
                {"source": "alpaca_live", "source_table": "event_news_items", "source_record_id": row.event_news_item_id}
                for row in news_rows
            ]
            + [{"source_record_id": "market_bars:NVDA"}],
            source_available_times_json={
                row.event_news_item_id: row.available_for_decision_at.isoformat()
                for row in news_rows
            }
            | {"market_bars:NVDA": now.isoformat()},
        )
    )

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="NVDA",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.81,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"events_news.catalyst_quality_score": 0.8},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=[],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="condensed catalysts remain strong",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-1",
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="relative_strength_rotation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="close_or_invalidator",
        result_status="actionable_trade",
        classification_reason="eligible",
        selected_strategy_context_json={"benchmark_context": {"primary_benchmark": "QQQ"}},
        decision_time=now,
    )
    risk = RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="NVDA",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.04,
        approved_notional=4_000,
        approved_quantity=20,
        portfolio_risk_snapshot_id="snapshot-risk-1",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )

    def runner(prompt: str, model_name: str):
        del prompt, model_name
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "enter_long",
                "strategy_id": "relative_strength_rotation_v1",
                "expression_bucket_id": "long_stock",
                "trade_identity": "tactical_stock_trade",
                "instrument_type": "stock",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.74,
                "confidence_basis": {"calibration_bucket": "bullish_relative_strength"},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.04,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": "market_open",
                "exit_plan": "close_or_invalidator",
                "thesis": "Condensed event flow remains constructive.",
                "key_drivers": ["event_flow"],
                "counterarguments": ["offering risk remains active"],
                "risk_checks": ["liquidity_ok"],
                "invalidators": ["earnings momentum fades"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-05T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": "gpt-5-mini",
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    pipeline = TradingDecisionPipeline(
        repository=repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    )

    result = pipeline.run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(risk,),
        decision_time=now,
    )

    evidence_ids = [
        item["source_record_id"]
        for item in result.decisions[0].context_snapshot_json["signal_snapshot"]["evidence_items"]
    ]
    assert evidence_ids == [
        "event-offering",
        "event-earnings-primary",
        "event-analyst",
        "event-customer",
    ]


def test_trading_decision_pipeline_skips_llm_and_falls_back_when_signal_snapshot_is_missing(tmp_path):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()

    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        signal_snapshot_id="missing-snapshot",
        ticker="NVDA",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.81,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"technical.trend_slope": 1.2},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["QQQ breaks trend"],
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
    classification = TradeClassificationRecord(
        trade_classification_id="classification-1",
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="relative_strength_rotation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="close_or_invalidator",
        result_status="actionable_trade",
        classification_reason="eligible",
        selected_strategy_context_json={"benchmark_context": {"primary_benchmark": "QQQ"}},
        decision_time=now,
    )
    risk = RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="NVDA",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.04,
        approved_notional=4_000,
        approved_quantity=20,
        portfolio_risk_snapshot_id="snapshot-risk-1",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )

    def runner(prompt: str, model_name: str):
        raise AssertionError("LLM should not run when signal snapshot context is missing")

    pipeline = TradingDecisionPipeline(
        repository=repository,
        prompt_registry=registry,
        manual_request_service=None,
        model_name="gpt-5-mini",
        agent_runner=runner,
    )

    result = pipeline.run(
        candidates=(candidate,),
        classifications=(classification,),
        risk_decisions=(risk,),
        decision_time=now,
    )

    assert len(result.decisions) == 1
    assert result.decisions[0].decision == "no_trade"
    assert result.decisions[0].metadata_json["fallback_action"] == "no_trade"
    assert result.decisions[0].metadata_json["fallback_reason"] == "missing_signal_snapshot_context"
