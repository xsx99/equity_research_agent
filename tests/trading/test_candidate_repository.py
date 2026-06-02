from datetime import datetime, timezone

from src.trading.brokers.paper_stock import PaperExecutionRecord, PaperOrderRecord
from src.trading.portfolio.state import PortfolioSnapshot, StockPosition
from src.trading.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.risk import PortfolioRiskSnapshotRecord, PositionSizingDecisionRecord, RiskDecisionRecord, RiskFactorExposureRecord
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord, StrategyRunRecord


def test_in_memory_repository_stores_pr3_artifacts_and_filters_active_definitions():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    repo = InMemoryTradingRepository()
    active = StrategyDefinitionRecord(
        strategy_definition_id="active-id",
        strategy_id="relative_strength_rotation_v1",
        version="v1",
        display_name="Relative Strength",
        strategy_layer="tactical_pattern",
        typical_horizon="2w-3m",
        config_json={},
        lifecycle_status="active",
        is_active=True,
    )
    retired = StrategyDefinitionRecord(
        strategy_definition_id="retired-id",
        strategy_id="old_v1",
        version="v1",
        display_name="Old",
        strategy_layer="tactical_pattern",
        typical_horizon="1d",
        config_json={},
        lifecycle_status="retired",
        is_active=False,
    )
    run = StrategyRunRecord(
        strategy_run_id="run-1",
        decision_time=now,
        snapshot_type="pre_open",
        status="succeeded",
        metadata_json={},
    )
    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="active-id",
        candidate_score=0.7,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=[],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="relative strength",
        rejection_reason=None,
        benchmark_context={},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )
    outcome = CandidateOutcomeEvaluationRecord(
        candidate_outcome_evaluation_id="outcome-1",
        historical_replay_run_id=None,
        candidate_score_id="candidate-1",
        trade_classification_id=None,
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        trade_identity="watch_only",
        direction="bullish",
        catalyst_type=None,
        confidence_bucket="bucket",
        decision_time=now,
        horizon_start_at=now,
        horizon_end_at=now,
        evaluation_status="final",
        candidate_return=0.04,
        benchmark_returns={"QQQ": 0.02},
        peer_basket_id=None,
        peer_basket_return=None,
        alpha=0.02,
        max_favorable_excursion=0.05,
        max_adverse_excursion=-0.01,
        regime=None,
        sector_theme=None,
        metadata_json={},
    )

    repo.save_strategy_definition(active)
    repo.save_strategy_definition(retired)
    repo.save_strategy_run(run)
    repo.save_candidate_scores([candidate])
    repo.save_candidate_outcome_evaluations([outcome])

    assert repo.load_active_strategy_definitions() == [active]
    assert repo.strategy_runs == [run]
    assert repo.candidate_scores == [candidate]
    assert repo.candidate_outcome_evaluations == [outcome]


def test_in_memory_repository_stores_pr4_risk_artifacts():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    repo = InMemoryTradingRepository()
    sizing = PositionSizingDecisionRecord(
        position_sizing_decision_id="sizing-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        ticker="AAPL",
        risk_appetite="balanced",
        base_weight=0.06,
        volatility_adjusted_weight=0.04,
        liquidity_capped_weight=0.03,
        final_weight=0.03,
        final_notional=3_000,
        applied_caps=["liquidity_cap"],
        binding_constraint="liquidity_cap",
        decision_time=now,
        metadata_json={},
    )
    exposure = RiskFactorExposureRecord(
        factor_type="sector",
        factor_value="Technology",
        gross_exposure=30_000,
        net_exposure=30_000,
        long_exposure=30_000,
        short_exposure=0,
        position_count=2,
        metadata_json={},
    )
    snapshot = PortfolioRiskSnapshotRecord(
        portfolio_risk_snapshot_id="snapshot-1",
        decision_time=now,
        risk_appetite="balanced",
        resolver_version="risk_config_resolver_v1",
        margin_model_profile="estimated_fidelity_like_conservative_v1",
        margin_model_version="v1",
        account_equity=100_000,
        cash_balance=25_000,
        buying_power=180_000,
        excess_liquidity=50_000,
        stock_margin_requirement=12_000,
        option_margin_requirement=0,
        total_margin_requirement=12_000,
        initial_margin_requirement=12_000,
        maintenance_margin_requirement=8_000,
        margin_requirement_source="estimated",
        net_exposure=30_000,
        gross_exposure=30_000,
        beta_adjusted_net_exposure=36_000,
        concentration_flags=["sector:Technology"],
        metadata_json={},
    )
    decision = RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="AAPL",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.03,
        approved_notional=3_000,
        approved_quantity=30,
        portfolio_risk_snapshot_id="snapshot-1",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )

    repo.save_position_sizing_decision(sizing)
    repo.save_risk_factor_exposures([exposure])
    repo.save_portfolio_risk_snapshot(snapshot)
    repo.save_risk_decision(decision)

    assert repo.position_sizing_decisions == [sizing]
    assert repo.risk_factor_exposures == [exposure]
    assert repo.portfolio_risk_snapshots == [snapshot]
    assert repo.risk_decisions == [decision]


def test_in_memory_repository_stores_pr6_paper_broker_artifacts_idempotently():
    now = datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    repo = InMemoryTradingRepository()
    order = PaperOrderRecord(
        paper_order_id="order-1",
        broker_order_id="broker-order-1",
        client_order_id="2026-06-01:NVDA:relative_strength_rotation_v1:enter_long",
        trading_decision_id="decision-1",
        risk_decision_id="risk-1",
        ticker="NVDA",
        strategy_id="relative_strength_rotation_v1",
        action="enter_long",
        trade_date=now.date(),
        quantity=25.0,
        limit_price=200.0,
        status="filled",
        rejection_reason=None,
        created_at=now,
    )
    execution = PaperExecutionRecord(
        paper_execution_id="execution-1",
        paper_order_id="order-1",
        broker_order_id="broker-order-1",
        ticker="NVDA",
        quantity=25.0,
        fill_price=200.0,
        trade_date=now.date(),
        executed_at=now,
        net_cash_effect=-5_000.0,
    )
    position = StockPosition(
        ticker="NVDA",
        quantity=25.0,
        average_cost=200.0,
        market_price=200.0,
        market_value=5_000.0,
        trade_identity="tactical_stock_trade",
        strategy_id="relative_strength_rotation_v1",
        opened_at=now,
        updated_at=now,
        direction="long",
    )
    snapshot = PortfolioSnapshot(
        as_of=now,
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
    )

    repo.save_paper_order(order)
    repo.save_paper_order(order)
    repo.save_paper_execution(execution)
    repo.save_paper_position(position)
    repo.save_portfolio_snapshot(snapshot)

    assert repo.paper_orders == [order]
    assert repo.paper_executions == [execution]
    assert repo.paper_positions == [position]
    assert repo.portfolio_snapshots == [snapshot]
    assert repo.has_paper_execution("execution-1") is True
