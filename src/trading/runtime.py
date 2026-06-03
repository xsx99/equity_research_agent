"""Shared trading runtime entrypoints for scheduler jobs and standalone smoke scripts."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from src.agents.prompt_registry import PromptRegistry
from src.core.logging import get_logger
from src.db.connection import get_session
from src.db.models.trading import SignalSnapshot as SignalSnapshotModel
from src.db.models.trading import UniverseFilterConfig as UniverseFilterConfigModel
from src.db.models.trading import UniverseSnapshot as UniverseSnapshotModel
from src.db.models.trading import UniverseSymbol as UniverseSymbolModel
from src.trading.brokers.paper_stock import PaperOrderRequest
from src.trading.data_sources.universe import UniverseAsset, UniverseFilterConfig
from src.trading.intraday.news_alerts import NewsAlertService
from src.trading.intraday.signals import build_intraday_signal_snapshot
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.options.strategy import (
    OptionLegDefinition,
    OptionStrategyDecisionInput,
    OptionsStrategyLayer,
)
from src.trading.reflection_pipeline import ReflectionPipeline, ReflectionPipelineRequest
from src.trading.replay.historical import HistoricalReplayRunner
from src.trading.replay.outcomes import OutcomeEvaluator, PricePoint
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.risk import PortfolioContext
from src.trading.risk.config import RiskConfigResolver
from src.trading.risk.context import RiskFactorExposureRecord
from src.trading.risk.options import OptionLegRiskInput, OptionRiskInput, OptionRiskManager
from src.trading.signals.source_ingestion import SourceIngestionService
from src.trading.signals.sources import EventNewsItemRecord, InMemorySignalSourceRepository
from src.trading.strategies.matching import StrategyDefinitionRecord
from src.trading.strategy_evolution import StrategyEvolutionPipeline, StrategyEvolutionRequest
from src.trading.runtime_live import run_live_preopen_once
from src.trading.workflows.signal_snapshot import SignalPipeline
from src.trading.workflows.strategy_scoring import StrategyPipeline
from src.trading.workflows.universe_scan import UniverseScanPipeline

logger = get_logger(__name__)

AVAILABLE_SMOKE_MODES = (
    "provider_guardrail_fixture",
    "universe_signal_db_write",
    "historical_replay_fixture",
    "paper_trade_dry_run",
    "manual_review_fixture",
    "paper_option_fixture",
    "intraday_refresh_fixture",
    "reflection_fixture",
    "strategy_evolution_fixture",
)

TRADING_JOB_PHASES = (
    "preopen",
    "manual_review",
    "intraday_refresh",
    "reflection",
    "strategy_evolution",
)


def run_job_phase(phase: str) -> dict[str, Any]:
    """Run one scheduler-facing trading phase."""
    handlers = {
        "preopen": run_live_preopen_once,
        "manual_review": run_manual_ticker_review_once,
        "intraday_refresh": run_intraday_signal_refresh_once,
        "reflection": run_trading_reflection_once,
        "strategy_evolution": run_strategy_evolution_once,
    }
    try:
        return handlers[phase]()
    except KeyError as exc:
        raise ValueError(f"unsupported_trading_job_phase:{phase}") from exc


def run_smoke_mode(mode: str) -> dict[str, Any]:
    """Run one standalone fixture-first smoke mode."""
    handlers = {
        "provider_guardrail_fixture": _run_provider_guardrail_fixture,
        "universe_signal_db_write": _run_universe_signal_db_write,
        "historical_replay_fixture": _run_historical_replay_fixture,
        "paper_trade_dry_run": _run_paper_trade_dry_run,
        "manual_review_fixture": _run_manual_review_fixture,
        "paper_option_fixture": _run_paper_option_fixture,
        "intraday_refresh_fixture": _run_intraday_refresh_fixture,
        "reflection_fixture": _run_reflection_fixture,
        "strategy_evolution_fixture": _run_strategy_evolution_fixture,
    }
    try:
        report = handlers[mode]()
    except KeyError as exc:
        raise ValueError(f"unsupported_trading_smoke_mode:{mode}") from exc
    logger.info("trading_smoke_completed", mode=mode, status=report["status"])
    return report


def run_trading_preopen_once() -> dict[str, Any]:
    """Run the fixture-backed pre-open universe/signal/strategy path."""
    decision_time = _fixed_now()
    repository = InMemoryTradingRepository()
    _seed_strategy_definitions(repository)
    source_repository = InMemorySignalSourceRepository()
    manual_request_service = ManualTickerRequestService(now=lambda: decision_time)
    universe_result = UniverseScanPipeline(
        provider=_FixtureUniverseProvider(),
        config=UniverseFilterConfig(excluded_sectors=("Financials",)),
        now=lambda: decision_time,
    ).run()
    repository.save_universe_snapshot(universe_result)
    ingestion_service = SourceIngestionService(
        market_provider=_FixtureMarketProvider(),
        news_provider=_FixtureNewsProvider(),
        source_repository=source_repository,
        artifact_repository=repository,
        provider_name="fixture",
        now=lambda: decision_time,
        sleeper=lambda seconds: None,
    )
    snapshots = SignalPipeline(
        source_repository=source_repository,
        manual_request_service=manual_request_service,
        source_ingestion_service=ingestion_service,
    ).build_pre_open_snapshots(
        universe_result=universe_result,
        decision_time=decision_time,
    )
    for snapshot in snapshots:
        repository.save_signal_snapshot(snapshot)
    strategy_result = StrategyPipeline(
        repository=repository,
        manual_request_service=manual_request_service,
    ).run(
        snapshots=snapshots,
        decision_time=decision_time,
    )
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


def run_trading_reflection_once() -> dict[str, Any]:
    """Run the post-close reflection path with a fixed fixture payload."""
    return _run_reflection_fixture()


def run_strategy_evolution_once() -> dict[str, Any]:
    """Run the strategy-evolution phase with fixed reflection fixtures."""
    return _run_strategy_evolution_fixture()


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
                min_price=Decimal(str(universe_result.filter_config.min_price)),
                min_avg_dollar_volume=Decimal(str(universe_result.filter_config.min_avg_dollar_volume)),
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
    repository.save_strategy_definition(_simple_strategy_definition())
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
            "selected_count": len(replay.selected),
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
        portfolio_context=_empty_portfolio_context(decision_time),
        config=RiskConfigResolver().resolve(
            risk_appetite="balanced",
            portfolio_context=_empty_portfolio_context(decision_time),
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
    event_item = EventNewsItemRecord(
        event_news_item_id=str(uuid.uuid4()),
        ticker="NVDA",
        source_ticker="NVDA",
        event_type="analyst_upgrade",
        direction="positive",
        sentiment="positive",
        importance="high",
        headline="NVDA raised after analyst upgrade",
        summary="Fresh high-signal positive catalyst.",
        provider="fixture",
        source_refs_json=[],
        dedupe_key="NVDA|analyst_upgrade|2026-06-02T14:00:00+00:00",
        event_time=decision_time + timedelta(minutes=30),
        published_at=decision_time + timedelta(minutes=30),
        ingested_at=decision_time + timedelta(minutes=30),
        available_for_decision_at=decision_time + timedelta(minutes=30),
        raw_payload_ref=None,
        metadata_json={"strategy_relevance": ["relative_strength_rotation_v1"]},
    )
    alerts = NewsAlertService().build_alerts(
        event_items=(event_item,),
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


def _run_reflection_fixture() -> dict[str, Any]:
    decision_time = _fixed_now() + timedelta(hours=8)
    repository = InMemoryTradingRepository()
    result = ReflectionPipeline(
        repository=repository,
        prompt_registry=PromptRegistry.get_default(),
        model_name="gpt-5-mini",
        agent_runner=_reflection_agent_runner,
    ).run(
        request=ReflectionPipelineRequest(
            trade_date=decision_time.date(),
            decision_time=decision_time,
            available_for_decision_at=decision_time,
            portfolio_outcome={"realized_pnl": 125.0, "unrealized_pnl": -10.0},
            morning_macro_snapshot={"regime": "neutral"},
            benchmark_peer_returns={"QQQ": 0.01},
        )
    )
    return {
        "status": "passed",
        "mode": "reflection_fixture",
        "summary": {
            "reflection_count": len(result.daily_reflections),
            "learning_factor_count": len(result.learning_factors),
            "reflection_status": result.daily_reflections[0].status,
        },
    }


def _run_strategy_evolution_fixture() -> dict[str, Any]:
    decision_time = _fixed_now() + timedelta(hours=8)
    repository = InMemoryTradingRepository()
    repository.save_strategy_definition(_simple_strategy_definition())
    reflection_result = ReflectionPipeline(
        repository=repository,
        prompt_registry=PromptRegistry.get_default(),
        model_name="gpt-5-mini",
        agent_runner=_reflection_agent_runner,
    ).run(
        request=ReflectionPipelineRequest(
            trade_date=decision_time.date(),
            decision_time=decision_time,
            available_for_decision_at=decision_time,
            portfolio_outcome={"realized_pnl": 125.0, "unrealized_pnl": -10.0},
            morning_macro_snapshot={"regime": "neutral"},
            benchmark_peer_returns={"QQQ": 0.01},
        )
    )
    evolution = StrategyEvolutionPipeline(
        repository=repository,
        prompt_registry=PromptRegistry.get_default(),
        model_name="gpt-5-mini",
        agent_runner=_strategy_evolution_agent_runner,
    ).run(
        request=StrategyEvolutionRequest(
            trade_date=decision_time.date(),
            decision_time=decision_time,
            available_for_decision_at=decision_time,
            daily_reflections=reflection_result.daily_reflections,
            learning_factors=reflection_result.learning_factors,
            rejected_candidates=(
                {
                    "ticker": "PLTR",
                    "strategy_id": "relative_strength_rotation_v1",
                    "rejection_reason": "late_entry",
                    "core_signal_evidence": {"technical.relative_volume": 1.7},
                },
            ),
            candidate_outcome_evaluations=(),
        )
    )
    return {
        "status": "passed",
        "mode": "strategy_evolution_fixture",
        "summary": {
            "proposal_count": len(evolution.strategy_proposals),
            "definition_count": len(evolution.strategy_definitions),
            "proposal_statuses": [proposal.proposal_status for proposal in evolution.strategy_proposals],
        },
    }


def _build_universe_and_snapshots(
    decision_time: datetime,
    *,
    with_manual_request: bool = False,
) -> tuple[Any, tuple[Any, ...], InMemoryTradingRepository]:
    repository = InMemoryTradingRepository()
    source_repository = InMemorySignalSourceRepository()
    manual_request_service = ManualTickerRequestService(now=lambda: decision_time)
    if with_manual_request:
        manual_request_service.create("NVDA", "manual review fixture", "review_only")
    universe_result = UniverseScanPipeline(
        provider=_FixtureUniverseProvider(),
        config=UniverseFilterConfig(manual_exclude=("MSFT",)),
        now=lambda: decision_time,
    ).run()
    repository.save_universe_snapshot(universe_result)
    ingestion_service = SourceIngestionService(
        market_provider=_FixtureMarketProvider(),
        news_provider=_FixtureNewsProvider(),
        source_repository=source_repository,
        artifact_repository=repository,
        provider_name="fixture",
        now=lambda: decision_time,
        sleeper=lambda seconds: None,
    )
    snapshots = SignalPipeline(
        source_repository=source_repository,
        manual_request_service=manual_request_service,
        source_ingestion_service=ingestion_service,
    ).build_pre_open_snapshots(
        universe_result=universe_result,
        decision_time=decision_time,
    )
    for snapshot in snapshots:
        repository.save_signal_snapshot(snapshot)
    return universe_result, snapshots, repository


def _seed_strategy_definitions(repository: InMemoryTradingRepository) -> None:
    repository.save_strategy_definition(_simple_strategy_definition())


def _simple_strategy_definition() -> StrategyDefinitionRecord:
    return StrategyDefinitionRecord(
        strategy_definition_id="relative-strength-definition",
        strategy_id="relative_strength_rotation_v1",
        version="v1",
        display_name="Relative Strength Rotation",
        strategy_layer="tactical_pattern",
        typical_horizon="2w-3m",
        config_json={"required_signals": []},
        lifecycle_status="active",
        is_active=True,
        source="seed",
    )


def _manual_snapshot(ticker: str, decision_time: datetime) -> Any:
    source_repository = InMemorySignalSourceRepository()
    source_repository.add(
        *_fixture_source_ingestion_records(ticker=ticker, as_of=decision_time)
    )
    return SignalPipeline(
        source_repository=source_repository,
        manual_request_service=ManualTickerRequestService(now=lambda: decision_time),
    ).build_pre_open_snapshots(
        universe_result=UniverseScanPipeline(
            provider=_SingleTickerUniverseProvider(ticker),
            config=UniverseFilterConfig(),
            now=lambda: decision_time,
        ).run(),
        decision_time=decision_time,
    )[0]


def _fixture_source_ingestion_records(*, ticker: str, as_of: datetime) -> tuple[Any, ...]:
    repository = InMemoryTradingRepository()
    source_repository = InMemorySignalSourceRepository()
    result = SourceIngestionService(
        market_provider=_FixtureMarketProvider(),
        news_provider=_FixtureNewsProvider(),
        source_repository=source_repository,
        artifact_repository=repository,
        provider_name="fixture",
        now=lambda: as_of,
        sleeper=lambda seconds: None,
    ).refresh_tickers((ticker,), as_of=as_of, run_type="fixture")
    return result.source_records


def _empty_portfolio_context(as_of: datetime) -> PortfolioContext:
    return PortfolioContext(
        as_of=as_of,
        account_equity=100_000.0,
        cash_balance=100_000.0,
        buying_power=200_000.0,
        excess_liquidity=100_000.0,
        positions=(),
        open_strategy_exposure={},
        current_factor_exposure=(
            RiskFactorExposureRecord(
                factor_type="sector",
                factor_value="technology",
                gross_exposure=0.0,
                net_exposure=0.0,
                long_exposure=0.0,
                short_exposure=0.0,
                position_count=0,
            ),
        ),
        stock_margin_requirement=0.0,
        option_margin_requirement=0.0,
        total_margin_requirement=0.0,
    )


def _reflection_agent_runner(prompt: str, model_name: str) -> dict[str, Any]:
    return {
        "content": {
            "trade_date": "2026-06-02",
            "portfolio_summary": {
                "realized_pnl": 125.0,
                "unrealized_pnl": -10.0,
                "benchmark_return": 0.01,
            },
            "what_worked": ["Waited for confirmation before adding."],
            "what_failed": ["Late entries after the main move."],
            "attribution": [],
            "learning_factors": [
                {
                    "factor_type": "candidate_filter",
                    "scope": "strategy",
                    "title": "Require confirmation for extended gaps",
                    "strategy_id": "relative_strength_rotation_v1",
                    "condition": "opening_gap_pct > 0.04 and relative_volume < 1.5",
                    "recommendation": "Require confirmation before entry.",
                    "confidence": 0.7,
                    "activation_policy": "auto_risk_tightening",
                    "effect_tags": ["require_confirmation", "lower_confidence"],
                    "evidence": ["Reduced false starts in fixture outcomes."],
                }
            ],
            "strategy_proposal_hints": [
                {"title": "Post-gap reclaim continuation"}
            ],
            "schema_version": "v1",
            "generated_at": "2026-06-02T22:00:00+00:00",
        }
    }


def _strategy_evolution_agent_runner(prompt: str, model_name: str) -> dict[str, Any]:
    return {
        "content": {
            "proposals": [
                {
                    "proposed_strategy_id": "post_gap_vwap_reclaim_v1",
                    "display_name": "Post-Gap VWAP Reclaim",
                    "source_reflection_ids": ["reflection-1"],
                    "core_thesis": "Stocks that reclaim VWAP after an early fade can continue higher.",
                    "typical_horizon": "intraday-3d",
                    "required_signals": [
                        "opening_gap_pct",
                        "vwap_reclaim",
                        "relative_volume",
                        "opening_range_reclaim",
                    ],
                    "optional_signals": ["fresh_catalyst_type"],
                    "scoring_rules": {"min_opening_gap_pct": 0.02},
                    "risk_tags": ["gap_risk", "intraday_momentum"],
                    "macro_blocked_regimes": ["stressed"],
                    "invalidators": ["re-loses VWAP"],
                    "evidence_summary": "Observed repeatedly in fixture reflection rows.",
                }
            ],
            "schema_version": "v1",
            "generated_at": "2026-06-02T22:00:00+00:00",
        }
    }


class _FixtureUniverseProvider:
    def fetch_universe_assets(self) -> list[UniverseAsset]:
        return [
            UniverseAsset("AAPL", "Apple", "common_stock", "NASDAQ", "Technology", "Hardware", 180.0, 90_000_000),
            UniverseAsset("MSFT", "Microsoft", "common_stock", "NASDAQ", "Technology", "Software", 320.0, 95_000_000),
            UniverseAsset("NVDA", "NVIDIA", "common_stock", "NASDAQ", "Technology", "Semiconductors", 120.0, 140_000_000),
        ]


class _SingleTickerUniverseProvider:
    def __init__(self, ticker: str) -> None:
        self._ticker = ticker.upper()

    def fetch_universe_assets(self) -> list[UniverseAsset]:
        return [
            UniverseAsset(
                self._ticker,
                self._ticker,
                "common_stock",
                "NASDAQ",
                "Technology",
                "Semiconductors",
                120.0,
                140_000_000,
            )
        ]


class _FixtureMarketProvider:
    def fetch_daily_bars(self, ticker: str, lookback_days: int) -> list[dict[str, Any]]:
        return [
            {"date": date(2026, 6, 1), "open": 100.0, "high": 104.0, "low": 99.0, "close": 101.0, "volume": 1_000_000},
            {"date": date(2026, 6, 2), "open": 101.0, "high": 106.0, "low": 100.0, "close": 104.0, "volume": 2_100_000},
        ]

    def fetch_context(self, ticker: str) -> dict[str, Any]:
        return {
            "market_cap": 3_000_000_000_000,
            "quality_score": 0.8,
            "revenue_growth_score": 0.7,
            "sector": "Technology",
            "earnings_in_days": 10,
        }


class _FixtureNewsProvider:
    def fetch_recent(self, ticker: str, limit: int) -> list[dict[str, Any]]:
        return [
            {
                "title": f"{ticker} upgraded after demand check",
                "summary": "Analyst raises rating.",
                "published_at": "2026-06-02T10:30:00+00:00",
                "source": "fixture",
                "signal_type": "analyst_rating",
            }
        ]


class _FakePaperStockBroker:
    def submit_order(self, request: PaperOrderRequest) -> Any:
        self.last_request = request
        return type(
            "Order",
            (),
            {
                "paper_order_id": "paper-order-1",
                "broker_order_id": "broker-order-1",
                "client_order_id": "client-order-1",
                "ticker": request.ticker,
                "status": "filled",
                "rejection_reason": None,
            },
        )()

    def find_execution_by_order_id(self, paper_order_id: str) -> Any:
        return type(
            "Execution",
            (),
            {
                "paper_execution_id": "exec-1",
                "paper_order_id": paper_order_id,
                "broker_order_id": "broker-order-1",
                "ticker": "AAPL",
                "quantity": 0.01,
                "fill_price": 315.0,
                "trade_date": _fixed_now().date(),
                "executed_at": _fixed_now(),
                "net_cash_effect": -3.15,
            },
        )()

    def sync_account(self) -> dict[str, Any]:
        return {
            "cash": "999996.85",
            "equity": "1000000.00",
            "portfolio_value": "1000000.00",
            "buying_power": "1999996.85",
            "long_market_value": "3.15",
            "initial_margin": "1.58",
            "maintenance_margin": "0.95",
            "last_equity": "1000000.00",
        }

    def sync_positions(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "avg_entry_price": "315.00",
                "current_price": "315.00",
                "market_value": "3.15",
                "side": "long",
            }
        ]


def _fixed_now() -> datetime:
    return datetime(2026, 6, 2, 13, 30, tzinfo=timezone.utc)


def _decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _uuid_or_none(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    return uuid.UUID(str(value))
