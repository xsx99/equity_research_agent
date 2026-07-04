"""Fixture-backed smoke handlers for preopen, manual-review, and intraday paths."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

from src.db.connection import get_session
from src.db.models.trading import SignalSnapshot as SignalSnapshotModel
from src.db.models.trading import UniverseFilterConfig as UniverseFilterConfigModel
from src.db.models.trading import UniverseSnapshot as UniverseSnapshotModel
from src.db.models.trading import UniverseSymbol as UniverseSymbolModel
from src.trading.phases.intraday.news_alerts import AlertSourceItem, NewsAlertService
from src.trading.phases.intraday.signals import build_intraday_signal_snapshot
from src.trading.options.strategy import (
    OptionLegDefinition,
    OptionStrategyDecisionInput,
    OptionsStrategyLayer,
)
from src.trading.phases.replay.historical import HistoricalReplayRunner
from src.trading.phases.replay.outcomes import OutcomeEvaluator, PricePoint
from src.trading.phases.manual_review import LiveManualReviewDependencies, LiveManualReviewRuntime
from src.trading.phases.manual_review.requests import ManualTickerRequestService
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.risk import HedgeActionRecord, PortfolioRiskIntentRecord, RiskDecisionRecord
from src.trading.risk.config import RiskConfigResolver
from src.trading.risk.options import OptionLegRiskInput, OptionRiskInput, OptionRiskManager
from src.trading.workflows.paper_execution import PaperExecutionWorkflow
from src.trading.workflows.trading_decision import TradingDecisionRecord

from src.trading.risk.lookahead_risk import LookaheadRiskWorkflowHelper
from .smoke_support import (
    _FakePaperStockBroker,
    _build_preopen_fixture_run,
    _build_universe_and_snapshots,
    _decimal_or_none,
    _empty_portfolio_context,
    _fixed_now,
    _manual_snapshot,
    _seed_strategy_definitions,
    _uuid_or_none,
)


def run_trading_preopen_once() -> dict[str, Any]:
    """Run the fixture-backed pre-open universe/signal/strategy path."""
    decision_time = _fixed_now()
    universe_result, snapshots, strategy_result, repository = _build_preopen_fixture_run(decision_time)
    return {
        "status": "passed",
        "phase": "preopen",
        "as_of": decision_time.isoformat(),
        "summary": {
            "included_symbols": list(universe_result.included_symbols),
            "excluded_count": len(universe_result.excluded),
            "signal_snapshot_count": len(snapshots),
            "candidate_count": len(strategy_result.candidates),
            "classification_count": len(strategy_result.classifications),
            "provider_request_count": len(repository.provider_request_runs),
        },
    }


def run_manual_ticker_review_once() -> dict[str, Any]:
    """Run the active-manual-review path with a fixture-backed review_only request."""
    return _run_manual_review_fixture()


def run_intraday_signal_refresh_once() -> dict[str, Any]:
    """Run the hourly intraday refresh path with fixture data."""
    return _run_intraday_refresh_fixture()


def _run_provider_guardrail_fixture() -> dict[str, Any]:
    preopen = run_trading_preopen_once()
    return {
        "status": preopen["status"],
        "mode": "provider_guardrail_fixture",
        "summary": {
            "provider_request_count": preopen["summary"]["provider_request_count"],
            "signal_snapshot_count": preopen["summary"]["signal_snapshot_count"],
            "included_symbols": preopen["summary"]["included_symbols"],
        },
    }


def _run_universe_signal_db_write() -> dict[str, Any]:
    decision_time = _fixed_now()
    universe_result, snapshots, _repository = _build_universe_and_snapshots(decision_time)
    persisted = False
    persisted_rows = {"universe_snapshots": 0, "signal_snapshots": 0}
    try:
        with get_session() as session:
            filter_row = UniverseFilterConfigModel(
                universe_filter_config_id=uuid.uuid4(),
                profile_name=universe_result.filter_config.profile_name,
                version=universe_result.filter_config.version,
                is_active=universe_result.filter_config.is_active,
                min_price=_decimal_or_none(universe_result.filter_config.min_price),
                min_avg_dollar_volume=_decimal_or_none(universe_result.filter_config.min_avg_dollar_volume),
                included_sectors_json=list(universe_result.filter_config.included_sectors),
                excluded_sectors_json=list(universe_result.filter_config.excluded_sectors),
                included_industries_json=list(universe_result.filter_config.included_industries),
                excluded_industries_json=list(universe_result.filter_config.excluded_industries),
                exchanges_json=list(universe_result.filter_config.exchanges),
                asset_types_json=list(universe_result.filter_config.asset_types),
                manual_include_json=list(universe_result.filter_config.manual_include),
                manual_exclude_json=list(universe_result.filter_config.manual_exclude),
            )
            session.add(filter_row)
            snapshot_row = UniverseSnapshotModel(
                universe_snapshot_id=uuid.UUID(universe_result.snapshot_id),
                universe_filter_config_id=filter_row.universe_filter_config_id,
                snapshot_date=decision_time.date(),
                started_at=universe_result.snapshot_time,
                completed_at=universe_result.snapshot_time,
                provider="fixture",
                status="succeeded",
                included_count=len(universe_result.included),
                excluded_count=len(universe_result.excluded),
                metadata_json=dict(universe_result.metadata),
            )
            session.add(snapshot_row)
            for decision in (*universe_result.included, *universe_result.excluded):
                session.add(
                    UniverseSymbolModel(
                        universe_symbol_id=uuid.uuid4(),
                        universe_snapshot_id=snapshot_row.universe_snapshot_id,
                        symbol=decision.symbol,
                        company_name=decision.asset.company_name,
                        asset_type=decision.asset.asset_type,
                        exchange=decision.asset.exchange,
                        sector=decision.asset.sector,
                        industry=decision.asset.industry,
                        price=_decimal_or_none(decision.asset.price),
                        avg_dollar_volume=_decimal_or_none(decision.asset.avg_dollar_volume),
                        status=decision.status,
                        exclusion_reason=decision.exclusion_reason,
                        metadata_json={},
                    )
                )
            for snapshot in snapshots:
                session.add(
                    SignalSnapshotModel(
                        signal_snapshot_id=uuid.UUID(snapshot.signal_snapshot_id),
                        ticker=snapshot.ticker,
                        snapshot_type=snapshot.snapshot_type,
                        decision_time=snapshot.decision_time,
                        available_for_decision_at=snapshot.available_for_decision_at,
                        max_input_available_for_decision_at=snapshot.max_input_available_for_decision_at,
                        signal_json=dict(snapshot.signal_json),
                        source_freshness_json=dict(snapshot.source_freshness_json),
                        missing_signals_json=list(snapshot.missing_signals_json),
                        stale_signals_json=list(snapshot.stale_signals_json),
                        source_record_refs_json=list(snapshot.source_record_refs_json),
                        source_available_times_json=dict(snapshot.source_available_times_json),
                        excluded_future_source_count=snapshot.excluded_future_source_count,
                        point_in_time_passed=snapshot.point_in_time_passed,
                        selection_source=snapshot.selection_source,
                        manual_request_id=_uuid_or_none(snapshot.manual_request_id),
                        universe_snapshot_id=snapshot_row.universe_snapshot_id,
                        metadata_json={},
                    )
                )
            persisted = True
            persisted_rows = {
                "universe_snapshots": 1,
                "signal_snapshots": len(snapshots),
            }
    except Exception as exc:  # pragma: no cover - depends on external Postgres
        return {
            "status": "failed",
            "mode": "universe_signal_db_write",
            "error": str(exc),
            "summary": {
                "db_persisted": False,
                "included_symbols": list(universe_result.included_symbols),
                "signal_snapshot_count": len(snapshots),
            },
        }
    return {
        "status": "passed" if persisted else "failed",
        "mode": "universe_signal_db_write",
        "summary": {
            "db_persisted": persisted,
            "persisted_rows": persisted_rows,
            "included_symbols": list(universe_result.included_symbols),
            "signal_snapshot_count": len(snapshots),
        },
    }


def _run_historical_replay_fixture() -> dict[str, Any]:
    decision_time = _fixed_now()
    repository = InMemoryTradingRepository()
    _seed_strategy_definitions(repository)
    snapshot = _manual_snapshot("AAPL", decision_time)
    repository.save_signal_snapshot(snapshot)
    replay = HistoricalReplayRunner(
        repository=repository,
        outcome_evaluator=OutcomeEvaluator(
            price_points={
                "AAPL": [
                    PricePoint(decision_time, 100.0),
                    PricePoint(decision_time + timedelta(days=5), 108.0),
                ],
                "QQQ": [
                    PricePoint(decision_time, 400.0),
                    PricePoint(decision_time + timedelta(days=5), 404.0),
                ],
                "SPY": [
                    PricePoint(decision_time, 500.0),
                    PricePoint(decision_time + timedelta(days=5), 505.0),
                ],
            }
        ),
        now=lambda: decision_time,
    ).run(
        decision_time=decision_time,
        horizon_end_at=decision_time + timedelta(days=5),
    )
    return {
        "status": "passed",
        "mode": "historical_replay_fixture",
        "summary": {
            "candidate_count": len(replay.candidates),
            "selected_count": len(replay.selected_trades),
            "outcome_count": len(replay.outcomes),
            "tickers": [candidate.ticker for candidate in replay.candidates],
        },
    }


def _run_paper_trade_dry_run() -> dict[str, Any]:
    from scripts.run_trading_paper_execution import run_execution

    result = run_execution(
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        trade_identity="tactical_stock_trade",
        decision="enter_long",
        quantity=0.01,
        broker=_FakePaperStockBroker(),
        as_of=_fixed_now(),
    )
    return {
        "status": result["status"],
        "mode": "paper_trade_dry_run",
        "summary": {
            "order_status": result["order"]["status"] if result["order"] is not None else None,
            "position_count": len(result["positions"]),
            "cash_balance": (
                result["portfolio_snapshot"]["cash_balance"]
                if result["portfolio_snapshot"] is not None
                else None
            ),
        },
    }


def _run_manual_review_fixture() -> dict[str, Any]:
    decision_time = _fixed_now()
    universe_result, snapshots, _repository = _build_universe_and_snapshots(
        decision_time,
        with_manual_request=True,
    )
    manual_snapshot = next(snapshot for snapshot in snapshots if snapshot.ticker == "NVDA")
    return {
        "status": "passed",
        "mode": "manual_review_fixture",
        "summary": {
            "active_manual_requests": 1,
            "latest_result_status": "ordinary_watch",
            "manual_request_ticker": manual_snapshot.ticker,
            "included_symbols": list(universe_result.included_symbols),
        },
    }


def _run_manual_review_execution_fixture() -> dict[str, Any]:
    decision_time = _fixed_now()
    repository = InMemoryTradingRepository()
    manual_service = ManualTickerRequestService(now=lambda: decision_time)
    request = manual_service.create("AAPL", "fixture executable request", "paper_trade_eligible")
    broker = _FakePaperStockBroker()

    class _SignalPipeline:
        def build_pre_open_snapshots(self, *, universe_result: object, decision_time: object) -> tuple[object, ...]:
            manual_service.record_evaluation(
                request.request_id,
                result_status="actionable_trade",
                signal_snapshot_id="snapshot-1",
            )
            return (SimpleNamespace(ticker="AAPL"),)

    risk_decision = RiskDecisionRecord.create(
        candidate_score_id=None,
        trade_classification_id=None,
        position_sizing_decision_id=None,
        ticker="AAPL",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.01,
        approved_notional=3.15,
        approved_quantity=0.01,
        portfolio_risk_snapshot_id=None,
        applied_rules=["fixture_manual_review_execution"],
        decision_time=decision_time,
    )
    trading_decision = TradingDecisionRecord(
        trading_decision_id=str(uuid.uuid4()),
        candidate_score_id=None,
        trade_classification_id=None,
        risk_decision_id=risk_decision.risk_decision_id,
        ticker="AAPL",
        decision="enter_long",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        selection_source="manual_request",
        manual_request_id=request.request_id,
        confidence=0.81,
        target_weight=0.01,
        approved_weight=0.01,
        max_loss_pct=0.02,
        time_horizon="intraday",
        thesis="Fixture manual review execution path.",
        prompt_template=None,
        prompt_run=None,
        usage_events=[],
        decision_time=decision_time,
        available_for_decision_at=decision_time,
        metadata_json={
            "paper_trade_authorized": True,
            "manual_request_mode": "paper_trade_eligible",
        },
    )

    runtime = LiveManualReviewRuntime(
        dependencies=LiveManualReviewDependencies(
            universe_filter_loader=SimpleNamespace(load_active=lambda: SimpleNamespace()),
            manual_request_loader=manual_service,
            universe_scan_pipeline=SimpleNamespace(
                run=lambda **kwargs: SimpleNamespace(included_symbols=("AAPL",))
            ),
            signal_pipeline=_SignalPipeline(),
            strategy_pipeline=SimpleNamespace(
                run=lambda **kwargs: SimpleNamespace(
                    candidates=(SimpleNamespace(ticker="AAPL"),),
                    classifications=(SimpleNamespace(ticker="AAPL"),),
                )
            ),
            portfolio_sync_workflow=SimpleNamespace(
                run=lambda **kwargs: SimpleNamespace(portfolio_context=_empty_portfolio_context(decision_time))
            ),
            risk_workflow=SimpleNamespace(
                run=lambda **kwargs: SimpleNamespace(risk_decisions=(risk_decision,))
            ),
            trading_decision_pipeline=SimpleNamespace(
                run=lambda **kwargs: SimpleNamespace(decisions=(trading_decision,))
            ),
            paper_execution_workflow=PaperExecutionWorkflow(
                repository=repository,
                broker=broker,
                manual_request_service=manual_service,
            ),
            trading_repository=None,
        ),
        now=lambda: decision_time,
        execute_paper_orders=True,
    )
    result = runtime.run()
    order = repository.paper_orders[0]
    return {
        "status": result["status"],
        "mode": "manual_review_execution_fixture",
        "summary": {
            "active_manual_requests": 1,
            "latest_result_status": manual_service.load_active()[0].latest_result_status,
            "orders_submitted": result["execution"]["orders_submitted"],
            "latest_order_status": order.status,
        },
    }


def _run_paper_option_fixture() -> dict[str, Any]:
    decision_time = _fixed_now()
    layer = OptionsStrategyLayer()
    input_data = OptionStrategyDecisionInput(
        trading_decision_id=str(uuid.uuid4()),
        ticker="NVDA",
        trade_identity="tactical_option_trade",
        option_strategy_type="long_call",
        decision_action="open_option_strategy",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        decision_time=decision_time,
        expiry=date(2026, 6, 19),
        underlying_price=120.0,
        earnings_date=date(2026, 6, 30),
        event_through_expiry=False,
        profit_target_pct=0.5,
        max_loss_rule="premium_paid",
        roll_conditions=("delta_drops",),
        close_conditions=("take_profit",),
        margin_model_profile="estimated_fidelity_like_conservative_v1",
        margin_model_version="v1",
        margin_requirement_source="simulated_formula",
        strategy_pairing_method="single_leg",
        assignment_plan=None,
        legs=(
            OptionLegDefinition(
                option_type="call",
                side="buy",
                quantity=1,
                strike=125.0,
                expiry=date(2026, 6, 19),
                dte=17,
                delta=0.42,
                gamma=0.03,
                theta=-0.02,
                vega=0.08,
                iv_rank=0.65,
                bid=2.2,
                ask=2.4,
                mid=2.3,
                chosen_price=2.3,
            ),
        ),
    )
    decision = layer.build_strategy(input_data)
    legs = layer.build_legs(decision)
    portfolio_context = _empty_portfolio_context(decision_time)
    option_risk = OptionRiskManager().evaluate_assignment_risk(
        OptionRiskInput(
            ticker="NVDA",
            trade_identity=decision.trade_identity,
            option_strategy_type=decision.option_strategy_type,
            underlying_price=decision.underlying_price,
            sector="Technology",
            event_type="earnings",
            event_through_expiry=decision.event_through_expiry,
            margin_requirement=decision.margin_requirement,
            buying_power_effect=decision.buying_power_effect,
            max_loss=decision.max_loss,
            max_profit=decision.max_profit,
            net_debit_or_credit=decision.net_debit_or_credit,
            legs=[
                OptionLegRiskInput(
                    option_type=leg.option_type,
                    side=leg.side,
                    quantity=leg.quantity,
                    strike=leg.strike,
                    expiry=leg.expiry,
                    delta=leg.delta,
                    gamma=leg.gamma,
                    theta=leg.theta,
                    vega=leg.vega,
                    premium=leg.chosen_price,
                )
                for leg in legs
            ],
        ),
        portfolio_context=portfolio_context,
        config=RiskConfigResolver().resolve(
            risk_appetite="balanced",
            portfolio_context=portfolio_context,
            macro_risk_budget_multiplier=1.0,
        ),
    )
    return {
        "status": "passed",
        "mode": "paper_option_fixture",
        "summary": {
            "decision_status": decision.status,
            "leg_count": len(legs),
            "risk_status": option_risk.status,
            "worst_case_assignment_notional": option_risk.worst_case_assignment_notional,
        },
    }


def _run_paper_option_lifecycle_fixture() -> dict[str, Any]:
    decision_time = _fixed_now()
    portfolio_context = _empty_portfolio_context(decision_time)
    config = RiskConfigResolver().resolve(
        risk_appetite="balanced",
        portfolio_context=portfolio_context,
        macro_risk_budget_multiplier=1.0,
    )
    layer = OptionsStrategyLayer()

    open_input = OptionStrategyDecisionInput(
        trading_decision_id=str(uuid.uuid4()),
        ticker="NVDA",
        trade_identity="tactical_option_trade",
        option_strategy_type="long_call",
        decision_action="open_option_strategy",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        decision_time=decision_time,
        expiry=date(2026, 6, 19),
        underlying_price=120.0,
        earnings_date=date(2026, 6, 30),
        event_through_expiry=False,
        profit_target_pct=0.5,
        max_loss_rule="premium_paid",
        roll_conditions=("delta_drops",),
        close_conditions=("take_profit",),
        margin_model_profile="estimated_fidelity_like_conservative_v1",
        margin_model_version="v1",
        margin_requirement_source="simulated_formula",
        strategy_pairing_method="single_leg",
        assignment_plan=None,
        legs=(
            OptionLegDefinition(
                option_type="call",
                side="buy",
                quantity=1,
                strike=125.0,
                expiry=date(2026, 6, 19),
                dte=17,
                delta=0.42,
                gamma=0.03,
                theta=-0.02,
                vega=0.08,
                iv_rank=0.65,
                bid=2.2,
                ask=2.4,
                mid=2.3,
                chosen_price=2.3,
            ),
        ),
    )
    open_decision = layer.build_strategy(open_input)
    open_legs = layer.build_legs(open_decision)
    open_risk = OptionRiskManager().evaluate_assignment_risk(
        _option_risk_input(
            decision=open_decision,
            legs=open_legs,
            sector="Technology",
            event_type="earnings",
        ),
        portfolio_context=portfolio_context,
        config=config,
    )

    reject_input = OptionStrategyDecisionInput(
        trading_decision_id=str(uuid.uuid4()),
        ticker="NVDA",
        trade_identity="tactical_option_trade",
        option_strategy_type="put_credit_spread",
        decision_action="open_option_strategy",
        strategy_id="earnings_drift_v1",
        strategy_version="v1",
        expression_bucket_id="defined_risk_income_spread",
        expression_bucket_version="v1",
        decision_time=decision_time,
        expiry=date(2026, 6, 19),
        underlying_price=118.0,
        earnings_date=date(2026, 6, 18),
        event_through_expiry=True,
        profit_target_pct=0.5,
        max_loss_rule="close_at_2x_credit",
        roll_conditions=("7_dte_if_otm",),
        close_conditions=("take_profit_50pct",),
        margin_model_profile="estimated_fidelity_like_conservative_v1",
        margin_model_version="v1",
        margin_requirement_source="simulated_formula",
        strategy_pairing_method="vertical_by_expiry_and_width",
        assignment_plan="close_or_roll_before_expiry_if_itm",
        legs=(
            OptionLegDefinition(
                option_type="put",
                side="sell",
                quantity=1,
                strike=115.0,
                expiry=date(2026, 6, 19),
                dte=17,
                delta=-0.29,
                gamma=0.02,
                theta=0.01,
                vega=-0.07,
                iv_rank=0.61,
                bid=1.4,
                ask=1.6,
                mid=1.5,
                chosen_price=1.5,
            ),
            OptionLegDefinition(
                option_type="put",
                side="buy",
                quantity=1,
                strike=110.0,
                expiry=date(2026, 6, 19),
                dte=17,
                delta=-0.18,
                gamma=0.01,
                theta=-0.01,
                vega=0.04,
                iv_rank=0.61,
                bid=0.8,
                ask=1.0,
                mid=0.9,
                chosen_price=0.9,
            ),
        ),
    )
    rejected_decision = layer.build_strategy(reject_input)
    rejected_legs = layer.build_legs(rejected_decision)
    rejected_risk = OptionRiskManager().evaluate_assignment_risk(
        _option_risk_input(
            decision=rejected_decision,
            legs=rejected_legs,
            sector="Technology",
            event_type="earnings",
        ),
        portfolio_context=portfolio_context,
        config=config,
    )

    hedge_seed = RiskDecisionRecord.create(
        candidate_score_id="candidate-NVDA",
        trade_classification_id="classification-NVDA",
        position_sizing_decision_id="sizing-NVDA",
        ticker="NVDA",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.02,
        approved_notional=rejected_decision.margin_requirement,
        approved_quantity=1.0,
        portfolio_risk_snapshot_id="snapshot-1",
        applied_rules=["portfolio_risk_intent"],
        decision_time=decision_time,
        metadata_json={
            "approved_margin_exposure": rejected_decision.margin_requirement,
            "approved_assignment_notional": rejected_decision.assignment_notional,
        },
    )
    hedge_intent = PortfolioRiskIntentRecord.create(
        decision_time=decision_time,
        risk_window="1-5d",
        aggregate_risk_state="assignment_risk",
        hedge_actions=(
            HedgeActionRecord(
                action="adjust_hedge",
                risk_source="assignment",
                severity="high",
                target_underlier="QQQ",
                target_exposure_type="assignment",
                coverage_ratio=0.5,
                reason_code="assignment_overlay",
                metadata_json={
                    "option_strategy_type": "long_put",
                    "underlying_price": 500.0,
                },
            ),
        ),
    )
    hedge_payload = LookaheadRiskWorkflowHelper().materialize_generated_hedges(
        risk_decisions=(hedge_seed,),
        portfolio_risk_intent=hedge_intent,
    )[0].generated_hedge_action

    return {
        "status": "passed",
        "mode": "paper_option_lifecycle_fixture",
        "summary": {
            "open_risk_status": open_risk.status,
            "rejection_reason_code": rejected_risk.reason_code,
            "hedge_overlay_action": hedge_payload["action"] if hedge_payload is not None else None,
            "hedge_overlay_basis": hedge_payload["protected_exposure_basis"] if hedge_payload is not None else None,
        },
    }


def _run_intraday_refresh_fixture() -> dict[str, Any]:
    decision_time = _fixed_now()
    baseline = _manual_snapshot("NVDA", decision_time)
    intraday = build_intraday_signal_snapshot(
        intraday_signal_scan_id=str(uuid.uuid4()),
        ticker="NVDA",
        decision_time=decision_time + timedelta(hours=1),
        baseline_snapshot=baseline,
        previous_intraday_snapshot=None,
        refreshed_signals_json={
            "technical": {"last_price": 123.0, "relative_volume": 1.7},
            "events_news": {"high_signal_news_count_24h": 1},
        },
        source_freshness_json={
            "technical": "fresh",
            "fundamental": "carried_forward_from_baseline",
            "events_news": "fresh",
        },
    )
    alert_item = AlertSourceItem(
        alert_item_id=str(uuid.uuid4()),
        ticker="NVDA",
        source_ticker="NVDA",
        source_family="events_news",
        alert_type="analyst_upgrade",
        direction="positive",
        sentiment="positive",
        importance="high",
        importance_score=0.9,
        headline="NVDA raised after analyst upgrade",
        summary="Fresh high-signal positive catalyst.",
        provider="fixture",
        dedupe_key="NVDA|analyst_upgrade|2026-06-02T14:00:00+00:00",
        published_at=decision_time + timedelta(minutes=30),
        available_for_decision_at=decision_time + timedelta(minutes=30),
        metadata_json={"strategy_relevance": ["relative_strength_rotation_v1"]},
    )
    alerts = NewsAlertService().build_alerts(
        source_items=(alert_item,),
        existing_dedupe_keys=frozenset(),
        affected_positions_by_ticker={},
        affected_candidates_by_ticker={"NVDA": ("NVDA",)},
        affected_themes_by_ticker={"NVDA": ("AI",)},
    )
    return {
        "status": "passed",
        "mode": "intraday_refresh_fixture",
        "summary": {
            "ticker": intraday.ticker,
            "delta_vs_baseline_last_price": intraday.delta_vs_baseline_json["technical"]["last_price"],
            "carried_forward_families": sorted(intraday.carried_forward_signals_json),
            "alert_count": len(alerts),
        },
    }


def _option_risk_input(
    *,
    decision: Any,
    legs: tuple[Any, ...],
    sector: str | None,
    event_type: str | None,
) -> OptionRiskInput:
    return OptionRiskInput(
        ticker=decision.ticker,
        trade_identity=decision.trade_identity,
        option_strategy_type=decision.option_strategy_type,
        underlying_price=decision.underlying_price,
        sector=sector,
        event_type=event_type,
        event_through_expiry=decision.event_through_expiry,
        margin_requirement=decision.margin_requirement,
        buying_power_effect=decision.buying_power_effect,
        max_loss=decision.max_loss,
        max_profit=decision.max_profit,
        net_debit_or_credit=decision.net_debit_or_credit,
        legs=[
            OptionLegRiskInput(
                option_type=leg.option_type,
                side=leg.side,
                quantity=leg.quantity,
                strike=leg.strike,
                expiry=leg.expiry,
                delta=leg.delta,
                gamma=leg.gamma,
                theta=leg.theta,
                vega=leg.vega,
                premium=leg.chosen_price,
            )
            for leg in legs
        ],
    )


__all__ = [
    "_run_historical_replay_fixture",
    "_run_intraday_refresh_fixture",
    "_run_manual_review_fixture",
    "_run_paper_option_lifecycle_fixture",
    "_run_paper_option_fixture",
    "_run_paper_trade_dry_run",
    "_run_provider_guardrail_fixture",
    "_run_universe_signal_db_write",
    "run_intraday_signal_refresh_once",
    "run_manual_ticker_review_once",
    "run_trading_preopen_once",
]
