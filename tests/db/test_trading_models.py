from datetime import date, datetime, timezone
from pathlib import Path

from src.db.models.trading import (
    CandidateOutcomeEvaluation,
    DailyReflection,
    DailyReflectionStatus,
    CandidateScore,
    EventNewsItem,
    FundamentalSnapshot,
    HistoricalReplayRun,
    LearningFactor,
    LearningFactorApplication,
    LearningFactorStatus,
    LlmParseStatus,
    LlmPromptLifecycleStatus,
    LlmPromptRun,
    LlmPromptTemplate,
    LlmUsageEvent,
    LlmUsageStatus,
    ManualTickerRequest,
    ManualTickerRequestMode,
    ManualTickerRequestStatus,
    PaperExecution,
    PaperOrder,
    PaperPosition,
    PeerBasket,
    PortfolioIntent,
    PortfolioIntentLifecycleStatus,
    PortfolioIntentType,
    PortfolioSnapshot,
    ProviderRequestRun,
    ProviderRequestStatus,
    IntradaySignalScan,
    IntradaySignalSnapshot,
    IntradayRebalanceDecision,
    NewsAlert,
    PortfolioRiskSnapshot,
    PositionSizingDecision,
    RiskAppetite,
    RiskDecision,
    RiskDecisionStatus,
    RiskFactorExposure,
    SignalSnapshot,
    SourceIngestionRun,
    SourceIngestionStatus,
    StrategyDefinition,
    StrategyLifecycleStatus,
    StrategyRun,
    StrategySource,
    ThemeLifecycleStatus,
    ThemeTaxonomy,
    TickerRelationship,
    TickerRelationshipType,
    TradeClassification,
    TradingDecision,
    UniverseFilterConfig,
    UniverseSnapshot,
    UniverseSymbol,
    UniverseSymbolStatus,
)


def test_strategy_definition_defaults():
    row = StrategyDefinition(
        strategy_id="gap_and_go_v1",
        version="v1",
        display_name="Gap-and-Go",
        strategy_layer="tactical_pattern",
        typical_horizon="intraday-3d",
        allowed_common_stock_direction="long_only",
        config_json={"required_signals": ["opening_gap_pct"]},
        lifecycle_status="active",
        source="seed",
        is_active=True,
    )
    assert row.strategy_id == "gap_and_go_v1"
    assert row.lifecycle_status == "active"
    assert row.allowed_common_stock_direction == "long_only"
    assert row.source == "seed"
    assert row.is_active is True


def test_new_status_enums_expose_choices():
    assert StrategyLifecycleStatus.choices() == (
        "candidate",
        "shadow",
        "experimental",
        "active",
        "retired",
    )
    assert StrategySource.choices() == ("seed", "reflection_learning", "manual")
    assert LlmPromptLifecycleStatus.choices() == ("active", "retired")
    assert LlmParseStatus.choices() == ("succeeded", "failed")
    assert LlmUsageStatus.choices() == ("succeeded", "failed")
    assert DailyReflectionStatus.choices() == ("succeeded", "fallback")
    assert LearningFactorStatus.choices() == (
        "candidate",
        "observation",
        "shadow",
        "active",
        "suppressed",
        "retired",
    )
    assert PortfolioIntentLifecycleStatus.choices() == ("active", "paused", "retired")
    assert PortfolioIntentType.choices() == (
        "core_growth",
        "core_index",
        "core_theme",
        "core_cash_like",
    )
    assert TickerRelationshipType.choices() == (
        "peer",
        "customer",
        "supplier",
        "competitor",
        "sector_leader",
        "etf_component",
        "theme_leader",
        "theme_constituent",
    )
    assert ThemeLifecycleStatus.choices() == ("active", "retired")
    assert UniverseSymbolStatus.choices() == ("included", "excluded")
    assert ManualTickerRequestMode.choices() == ("review_only", "paper_trade_eligible")
    assert ManualTickerRequestStatus.choices() == ("active", "dismissed", "cancelled")
    assert ProviderRequestStatus.choices() == (
        "succeeded",
        "failed",
        "cache_hit",
        "budget_exceeded",
        "circuit_open",
    )
    assert SourceIngestionStatus.choices() == ("succeeded", "failed", "degraded")
    assert RiskAppetite.choices() == ("conservative", "balanced", "aggressive")
    assert RiskDecisionStatus.choices() == ("approved", "reduced", "rejected")


