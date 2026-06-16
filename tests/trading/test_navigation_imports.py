"""Navigation tests for trading import paths."""
from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_trading_workflow_paths_export_pipeline_entrypoints():
    from src.trading.workflows.paper_execution import PaperExecutionWorkflow
    from src.trading.workflows.signal_snapshot import SignalPipeline
    from src.trading.workflows.strategy_scoring import StrategyPipeline
    from src.trading.workflows.trading_decision import TradingDecisionPipeline
    from src.trading.workflows.universe_scan import UniverseScanPipeline

    assert PaperExecutionWorkflow.__name__ == "PaperExecutionWorkflow"
    assert UniverseScanPipeline.__name__ == "UniverseScanPipeline"
    assert SignalPipeline.__name__ == "SignalPipeline"
    assert StrategyPipeline.__name__ == "StrategyPipeline"
    assert TradingDecisionPipeline.__name__ == "TradingDecisionPipeline"


def test_trading_canonical_runtime_and_post_close_paths_export_entrypoints():
    from src.trading.post_close.reflection import ReflectionPipeline as CanonicalReflectionPipeline
    from src.trading.post_close.strategy_evolution import (
        StrategyEvolutionPipeline as CanonicalStrategyEvolutionPipeline,
    )
    from src.trading.post_close.strategy_policy import experimental_strategy_weight_cap
    from src.trading.runtime import TRADING_JOB_PHASES, run_job_phase
    from src.trading.runtime.dispatch import get_job_phase_handler
    from src.trading.runtime.preopen import LivePreopenRuntime

    assert CanonicalReflectionPipeline.__name__ == "ReflectionPipeline"
    assert CanonicalStrategyEvolutionPipeline.__name__ == "StrategyEvolutionPipeline"
    assert experimental_strategy_weight_cap(0.12) == 0.02
    assert callable(run_job_phase)
    assert "preopen" in TRADING_JOB_PHASES
    assert callable(get_job_phase_handler)
    assert LivePreopenRuntime.__name__ == "LivePreopenRuntime"


def test_trading_runtime_internal_split_paths_export_navigation_units():
    from src.trading.runtime.intraday_refresh_dependencies import (
        LiveIntradayRefreshDependencies,
        _RepositoryIntradayScopeLoader,
    )
    from src.trading.runtime.intraday_refresh_helpers import (
        _build_rebalance_request,
        _event_item_from_source_record,
    )
    from src.trading.runtime.intraday_refresh_runner import LiveIntradayRefreshRuntime
    from src.trading.runtime.preopen_dependencies import (
        LivePreopenDependencies,
        _ConfiguredLiveUniverseScanPipeline,
    )
    from src.trading.runtime.preopen_risk import _LiveRiskWorkflow
    from src.trading.runtime.preopen_runner import LivePreopenRuntime as CanonicalPreopenRuntime

    assert LivePreopenDependencies.__name__ == "LivePreopenDependencies"
    assert _ConfiguredLiveUniverseScanPipeline.__name__ == "_ConfiguredLiveUniverseScanPipeline"
    assert _LiveRiskWorkflow.__name__ == "_LiveRiskWorkflow"
    assert CanonicalPreopenRuntime.__name__ == "LivePreopenRuntime"
    assert LiveIntradayRefreshDependencies.__name__ == "LiveIntradayRefreshDependencies"
    assert _RepositoryIntradayScopeLoader.__name__ == "_RepositoryIntradayScopeLoader"
    assert callable(_build_rebalance_request)
    assert callable(_event_item_from_source_record)
    assert LiveIntradayRefreshRuntime.__name__ == "LiveIntradayRefreshRuntime"


