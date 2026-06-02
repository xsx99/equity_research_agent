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


def test_trading_repository_path_names_in_memory_store_explicitly():
    from src.trading.repositories.in_memory import InMemoryTradingRepository

    assert InMemoryTradingRepository.__name__ == "InMemoryTradingRepository"


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
    from src.trading.strategies.catalog import get_initial_strategy_definitions
    from src.trading.strategies.classifier import TradeClassifier
    from src.trading.strategies.matching import StrategyMatcher
    from src.trading.strategies.selector import PrimaryStrategySelector
    from src.trading.strategies.taxonomy import get_trade_identity_policy

    assert ConfidenceCalibrator.__name__ == "ConfidenceCalibrator"
    assert callable(get_initial_strategy_definitions)
    assert TradeClassifier.__name__ == "TradeClassifier"
    assert StrategyMatcher.__name__ == "StrategyMatcher"
    assert PrimaryStrategySelector.__name__ == "PrimaryStrategySelector"
    assert callable(get_trade_identity_policy)


def test_trading_contract_paths_export_remaining_components():
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
    assert PaperStockBroker.__name__ == "PaperStockBroker"
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
        "src/trading/manual_requests.py",
        "src/trading/outcome_evaluator.py",
        "src/trading/paper_stock_broker.py",
        "src/trading/pipeline.py",
        "src/trading/point_in_time.py",
        "src/trading/portfolio_intents.py",
        "src/trading/primary_strategy_selector.py",
        "src/trading/provider_resilience.py",
        "src/trading/repository.py",
        "src/trading/relationships.py",
        "src/trading/signal_sources.py",
        "src/trading/source_ingestion.py",
        "src/trading/strategy_catalog.py",
        "src/trading/strategy_matching.py",
        "src/trading/technical_signals.py",
        "src/trading/trade_classifier.py",
        "src/trading/trade_taxonomy.py",
        "src/trading/universe.py",
    ]

    assert [path for path in removed_paths if (_REPO_ROOT / path).exists()] == []