def test_llm_models_can_be_instantiated():
    template = LlmPromptTemplate(
        prompt_id="trading_decision",
        prompt_version="v1",
        pipeline_name="trading",
        template_path="src/agents/prompts/trading/trading_decision_v1.yaml",
        template_hash="abc123",
        output_schema_id="trading_decision",
        output_schema_version="v1",
        lifecycle_status="active",
    )
    run = LlmPromptRun(
        prompt_template=template,
        pipeline_name="trading",
        rendered_prompt_hash="rendered123",
        input_context_json={"ticker": "NVDA"},
        raw_output_text="{}",
        parsed_output_json={},
        parse_status="succeeded",
        validation_errors_json=[],
        error_message=None,
    )
    usage = LlmUsageEvent(
        prompt_run=run,
        provider="google",
        model="gemini-2.5-flash",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost=0.01,
        latency_ms=1200,
        retry_count=0,
        status="succeeded",
    )

    assert template.prompt_id == "trading_decision"
    assert run.prompt_template is template
    assert usage.prompt_run is run


def test_reflection_models_can_be_instantiated():
    template = LlmPromptTemplate(
        prompt_id="reflection",
        prompt_version="v1",
        pipeline_name="reflection",
        template_path="src/agents/prompts/trading/reflection_v1.yaml",
        template_hash="reflection123",
        output_schema_id="reflection",
        output_schema_version="v1",
        lifecycle_status="active",
    )
    prompt_run = LlmPromptRun(
        prompt_template=template,
        pipeline_name="reflection",
        rendered_prompt_hash="rendered-reflection-123",
        input_context_json={"trade_date": "2026-06-02"},
        raw_output_text="{}",
        parsed_output_json={},
        parse_status="succeeded",
        validation_errors_json=[],
        error_message=None,
    )
    reflection = DailyReflection(
        trade_date=date(2026, 6, 2),
        prompt_run=prompt_run,
        status="succeeded",
        portfolio_summary_json={"realized_pnl": 120.0},
        reflection_json={"what_worked": ["confirmation"]},
        strategy_proposal_hints_json=[],
        metadata_json={},
    )
    factor = LearningFactor(
        factor_key="lf_2026_06_02_01",
        daily_reflection=reflection,
        trade_date=date(2026, 6, 2),
        title="Require confirmation for risky gaps",
        factor_type="candidate_filter",
        scope="strategy",
        status="active",
        strategy_id="gap_reversal_v1",
        condition="opening_gap_pct > 0.04 and relative_volume < 1.5",
        recommendation="Require first-30-minute confirmation.",
        confidence=0.7,
        activation_policy="auto_risk_tightening",
        effect_tags_json=["require_confirmation"],
        evidence_json=["Reduced false starts."],
        metadata_json={},
    )
    decision = TradingDecision(
        ticker="NVDA",
        decision="no_trade",
        strategy_id="gap_reversal_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        selection_source="scanner",
        manual_request_id=None,
        confidence=0,
        target_weight=0,
        approved_weight=0,
        max_loss_pct=0,
        time_horizon="2w-3m",
        thesis="Hold off until confirmation arrives.",
        invalidators_json=[],
        fallback_action=None,
        paper_trade_authorized=False,
        context_snapshot_json={},
        metadata_json={},
        decision_time=datetime(2026, 6, 2, 13, 0, tzinfo=timezone.utc),
        available_for_decision_at=datetime(2026, 6, 2, 13, 0, tzinfo=timezone.utc),
    )
    application = LearningFactorApplication(
        learning_factor=factor,
        trading_decision=decision,
        application_scope="trading_decision",
        metadata_json={},
    )

    assert reflection.status == "succeeded"
    assert factor.status == "active"
    assert application.learning_factor is factor