def test_trading_runtime_smoke_internal_split_paths_export_navigation_units():
    from src.trading.runtime.smoke import AVAILABLE_SMOKE_MODES
    from src.trading.runtime.smoke_entrypoints import (
        run_intraday_signal_refresh_once,
        run_strategy_evolution_once,
        run_trading_preopen_once,
    )
    from src.trading.runtime.smoke_fixture_modes import (
        _run_manual_review_fixture,
        _run_provider_guardrail_fixture,
    )
    from src.trading.runtime.smoke_post_close_modes import (
        _run_reflection_fixture,
        _run_strategy_evolution_fixture,
    )
    from src.trading.runtime.smoke_support import (
        _FixtureUniverseProvider,
        _build_universe_and_snapshots,
        _reflection_agent_runner,
    )

    assert "manual_review_fixture" in AVAILABLE_SMOKE_MODES
    assert "manual_review_execution_fixture" in AVAILABLE_SMOKE_MODES
    assert callable(run_trading_preopen_once)
    assert callable(run_intraday_signal_refresh_once)
    assert callable(run_strategy_evolution_once)
    assert callable(_run_provider_guardrail_fixture)
    assert callable(_run_manual_review_fixture)
    assert callable(_run_reflection_fixture)
    assert callable(_run_strategy_evolution_fixture)
    assert callable(_build_universe_and_snapshots)
    assert callable(_reflection_agent_runner)
    assert _FixtureUniverseProvider.__name__ == "_FixtureUniverseProvider"


def test_trading_repository_path_names_in_memory_store_explicitly():
    from src.trading.repositories.in_memory import InMemoryTradingRepository
    from src.trading.intraday.rebalance import IntradayRebalancePipeline
    from src.trading.intraday.signals import IntradaySignalSnapshotRecord
    from src.trading.intraday.news_alerts import NewsAlertService

    assert InMemoryTradingRepository.__name__ == "InMemoryTradingRepository"
    assert IntradayRebalancePipeline.__name__ == "IntradayRebalancePipeline"
    assert IntradaySignalSnapshotRecord.__name__ == "IntradaySignalSnapshotRecord"
    assert NewsAlertService.__name__ == "NewsAlertService"


def test_trading_signal_paths_export_builders_and_source_contracts():
    from src.trading.signals.event_news import build_event_news_signals
    from src.trading.signals.fundamental import build_fundamental_signals
    from src.trading.signals.point_in_time import filter_point_in_time_records
    from src.trading.signals.snapshots import SignalSnapshotResult, build_signal_snapshot
    from src.trading.signals.source_ingestion import SourceIngestionService
    from src.trading.signals.sources import SourceRecord
    from src.trading.signals.technical import build_technical_signals

    assert callable(build_event_news_signals)
    assert callable(build_fundamental_signals)
    assert callable(filter_point_in_time_records)
    assert SignalSnapshotResult.__name__ == "SignalSnapshotResult"
    assert callable(build_signal_snapshot)
    assert SourceIngestionService.__name__ == "SourceIngestionService"
    assert SourceRecord.__name__ == "SourceRecord"
    assert callable(build_technical_signals)


def test_trading_strategy_paths_export_catalog_and_selection_components():
    from src.trading.strategies.calibration import ConfidenceCalibrator
    from src.trading.strategies import (
        get_initial_expression_definitions,
        get_initial_strategy_definitions,
        load_all_trading_definitions,
    )
    from src.trading.strategies.classifier import TradeClassifier
    from src.trading.strategies.matching import StrategyMatcher
    from src.trading.strategies.selector import PrimaryStrategySelector
    from src.trading.strategies.taxonomy import get_trade_identity_policy

    assert ConfidenceCalibrator.__name__ == "ConfidenceCalibrator"
    assert callable(get_initial_strategy_definitions)
    assert callable(get_initial_expression_definitions)
    assert callable(load_all_trading_definitions)
    assert TradeClassifier.__name__ == "TradeClassifier"
    assert StrategyMatcher.__name__ == "StrategyMatcher"
    assert PrimaryStrategySelector.__name__ == "PrimaryStrategySelector"
    assert callable(get_trade_identity_policy)


