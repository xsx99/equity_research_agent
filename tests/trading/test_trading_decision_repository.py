from datetime import datetime, timezone

from src.agents.prompt_registry import PromptRegistry
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.risk import RiskDecisionRecord
from src.trading.signals import SignalSnapshotResult
from src.trading.signals.sources import EventNewsItemRecord
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord
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
        signal_json={
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
    assert repository.trading_decisions == list(result.decisions)
    assert len(repository.llm_prompt_runs) == 1
    assert len(repository.llm_usage_events) == 1
    assert manual_service.load_active()[0].latest_result_status == "actionable_trade"


def test_trading_decision_pipeline_builds_readable_news_evidence_items_for_llm_input(tmp_path):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    registry = _write_prompt(tmp_path)
    repository = InMemoryTradingRepository()
    news_id = "d8e368ec-7912-538e-bb54-740481024fc0"
    repository.save_event_news_item(
        EventNewsItemRecord(
            event_news_item_id=news_id,
            ticker="NVDA",
            source_ticker="NVDA",
            event_type="earnings",
            direction="bullish",
            sentiment="positive",
            importance="high",
            headline="NVIDIA raises guidance after AI demand accelerates",
            summary="Management said datacenter demand remained ahead of expectations.",
            provider="alpaca_live",
            source_refs_json=[],
            dedupe_key="nvda-earnings-1",
            event_time=now,
            published_at=now,
            ingested_at=now,
            available_for_decision_at=now,
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
                    "source_record_id": news_id,
                },
                {"source_record_id": "market_bars:NVDA"},
            ],
            source_available_times_json={
                news_id: now.isoformat(),
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
        candidate_score=0.81,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"events_news.catalyst_quality_score": 0.88},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["QQQ breaks trend"],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="catalyst confirmed",
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
    assert signal_snapshot["evidence_items"] == [
        {
            "source": "alpaca_live",
            "source_table": "event_news_items",
            "source_record_id": news_id,
            "source_text": (
                "NVIDIA raises guidance after AI demand accelerates\n\n"
                "Management said datacenter demand remained ahead of expectations."
            ),
            "available_time": now.isoformat(),
        }
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