def test_pr_8_models_can_be_instantiated():
    now = datetime(2026, 6, 2, 15, 0, tzinfo=timezone.utc)
    scan = IntradaySignalScan(
        decision_time=now,
        started_at=now,
        completed_at=now,
        status="succeeded",
        scope_json={"tickers": ["NVDA"]},
        coverage_json={"tickers_requested": 1, "tickers_completed": 1},
        metadata_json={},
    )
    snapshot = IntradaySignalSnapshot(
        intraday_signal_scan=scan,
        ticker="NVDA",
        decision_time=now,
        baseline_signal_snapshot_id=None,
        previous_intraday_snapshot_id=None,
        refreshed_signals_json={"technical": {"last_price": 125.0}},
        carried_forward_signals_json={"fundamental": {"market_cap_bucket": "mega"}},
        delta_vs_baseline_json={"technical": {"last_price": 5.0}},
        delta_vs_previous_json={},
        source_freshness_json={"technical": "fresh"},
        metadata_json={},
    )
    alert = NewsAlert(
        ticker="NVDA",
        source_ticker="NVDA",
        alert_type="earnings_beat_raise",
        sentiment="positive",
        severity="high",
        source="fixture",
        published_at=now,
        headline="NVDA rises after earnings beat and raised guidance",
        summary="Beat and raise guidance.",
        strategy_relevance_json=["earnings_drift_v1"],
        affected_positions_json=["position-1"],
        affected_candidates_json=["candidate-1"],
        affected_themes_json=["ai_semis"],
        readthrough_source_ticker=None,
        action_required=True,
        dedupe_key="NVDA|earnings_beat_raise|2026-06-02T15:00:00+00:00",
        event_news_item_id=None,
        metadata_json={},
    )

    assert scan.status == "succeeded"
    assert snapshot.ticker == "NVDA"
    assert alert.severity == "high"
    rebalance = IntradayRebalanceDecision(
        ticker="NVDA",
        action="hold",
        status="fallback",
        reason_code="classification_failed",
        confidence=0,
        target_weight=0,
        approved_quantity=0,
        thesis="",
        urgency="low",
        rationale_json=[],
        available_for_decision_at=now,
        decision_time=now,
        metadata_json={},
    )
    assert rebalance.action == "hold"


def test_pr_1b_models_can_be_instantiated():
    intent = PortfolioIntent(
        ticker="GOOGL",
        intent_type="core_growth",
        target_weight=0.08,
        max_weight=0.12,
        add_rules_json=["add_on_pullback"],
        trim_rules_json=["trim_above_max_weight"],
        thesis_invalidators_json=["cloud_growth_breaks_down"],
        allowed_tactical_interactions_json=["pause_adds", "trim_for_risk"],
        lifecycle_status="active",
    )
    relationship = TickerRelationship(
        source_ticker="NVDA",
        target_ticker="MU",
        relationship_type="theme_leader",
        theme_id="ai_infra",
        confidence=0.8,
        strength_score=0.7,
        valid_from=datetime(2026, 6, 1, tzinfo=timezone.utc),
        valid_until=None,
        source_refs_json=[{"source": "manual_theme_map_v1"}],
        allowed_uses_json=["readthrough", "peer_basket"],
    )
    basket = PeerBasket(
        basket_key="nvda_ai_infra",
        version="v1",
        trade_date=date(2026, 6, 1),
        members_json=["LITE", "MU"],
        construction_method="relationship_graph_v1",
        source_refs_json=["manual_theme_map_v1"],
    )
    theme = ThemeTaxonomy(
        theme_id="ai_infra",
        display_name="AI Infrastructure",
        parent_theme_id=None,
        description="Compute and networking beneficiaries.",
        lifecycle_status="active",
    )

    assert intent.ticker == "GOOGL"
    assert relationship.target_ticker == "MU"
    assert basket.members_json == ["LITE", "MU"]
    assert theme.lifecycle_status == "active"