def test_trading_contract_paths_export_remaining_components():
    from src.trading.brokers.paper_option import PaperOptionBroker
    from src.trading.risk.options import OptionRiskManager
    from src.trading.options.strategy import OptionsStrategyLayer
    from src.trading.brokers.paper_stock import PaperStockBroker
    from src.trading.data_sources.provider_resilience import ProviderResiliencePolicy
    from src.trading.data_sources.universe import UniverseAsset, normalize_ticker
    from src.trading.manual_review.requests import ManualTickerRequestService
    from src.trading.portfolio.intents import PortfolioIntentConfig
    from src.trading.portfolio.state import PortfolioLedger
    from src.trading.risk import PortfolioContext, PositionSizer, RiskConfigResolver, RiskManager
    from src.trading.relationships.graph import TickerRelationship
    from src.trading.replay.historical import HistoricalReplayRunner
    from src.trading.replay.outcomes import OutcomeEvaluator, PricePoint

    assert ProviderResiliencePolicy.__name__ == "ProviderResiliencePolicy"
    assert UniverseAsset.__name__ == "UniverseAsset"
    assert normalize_ticker(" aapl ") == "AAPL"
    assert ManualTickerRequestService.__name__ == "ManualTickerRequestService"
    assert PaperOptionBroker.__name__ == "PaperOptionBroker"
    assert PaperStockBroker.__name__ == "PaperStockBroker"
    assert OptionsStrategyLayer.__name__ == "OptionsStrategyLayer"
    assert OptionRiskManager.__name__ == "OptionRiskManager"
    assert PortfolioIntentConfig.__name__ == "PortfolioIntentConfig"
    assert PortfolioLedger.__name__ == "PortfolioLedger"
    assert PortfolioContext.__name__ == "PortfolioContext"
    assert PositionSizer.__name__ == "PositionSizer"
    assert RiskConfigResolver.__name__ == "RiskConfigResolver"
    assert RiskManager.__name__ == "RiskManager"
    assert TickerRelationship.__name__ == "TickerRelationship"
    assert HistoricalReplayRunner.__name__ == "HistoricalReplayRunner"
    assert OutcomeEvaluator.__name__ == "OutcomeEvaluator"
    assert PricePoint.__name__ == "PricePoint"


def test_trading_root_no_longer_contains_compatibility_modules():
    removed_paths = [
        "src/trading/confidence_calibration.py",
        "src/trading/event_news_signals.py",
        "src/trading/fundamental_signals.py",
        "src/trading/historical_replay.py",
        "src/trading/intraday_rebalance.py",
        "src/trading/intraday_signals.py",
        "src/trading/manual_requests.py",
        "src/trading/news_alerts.py",
        "src/trading/options/hedge.py",
        "src/trading/options/risk.py",
        "src/trading/outcome_evaluator.py",
        "src/trading/paper_stock_broker.py",
        "src/trading/pipeline.py",
        "src/trading/point_in_time.py",
        "src/trading/portfolio_intents.py",
        "src/trading/primary_strategy_selector.py",
        "src/trading/provider_resilience.py",
        "src/trading/repository.py",
        "src/trading/reflection",
        "src/trading/reflection_pipeline.py",
        "src/trading/relationships.py",
        "src/trading/runtime_dispatch.py",
        "src/trading/runtime_intraday_live.py",
        "src/trading/runtime_live.py",
        "src/trading/runtime_manual_review_live.py",
        "src/trading/runtime_reflection_live.py",
        "src/trading/runtime_smoke.py",
        "src/trading/runtime_strategy_evolution_live.py",
        "src/trading/runtime_support.py",
        "src/trading/signal_sources.py",
        "src/trading/source_ingestion.py",
        "src/trading/strategy_catalog.py",
        "src/trading/strategy_evolution.py",
        "src/trading/strategy_matching.py",
        "src/trading/technical_signals.py",
        "src/trading/trade_classifier.py",
        "src/trading/trade_taxonomy.py",
        "src/trading/universe.py",
    ]

    assert [path for path in removed_paths if (_REPO_ROOT / path).exists()] == []


def test_trading_runtime_package_includes_navigation_readme():
    assert (_REPO_ROOT / "src/trading/runtime/README.md").is_file()
