"""Dependency contracts and builders for the live intraday runtime."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from src.core import config as app_config
from src.trading.events import CalendarEventPipeline, PortfolioEventRiskAssessmentPipeline
from src.trading.phases.intraday.news_alerts import NewsAlertService
from src.trading.phases.intraday.rebalance import IntradayRebalancePipeline
from src.trading.macro import MacroSnapshotPipeline
from src.trading.trade_day import trade_date_for


@dataclass(frozen=True)
class LiveIntradayRefreshDependencies:
    scope_loader: Any
    baseline_loader: Any
    previous_snapshot_loader: Any
    request_context_loader: Any
    source_repository: Any
    portfolio_sync_workflow: Any
    news_alert_service: Any
    rebalance_pipeline: Any
    trading_repository: Any
    existing_news_dedupe_key_loader: Callable[[tuple[str, ...], datetime], frozenset[str]]
    candidate_context_loader: Callable[[tuple[str, ...], datetime], dict[str, tuple[str, ...]]]
    position_context_loader: Callable[[tuple[str, ...], tuple[object, ...]], dict[str, tuple[str, ...]]]
    theme_context_loader: Callable[[tuple[str, ...], datetime], dict[str, tuple[str, ...]]]
    macro_state_loader: Callable[[datetime], str | None]
    source_ingestion_service: Any | None = None
    lookahead_helper: Any | None = None
    macro_snapshot_loader: Callable[[datetime], object | None] | None = None
    macro_snapshot_pipeline: Any | None = None
    calendar_event_pipeline: Any | None = None
    event_risk_pipeline: Any | None = None


def build_live_intraday_refresh_dependencies(session: Any | None = None) -> LiveIntradayRefreshDependencies:
    """Build the default production dependency graph for one live intraday refresh run."""
    if session is None:
        raise RuntimeError("db_session_required_for_live_intraday_refresh_dependencies")

    from src.agents.prompt_registry import PromptRegistry
    from src.agents.trading import _default_agent_runner
    from src.providers.global_context import get_global_context
    from src.providers.market_data import AlpacaMarketDataProvider
    from src.providers.market_data.nasdaq_earnings import NasdaqEarningsCalendar
    from src.trading.brokers.paper_option import (
        DEFAULT_ALPACA_PAPER_TRADING_BASE_URL,
        PaperOptionBroker,
    )
    from src.trading.brokers.paper_stock import PaperStockBroker
    from src.trading.repositories.source_sqlalchemy import SQLAlchemySignalSourceRepository
    from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
    from src.trading.risk import PortfolioHedgePlanner
    from src.trading.risk.lookahead_risk import LookaheadRiskWorkflowHelper
    from src.trading.phases._shell.support import build_default_news_provider
    from src.trading.signals.source_ingestion import SourceIngestionService
    from src.trading.workflows.portfolio_sync import BrokerPortfolioSyncWorkflow

    trading_repository = SqlAlchemyTradingRepository(session)
    source_repository = SQLAlchemySignalSourceRepository(session)
    market_provider = AlpacaMarketDataProvider()
    earnings_calendar = NasdaqEarningsCalendar()
    news_provider = build_default_news_provider()
    broker = PaperStockBroker()
    option_broker = PaperOptionBroker(
        trading_base_url=DEFAULT_ALPACA_PAPER_TRADING_BASE_URL,
    )
    return LiveIntradayRefreshDependencies(
        scope_loader=_RepositoryIntradayScopeLoader(trading_repository),
        baseline_loader=_RepositoryBaselineLoader(trading_repository),
        previous_snapshot_loader=_RepositoryPreviousIntradaySnapshotLoader(trading_repository),
        request_context_loader=_RepositoryIntradayRequestContextLoader(trading_repository),
        source_repository=source_repository,
        source_ingestion_service=SourceIngestionService(
            market_provider=market_provider,
            news_provider=news_provider,
            earnings_calendar=earnings_calendar,
            global_context_fetcher=lambda as_of: get_global_context(as_of=as_of, limit=5),
            source_repository=source_repository,
            artifact_repository=source_repository,
            provider_name="alpaca_live",
        ),
        portfolio_sync_workflow=BrokerPortfolioSyncWorkflow(repository=trading_repository, broker=broker),
        news_alert_service=NewsAlertService(),
        rebalance_pipeline=IntradayRebalancePipeline(
            repository=trading_repository,
            prompt_registry=PromptRegistry.get_default(),
            model_name=app_config.TRADING_MODEL_NAME,
            agent_runner=_default_agent_runner,
            broker=broker,
            option_broker=option_broker,
        ),
        trading_repository=trading_repository,
        existing_news_dedupe_key_loader=_RepositoryExistingNewsDedupeKeyLoader(trading_repository),
        candidate_context_loader=_RepositoryIntradayCandidateContextLoader(trading_repository),
        position_context_loader=lambda tickers, positions: {
            ticker: (ticker,)
            for ticker in tickers
            if ticker in {getattr(position, "ticker", None) for position in positions}
        },
        theme_context_loader=lambda tickers, decision_time: {},
        macro_state_loader=lambda decision_time: None,
        lookahead_helper=LookaheadRiskWorkflowHelper(hedge_planner=PortfolioHedgePlanner()),
        macro_snapshot_loader=_RepositoryMacroSnapshotLoader(trading_repository),
        macro_snapshot_pipeline=MacroSnapshotPipeline(
            global_context_fetcher=lambda as_of: get_global_context(as_of=as_of, limit=5),
        ),
        calendar_event_pipeline=CalendarEventPipeline(),
        event_risk_pipeline=PortfolioEventRiskAssessmentPipeline(),
    )


def _scheduler_trade_date(decision_time: datetime) -> date:
    return trade_date_for(decision_time, app_config.SCHEDULER_TIMEZONE)


class _RepositoryIntradayScopeLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def load_scope(self, *, decision_time: datetime) -> tuple[str, ...]:
        return self.repository.load_intraday_scope(trade_date=_scheduler_trade_date(decision_time))


class _RepositoryBaselineLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def load_for_tickers(self, *, tickers: tuple[str, ...], decision_time: datetime) -> dict[str, Any]:
        return self.repository.load_latest_signal_snapshots_for_tickers(
            tickers=tickers,
            snapshot_type="pre_open",
            trade_date=_scheduler_trade_date(decision_time),
        )


class _RepositoryPreviousIntradaySnapshotLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def load_for_tickers(self, *, tickers: tuple[str, ...], decision_time: datetime) -> dict[str, Any]:
        return self.repository.load_latest_intraday_signal_snapshots_for_tickers(
            tickers=tickers,
            trade_date=_scheduler_trade_date(decision_time),
        )


class _RepositoryIntradayRequestContextLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def load_for_tickers(self, *, tickers: tuple[str, ...], decision_time: datetime) -> dict[str, Any]:
        return self.repository.load_intraday_request_contexts(
            tickers=tickers,
            trade_date=_scheduler_trade_date(decision_time),
        )


class _RepositoryExistingNewsDedupeKeyLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def __call__(self, tickers: tuple[str, ...], decision_time: datetime) -> frozenset[str]:
        return self.repository.load_existing_news_alert_dedupe_keys(
            tickers=tickers,
            trade_date=_scheduler_trade_date(decision_time),
        )


class _RepositoryIntradayCandidateContextLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def __call__(self, tickers: tuple[str, ...], decision_time: datetime) -> dict[str, tuple[str, ...]]:
        return self.repository.load_intraday_candidate_context(
            tickers=tickers,
            trade_date=_scheduler_trade_date(decision_time),
        )


class _RepositoryMacroSnapshotLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def __call__(self, decision_time: datetime) -> object | None:
        return self.repository.load_latest_macro_snapshot(
            trade_date=_scheduler_trade_date(decision_time),
            decision_time=decision_time,
        )