def test_pr_2_models_can_be_instantiated():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    config = UniverseFilterConfig(
        profile_name="default",
        version=1,
        is_active=True,
        min_price=5,
        min_avg_dollar_volume=25_000_000,
        included_sectors_json=["Technology"],
        excluded_sectors_json=[],
        included_industries_json=[],
        excluded_industries_json=[],
        exchanges_json=["NASDAQ"],
        asset_types_json=["common_stock"],
        manual_include_json=[],
        manual_exclude_json=[],
    )
    universe = UniverseSnapshot(
        filter_config=config,
        snapshot_date=date(2026, 6, 1),
        started_at=now,
        completed_at=now,
        provider="fixture",
        status="succeeded",
        included_count=1,
        excluded_count=0,
    )
    symbol = UniverseSymbol(
        universe_snapshot=universe,
        symbol="AAPL",
        company_name="Apple",
        asset_type="common_stock",
        exchange="NASDAQ",
        sector="Technology",
        industry="Hardware",
        price=180,
        avg_dollar_volume=90_000_000,
        status="included",
        exclusion_reason=None,
    )
    manual = ManualTickerRequest(
        ticker="AAPL",
        reason="forced review",
        mode="review_only",
        status="active",
        created_at=now,
    )
    ingestion = SourceIngestionRun(
        source_family="fundamental",
        run_type="targeted",
        scope_json={"tickers": ["AAPL"]},
        provider="fixture",
        as_of=now,
        status="succeeded",
        coverage_json={"count": 1},
    )
    request = ProviderRequestRun(
        provider="fixture",
        endpoint="fundamentals",
        source_family="fundamental",
        scope_json={"ticker": "AAPL"},
        cache_status="miss",
        request_count=1,
        budget_remaining=99,
        retry_count=0,
        backoff_ms=0,
        latency_ms=5,
        status="succeeded",
        error_code=None,
        circuit_state="closed",
        degraded_mode=False,
        started_at=now,
        completed_at=now,
    )
    fundamental = FundamentalSnapshot(
        ticker="AAPL",
        fiscal_period="2026Q1",
        as_of_date=date(2026, 3, 31),
        provider="fixture",
        source_refs_json=[{"id": "fund-1"}],
        event_time=now,
        published_at=now,
        ingested_at=now,
        available_for_decision_at=now,
        raw_payload_ref="fixture://fund-1",
        normalized_metrics_json={"revenue_growth_score": 0.7},
    )
    event = EventNewsItem(
        ticker="AAPL",
        source_ticker=None,
        event_type="analyst_upgrade",
        direction="positive",
        sentiment="positive",
        importance="high",
        headline="Analyst upgrade",
        summary="Upgrade",
        provider="fixture",
        source_refs_json=[{"id": "event-1"}],
        dedupe_key="AAPL|analyst_upgrade|2026-06-01",
        event_time=now,
        published_at=now,
        ingested_at=now,
        available_for_decision_at=now,
        raw_payload_ref="fixture://event-1",
    )
    signal = SignalSnapshot(
        ticker="AAPL",
        snapshot_type="pre_open",
        decision_time=now,
        available_for_decision_at=now,
        max_input_available_for_decision_at=now,
        signal_json={"technical": {}},
        source_freshness_json={"technical": "fresh"},
        missing_signals_json=["option_chain_availability"],
        stale_signals_json=[],
        source_record_refs_json=[{"source_record_id": "fund-1"}],
        source_available_times_json={"fund-1": now.isoformat()},
        excluded_future_source_count=0,
        point_in_time_passed=True,
        selection_source="scanner",
    )

    assert config.profile_name == "default"
    assert symbol.status == "included"
    assert manual.mode == "review_only"
    assert ingestion.status == "succeeded"
    assert request.circuit_state == "closed"
    assert fundamental.normalized_metrics_json["revenue_growth_score"] == 0.7
    assert event.dedupe_key.startswith("AAPL|")
    assert signal.point_in_time_passed is True


