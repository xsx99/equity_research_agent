"""Dependency contracts and builders for the live preopen runtime."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from src.core import config as app_config
from src.trading.runtime.lookahead_risk import LookaheadRiskWorkflowHelper
from src.trading.runtime.preopen_risk import _LiveRiskWorkflow
from src.trading.runtime.support import (
    build_default_news_provider,
    seed_initial_strategy_definitions,
)


class ActiveUniverseFilterLoader(Protocol):
    def load_active(self) -> object:
        """Load the active universe filter configuration."""


class ActiveManualRequestLoader(Protocol):
    def load_active(self) -> tuple[object, ...]:
        """Load active manual ticker requests."""


class LiveUniverseScanPipeline(Protocol):
    def run(self, *, config: object, decision_time: datetime, manual_requests: tuple[object, ...]) -> object:
        """Build the live universe snapshot."""


class LiveSignalPipeline(Protocol):
    def build_pre_open_snapshots(self, *, universe_result: object, decision_time: datetime) -> tuple[object, ...]:
        """Build pre-open signal snapshots."""


class LiveStrategyPipeline(Protocol):
    def run(self, *, snapshots: tuple[object, ...], decision_time: datetime) -> object:
        """Run morning strategy scoring/classification."""


class LivePortfolioSyncWorkflow(Protocol):
    def run(self, *, as_of: datetime) -> object:
        """Build live portfolio context from broker-backed state."""


class LiveRiskWorkflow(Protocol):
    def run(
        self,
        *,
        candidates: tuple[object, ...],
        classifications: tuple[object, ...],
        portfolio_context: object,
        decision_time: datetime,
    ) -> object:
        """Produce risk decisions for selected candidates."""


class LiveTradingDecisionPipeline(Protocol):
    def run(
        self,
        *,
        candidates: tuple[object, ...],
        classifications: tuple[object, ...],
        risk_decisions: tuple[object, ...],
        decision_time: datetime,
    ) -> object:
        """Generate persisted trading decisions."""


class LivePaperExecutionWorkflow(Protocol):
    def run(
        self,
        *,
        decisions: tuple[object, ...],
        risk_decisions: tuple[object, ...],
        as_of: datetime,
    ) -> object:
        """Submit approved paper orders."""


@dataclass(frozen=True)
class LivePreopenDependencies:
    universe_filter_loader: ActiveUniverseFilterLoader
    manual_request_loader: ActiveManualRequestLoader
    universe_scan_pipeline: LiveUniverseScanPipeline
    signal_pipeline: LiveSignalPipeline
    strategy_pipeline: LiveStrategyPipeline
    portfolio_sync_workflow: LivePortfolioSyncWorkflow
    risk_workflow: LiveRiskWorkflow
    trading_decision_pipeline: LiveTradingDecisionPipeline
    paper_execution_workflow: LivePaperExecutionWorkflow | None = None
    trading_repository: Any | None = None


def build_live_preopen_dependencies(session: Any | None = None) -> LivePreopenDependencies:
    """Build the default production dependency graph for one live preopen run."""
    if session is None:
        raise RuntimeError("db_session_required_for_live_preopen_dependencies")

    from src.agents.prompt_registry import PromptRegistry
    from src.agents.trading import _default_agent_runner
    from src.providers.global_context import get_global_context
    from src.providers.market_data import AlpacaMarketDataProvider
    from src.trading.brokers.paper_option import (
        DEFAULT_ALPACA_PAPER_TRADING_BASE_URL,
        PaperOptionBroker,
    )
    from src.trading.brokers.paper_stock import PaperStockBroker
    from src.trading.data_sources.live_universe import LiveUniverseProvider
    from src.trading.manual_review.sqlalchemy import SQLAlchemyManualTickerRequestService
    from src.trading.repositories.source_sqlalchemy import SQLAlchemySignalSourceRepository
    from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
    from src.trading.risk.config import RiskConfigResolver
    from src.trading.risk.manager import RiskManager
    from src.trading.risk.options import OptionRiskManager
    from src.trading.risk.planner import PortfolioHedgePlanner
    from src.trading.risk.sizing import PositionSizer
    from src.trading.signals.source_ingestion import SourceIngestionService
    from src.trading.workflows.paper_execution import PaperExecutionWorkflow
    from src.trading.workflows.portfolio_sync import BrokerPortfolioSyncWorkflow
    from src.trading.workflows.signal_snapshot import SignalPipeline
    from src.trading.workflows.strategy_scoring import StrategyPipeline
    from src.trading.workflows.trading_decision import TradingDecisionPipeline

    trading_repository = SqlAlchemyTradingRepository(session)
    seed_initial_strategy_definitions(trading_repository)
    source_repository = SQLAlchemySignalSourceRepository(session)
    manual_request_service = SQLAlchemyManualTickerRequestService(session)
    market_provider = AlpacaMarketDataProvider()
    news_provider = build_default_news_provider()
    broker = PaperStockBroker()
    option_broker = PaperOptionBroker(
        trading_base_url=DEFAULT_ALPACA_PAPER_TRADING_BASE_URL,
    )
    signal_ingestion = SourceIngestionService(
        market_provider=market_provider,
        news_provider=news_provider,
        global_context_fetcher=lambda as_of: get_global_context(as_of=as_of, limit=5),
        source_repository=source_repository,
        artifact_repository=source_repository,
        provider_name="alpaca_live",
    )
    config_resolver = RiskConfigResolver()
    position_sizer = PositionSizer()
    risk_manager = RiskManager()
    option_risk_manager = OptionRiskManager()
    return LivePreopenDependencies(
        universe_filter_loader=_RepositoryUniverseFilterLoader(trading_repository),
        manual_request_loader=manual_request_service,
        universe_scan_pipeline=_ConfiguredLiveUniverseScanPipeline(
            provider=LiveUniverseProvider(market_provider=market_provider)
        ),
        signal_pipeline=SignalPipeline(
            source_repository=source_repository,
            manual_request_service=manual_request_service,
            source_ingestion_service=signal_ingestion,
            snapshot_repository=trading_repository,
        ),
        strategy_pipeline=StrategyPipeline(
            repository=trading_repository,
            manual_request_service=manual_request_service,
        ),
        portfolio_sync_workflow=BrokerPortfolioSyncWorkflow(
            repository=trading_repository,
            broker=broker,
        ),
        risk_workflow=_LiveRiskWorkflow(
            repository=trading_repository,
            source_repository=source_repository,
            config_resolver=config_resolver,
            position_sizer=position_sizer,
            risk_manager=risk_manager,
            option_risk_manager=option_risk_manager,
            lookahead_helper=LookaheadRiskWorkflowHelper(
                hedge_planner=PortfolioHedgePlanner()
            ),
        ),
        trading_decision_pipeline=TradingDecisionPipeline(
            repository=trading_repository,
            source_repository=source_repository,
            prompt_registry=PromptRegistry.get_default(),
            manual_request_service=manual_request_service,
            model_name=app_config.TRADING_MODEL_NAME,
            agent_runner=_default_agent_runner,
        ),
        paper_execution_workflow=PaperExecutionWorkflow(
            repository=trading_repository,
            broker=broker,
            option_broker=option_broker,
            manual_request_service=manual_request_service,
            config_resolver=config_resolver,
            position_sizer=position_sizer,
            risk_manager=risk_manager,
            option_risk_manager=option_risk_manager,
        ),
        trading_repository=trading_repository,
    )


class _RepositoryUniverseFilterLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def load_active(self) -> object:
        return self.repository.load_active_universe_filter_config()


class _ConfiguredLiveUniverseScanPipeline:
    def __init__(self, *, provider: Any) -> None:
        self.provider = provider

    def run(self, *, config: object, decision_time: datetime, manual_requests: tuple[object, ...]) -> object:
        from src.trading.data_sources.universe import apply_universe_filters
        from src.trading.workflows.universe_scan import UniverseScanPipeline

        target_symbols = tuple(
            sorted(
                {
                    *getattr(config, "manual_include", ()),
                    *(getattr(request, "ticker", None) for request in manual_requests),
                }
                - {None}
            )
        )
        if target_symbols and hasattr(self.provider, "fetch_assets_for_symbols"):
            return apply_universe_filters(
                self.provider.fetch_assets_for_symbols(target_symbols),
                config,
                snapshot_time=decision_time,
            )
        return UniverseScanPipeline(
            provider=self.provider,
            config=config,
            now=lambda: decision_time,
        ).run()