def test_pr_3_models_can_be_instantiated():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    run = StrategyRun(
        decision_time=now,
        snapshot_type="pre_open",
        status="succeeded",
        metadata_json={"source": "unit"},
    )
    candidate = CandidateScore(
        strategy_run=run,
        signal_snapshot_id=None,
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id=None,
        candidate_score=0.72,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence_json={"technical.rs_vs_spy_1d": 0.02},
        missing_required_signals_json=[],
        unsupported_missing_signal_families_json=[],
        invalidators_json=["relative strength breaks"],
        risk_tags_json=["relative_strength"],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="relative strength confirmed",
        rejection_reason=None,
        benchmark_context_json={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )
    classification = TradeClassification(
        candidate_score=candidate,
        strategy_run=run,
        ticker="AAPL",
        selected_strategy_id="relative_strength_rotation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        watch_type=None,
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="actionable long stock",
        selected_strategy_context_json={"candidate_score": 0.72},
        decision_time=now,
    )
    replay = HistoricalReplayRun(
        decision_time=now,
        snapshot_type="pre_open",
        status="succeeded",
        started_at=now,
        completed_at=now,
        decision_filter_json={"available_for_decision_at_lte": now.isoformat()},
        outcome_horizon_policy_json={"default_days": 5},
        metadata_json={},
    )
    outcome = CandidateOutcomeEvaluation(
        historical_replay_run=replay,
        candidate_score=candidate,
        trade_classification=classification,
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        trade_identity="tactical_stock_trade",
        direction="bullish",
        catalyst_type="analyst_upgrade",
        confidence_bucket="relative_strength_rotation_v1|long_stock|tactical_stock_trade|bullish|analyst_upgrade",
        decision_time=now,
        horizon_start_at=now,
        horizon_end_at=now,
        evaluation_status="final",
        candidate_return=0.08,
        benchmark_returns_json={"QQQ": 0.02},
        peer_basket_id=None,
        peer_basket_return=None,
        alpha=0.06,
        max_favorable_excursion=0.1,
        max_adverse_excursion=-0.02,
        regime=None,
        sector_theme=None,
        metadata_json={},
    )

    assert candidate.strategy_run is run
    assert classification.candidate_score is candidate
    assert replay.status == "succeeded"
    assert outcome.trade_classification is classification
    assert outcome.alpha == 0.06


def test_pr_4_models_can_be_instantiated():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    sizing = PositionSizingDecision(
        candidate_score_id=None,
        trade_classification_id=None,
        ticker="AAPL",
        risk_appetite="balanced",
        base_weight=0.06,
        volatility_adjusted_weight=0.05,
        liquidity_capped_weight=0.04,
        final_weight=0.04,
        final_notional=4_000,
        applied_caps_json=["liquidity_cap"],
        binding_constraint="liquidity_cap",
        decision_time=now,
        metadata_json={},
    )
    snapshot = PortfolioRiskSnapshot(
        decision_time=now,
        risk_appetite="balanced",
        resolver_version="risk_config_resolver_v1",
        margin_model_profile="estimated_fidelity_like_conservative_v1",
        margin_model_version="v1",
        account_equity=100_000,
        cash_balance=20_000,
        buying_power=180_000,
        excess_liquidity=60_000,
        stock_margin_requirement=12_000,
        option_margin_requirement=0,
        total_margin_requirement=12_000,
        initial_margin_requirement=12_000,
        maintenance_margin_requirement=8_000,
        margin_requirement_source="estimated",
        net_exposure=40_000,
        gross_exposure=40_000,
        beta_adjusted_net_exposure=44_000,
        concentration_flags_json=["sector:Technology"],
        metadata_json={},
    )
    exposure = RiskFactorExposure(
        portfolio_risk_snapshot=snapshot,
        factor_type="sector",
        factor_value="Technology",
        gross_exposure=40_000,
        net_exposure=40_000,
        long_exposure=40_000,
        short_exposure=0,
        position_count=2,
        metadata_json={},
    )
    decision = RiskDecision(
        candidate_score_id=None,
        trade_classification_id=None,
        position_sizing_decision=sizing,
        portfolio_risk_snapshot=snapshot,
        ticker="AAPL",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.04,
        approved_notional=4_000,
        approved_quantity=40,
        applied_rules_json=["single_name_limit_ok"],
        generated_hedge_action_json=None,
        decision_time=now,
        metadata_json={},
    )

    assert sizing.risk_appetite == "balanced"
    assert snapshot.margin_model_profile == "estimated_fidelity_like_conservative_v1"
    assert exposure.portfolio_risk_snapshot is snapshot
    assert decision.position_sizing_decision is sizing


def test_pr_5_models_can_be_instantiated():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    decision = TradingDecision(
        candidate_score_id=None,
        trade_classification_id=None,
        risk_decision_id=None,
        prompt_run_id=None,
        ticker="NVDA",
        decision="no_trade",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        selection_source="manual_request",
        manual_request_id=None,
        confidence=0.0,
        target_weight=0.0,
        approved_weight=0.0,
        max_loss_pct=0.0,
        time_horizon="2w-3m",
        thesis="Review-only manual request found the setup actionable but did not authorize a trade.",
        invalidators_json=["QQQ breaks trend"],
        fallback_action="no_trade",
        paper_trade_authorized=False,
        context_snapshot_json={"manual_request_mode": "review_only"},
        metadata_json={"paper_trade_authorized": False},
        decision_time=now,
        available_for_decision_at=now,
    )

    assert decision.ticker == "NVDA"
    assert decision.decision == "no_trade"
    assert decision.paper_trade_authorized is False


def test_pr_6_models_can_be_instantiated():
    now = datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    order = PaperOrder(
        broker_order_id="broker-order-1",
        client_order_id="2026-06-01:NVDA:relative_strength_rotation_v1:enter_long",
        trading_decision_id=None,
        risk_decision_id=None,
        ticker="NVDA",
        strategy_id="relative_strength_rotation_v1",
        action="enter_long",
        trade_date=now.date(),
        quantity=25,
        order_price=200.0,
        status="filled",
        rejection_reason=None,
    )
    execution = PaperExecution(
        paper_order=order,
        broker_order_id="broker-order-1",
        ticker="NVDA",
        quantity=25,
        fill_price=200.0,
        trade_date=now.date(),
        executed_at=now,
        net_cash_effect=-5_000.0,
    )
    position = PaperPosition(
        ticker="NVDA",
        strategy_id="relative_strength_rotation_v1",
        trade_identity="tactical_stock_trade",
        direction="long",
        quantity=25,
        average_cost=200.0,
        market_price=200.0,
        market_value=5_000.0,
        opened_at=now,
        updated_at=now,
        status="open",
    )
    snapshot = PortfolioSnapshot(
        snapshot_time=now,
        cash_balance=95_000.0,
        account_equity=100_000.0,
        net_liquidation_value=100_000.0,
        buying_power=97_500.0,
        excess_liquidity=98_500.0,
        stock_market_value=5_000.0,
        option_market_value=0.0,
        stock_margin_requirement=2_500.0,
        option_margin_requirement=0.0,
        total_margin_requirement=2_500.0,
        initial_margin_requirement=2_500.0,
        maintenance_margin_requirement=1_500.0,
        margin_model_profile="estimated_fidelity_like_conservative_v1",
        margin_model_version="v1",
        margin_requirement_source="estimated",
        day_pnl=0.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        metadata_json={},
    )

    assert execution.paper_order is order
    assert order.client_order_id == "2026-06-01:NVDA:relative_strength_rotation_v1:enter_long"
    assert position.status == "open"
    assert snapshot.margin_model_profile == "estimated_fidelity_like_conservative_v1"


def test_trading_migration_contains_pr_1a_tables():
    migration_path = Path("alembic/versions/005_trading_minimal_foundation_tables.py")
    text = migration_path.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "004"' in text
    assert '"strategy_definitions"' in text
    assert '"llm_prompt_templates"' in text
    assert '"llm_prompt_runs"' in text
    assert '"llm_usage_events"' in text


def test_trading_migration_contains_pr_1b_tables_and_constraints():
    migration_path = Path("alembic/versions/006_portfolio_intents_relationship_graph.py")
    text = migration_path.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "005"' in text
    assert '"portfolio_intents"' in text
    assert '"ticker_relationships"' in text
    assert '"peer_baskets"' in text
    assert '"theme_taxonomy"' in text
    assert "ck_portfolio_intents_lifecycle_status" in text
    assert "ck_ticker_relationships_relationship_type" in text
    assert "ck_ticker_relationships_confidence" in text
    assert "ck_ticker_relationships_strength_score" in text
    assert "ck_theme_taxonomy_lifecycle_status" in text


def test_trading_migration_contains_pr_2_tables_and_pit_columns():
    migration_path = Path("alembic/versions/007_universe_signal_mvp_tables.py")
    text = migration_path.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "006"' in text
    for table_name in (
        '"universe_filter_configs"',
        '"universe_snapshots"',
        '"universe_symbols"',
        '"manual_ticker_requests"',
        '"source_ingestion_runs"',
        '"provider_request_runs"',
        '"fundamental_snapshots"',
        '"event_news_items"',
        '"signal_snapshots"',
    ):
        assert table_name in text
    for required_column in (
        '"decision_time"',
        '"available_for_decision_at"',
        '"max_input_available_for_decision_at"',
        '"source_record_refs_json"',
        '"source_available_times_json"',
        '"excluded_future_source_count"',
        '"point_in_time_passed"',
    ):
        assert required_column in text


def test_trading_migration_contains_pr_3_tables_and_constraints():
    migration_path = Path("alembic/versions/008_strategy_matching_replay_tables.py")
    text = migration_path.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "007"' in text
    for table_name in (
        '"strategy_runs"',
        '"candidate_scores"',
        '"trade_classifications"',
        '"historical_replay_runs"',
        '"candidate_outcome_evaluations"',
    ):
        assert table_name in text
    for constraint_name in (
        "ck_candidate_scores_score_range",
        "ck_candidate_scores_selection_source",
        "ck_trade_classifications_trade_identity",
        "ck_trade_classifications_watch_type",
        "ck_candidate_outcome_evaluations_status",
    ):
        assert constraint_name in text


def test_trading_migration_contains_pr_4_tables_and_constraints():
    migration_path = Path("alembic/versions/009_position_sizing_risk_manager_tables.py")
    text = migration_path.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "008"' in text
    for table_name in (
        '"position_sizing_decisions"',
        '"portfolio_risk_snapshots"',
        '"risk_factor_exposures"',
        '"risk_decisions"',
    ):
        assert table_name in text
    for constraint_name in (
        "ck_position_sizing_decisions_risk_appetite",
        "ck_position_sizing_decisions_weight_range",
        "ck_portfolio_risk_snapshots_risk_appetite",
        "ck_risk_factor_exposures_position_count",
        "ck_risk_decisions_status",
    ):
        assert constraint_name in text


def test_trading_migration_contains_pr_5_tables_and_constraints():
    migration_path = Path("alembic/versions/010_trading_decision_guardrails.py")
    text = migration_path.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "009"' in text
    assert '"trading_decisions"' in text
    for constraint_name in (
        "ck_trading_decisions_decision",
        "ck_trading_decisions_trade_identity",
        "ck_trading_decisions_instrument_type",
        "ck_trading_decisions_selection_source",
        "ck_trading_decisions_weight_ranges",
    ):
        assert constraint_name in text


def test_trading_migration_contains_pr_6_tables_and_constraints():
    migration_path = Path("alembic/versions/011_paper_stock_broker_portfolio_state.py")
    text = migration_path.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "010"' in text
    for table_name in (
        '"paper_orders"',
        '"paper_executions"',
        '"paper_positions"',
        '"portfolio_snapshots"',
    ):
        assert table_name in text
    for constraint_name in (
        "uq_paper_orders_client_order_id",
        "ck_paper_orders_action",
        "ck_paper_orders_status",
        "ck_paper_positions_direction",
        "ck_paper_positions_status",
    ):
        assert constraint_name in text
