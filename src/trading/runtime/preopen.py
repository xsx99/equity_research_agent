"""Live preopen runtime assembly and orchestration."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from src.core import config as app_config
from src.trading.runtime.support import (
    build_default_news_provider,
    build_execution_report,
    build_runtime_report,
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


class LivePreopenRuntime:
    """Orchestrate the live morning chain with explicit execution policy."""

    def __init__(
        self,
        *,
        dependencies: LivePreopenDependencies,
        now: Callable[[], datetime] | None = None,
        execute_paper_orders: bool = False,
    ) -> None:
        self.dependencies = dependencies
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.execute_paper_orders = execute_paper_orders

    def run(self) -> dict[str, Any]:
        decision_time = self.now()
        config = self.dependencies.universe_filter_loader.load_active()
        manual_requests = self.dependencies.manual_request_loader.load_active()
        universe_result = self.dependencies.universe_scan_pipeline.run(
            config=config,
            decision_time=decision_time,
            manual_requests=manual_requests,
        )
        snapshots = self.dependencies.signal_pipeline.build_pre_open_snapshots(
            universe_result=universe_result,
            decision_time=decision_time,
        )
        if self.dependencies.trading_repository is not None:
            self.dependencies.trading_repository.save_universe_snapshot(universe_result)
            for snapshot in snapshots:
                self.dependencies.trading_repository.save_signal_snapshot(snapshot)
        strategy_result = self.dependencies.strategy_pipeline.run(
            snapshots=snapshots,
            decision_time=decision_time,
        )
        portfolio_result = self.dependencies.portfolio_sync_workflow.run(as_of=decision_time)
        risk_result = self.dependencies.risk_workflow.run(
            candidates=tuple(getattr(strategy_result, "candidates", ())),
            classifications=tuple(getattr(strategy_result, "classifications", ())),
            portfolio_context=getattr(portfolio_result, "portfolio_context", portfolio_result),
            decision_time=decision_time,
        )
        decision_result = self.dependencies.trading_decision_pipeline.run(
            candidates=tuple(getattr(strategy_result, "candidates", ())),
            classifications=tuple(getattr(strategy_result, "classifications", ())),
            risk_decisions=tuple(getattr(risk_result, "risk_decisions", ())),
            decision_time=decision_time,
        )
        execution = self._run_execution(
            decisions=tuple(getattr(decision_result, "decisions", ())),
            risk_decisions=tuple(getattr(risk_result, "risk_decisions", ())),
            as_of=decision_time,
        )
        return build_runtime_report(
            phase="preopen",
            as_of=decision_time,
            summary={
                "manual_request_count": len(manual_requests),
                "signal_snapshot_count": len(snapshots),
                "candidate_count": len(tuple(getattr(strategy_result, "candidates", ()))),
                "classification_count": len(tuple(getattr(strategy_result, "classifications", ()))),
                "risk_decision_count": len(tuple(getattr(risk_result, "risk_decisions", ()))),
                "trading_decision_count": len(tuple(getattr(decision_result, "decisions", ()))),
            },
            execution=execution,
        )

    def _run_execution(
        self,
        *,
        decisions: tuple[object, ...],
        risk_decisions: tuple[object, ...],
        as_of: datetime,
    ) -> dict[str, Any]:
        if not self.execute_paper_orders:
            return build_execution_report(mode="dry_run", orders_submitted=0)
        workflow = self.dependencies.paper_execution_workflow
        if workflow is None:
            raise RuntimeError("paper_execution_workflow_not_configured")
        result = workflow.run(
            trading_decisions=decisions,
            risk_decisions=risk_decisions,
            trade_date=as_of,
        )
        submitted_orders = tuple(getattr(result, "paper_orders", ()))
        return build_execution_report(mode="execute", orders_submitted=len(submitted_orders))


def run_live_preopen_once(
    *,
    dependencies: LivePreopenDependencies | None = None,
    execute_paper_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Execute one live preopen run with injected dependencies."""
    return run_preopen_once(
        dependencies=dependencies,
        execute_paper_orders=execute_paper_orders,
        now=now,
    )


def run_preopen_once(
    *,
    dependencies: LivePreopenDependencies | None = None,
    execute_paper_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Execute one live preopen run with injected dependencies."""
    if dependencies is not None:
        runtime = LivePreopenRuntime(
            dependencies=dependencies,
            now=now,
            execute_paper_orders=execute_paper_orders,
        )
        return runtime.run()

    from src.db.connection import get_session

    with get_session() as session:
        runtime = LivePreopenRuntime(
            dependencies=build_live_preopen_dependencies(session),
            now=now,
            execute_paper_orders=execute_paper_orders,
        )
        return runtime.run()


def build_live_preopen_dependencies(session: Any | None = None) -> LivePreopenDependencies:
    """Build the default production dependency graph for one live preopen run."""
    if session is None:
        raise RuntimeError("db_session_required_for_live_preopen_dependencies")

    from src.agents.prompt_registry import PromptRegistry
    from src.agents.trading import _default_agent_runner
    from src.providers.market_data import AlpacaMarketDataProvider
    from src.trading.brokers.paper_stock import PaperStockBroker
    from src.trading.data_sources.live_universe import LiveUniverseProvider
    from src.trading.manual_review.sqlalchemy import SQLAlchemyManualTickerRequestService
    from src.trading.repositories.source_sqlalchemy import SQLAlchemySignalSourceRepository
    from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
    from src.trading.risk.config import RiskConfigResolver
    from src.trading.risk.manager import RiskManager
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
    signal_ingestion = SourceIngestionService(
        market_provider=market_provider,
        news_provider=news_provider,
        source_repository=source_repository,
        artifact_repository=source_repository,
        provider_name="alpaca_live",
    )
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
            config_resolver=RiskConfigResolver(),
            position_sizer=PositionSizer(),
            risk_manager=RiskManager(),
        ),
        trading_decision_pipeline=TradingDecisionPipeline(
            repository=trading_repository,
            prompt_registry=PromptRegistry.get_default(),
            manual_request_service=manual_request_service,
            model_name=app_config.TRADING_MODEL_NAME,
            agent_runner=_default_agent_runner,
        ),
        paper_execution_workflow=PaperExecutionWorkflow(
            repository=trading_repository,
            broker=broker,
            manual_request_service=manual_request_service,
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


class _LiveRiskWorkflow:
    def __init__(
        self,
        *,
        repository: Any,
        source_repository: Any,
        config_resolver: Any,
        position_sizer: Any,
        risk_manager: Any,
    ) -> None:
        self.repository = repository
        self.source_repository = source_repository
        self.config_resolver = config_resolver
        self.position_sizer = position_sizer
        self.risk_manager = risk_manager

    def run(
        self,
        *,
        candidates: tuple[object, ...],
        classifications: tuple[object, ...],
        portfolio_context: object,
        decision_time: datetime,
    ) -> object:
        from types import SimpleNamespace

        signal_by_id = {
            snapshot.signal_snapshot_id: snapshot
            for snapshot in self.repository.load_signal_snapshots_for_decision(
                decision_time=decision_time,
                snapshot_type="pre_open",
            )
        }
        config = self.config_resolver.resolve(
            risk_appetite="balanced",
            portfolio_context=portfolio_context,
            macro_risk_budget_multiplier=1.0,
        )
        portfolio_snapshot = self.risk_manager.build_portfolio_risk_snapshot(portfolio_context, config)
        exposures = self.risk_manager.compute_factor_exposures(portfolio_context)
        self.repository.save_portfolio_risk_snapshot(portfolio_snapshot)
        self.repository.save_risk_factor_exposures(exposures)
        candidate_by_id = {candidate.candidate_score_id: candidate for candidate in candidates}
        decisions: list[object] = []
        for classification in classifications:
            candidate = candidate_by_id.get(classification.candidate_score_id)
            if candidate is None:
                continue
            snapshot = signal_by_id.get(candidate.signal_snapshot_id)
            request = _build_trade_risk_request(
                candidate=candidate,
                classification=classification,
                snapshot=snapshot,
                source_repository=self.source_repository,
                decision_time=decision_time,
            )
            sizing = self.position_sizer.size_position(request, portfolio_context, config)
            decision = self.risk_manager.evaluate(request, sizing, portfolio_context, config)
            decision = replace(
                decision,
                portfolio_risk_snapshot_id=portfolio_snapshot.portfolio_risk_snapshot_id,
            )
            self.repository.save_position_sizing_decision(sizing)
            self.repository.save_risk_decision(decision)
            decisions.append(decision)
        return SimpleNamespace(risk_decisions=tuple(decisions))


def _build_trade_risk_request(
    *,
    candidate: Any,
    classification: Any,
    snapshot: Any,
    source_repository: Any,
    decision_time: datetime,
) -> Any:
    from src.trading.risk.context import TradeRiskRequest

    technical = dict(getattr(snapshot, "signal_json", {}).get("technical", {}))
    source_freshness = dict(getattr(snapshot, "source_freshness_json", {}))
    price = _latest_price_from_sources(
        source_repository=source_repository,
        ticker=candidate.ticker,
        decision_time=decision_time,
    )
    atr_pct = float(technical.get("atr_pct") or 0.0)
    average_daily_dollar_volume = float(technical.get("dollar_volume") or 0.0)
    return TradeRiskRequest(
        candidate=candidate,
        classification=classification,
        instrument_type="watch" if classification.trade_identity == "watch_only" else "stock",
        target_weight=min(max(float(candidate.candidate_score) * 0.05, 0.0), 0.10),
        confidence=min(max(float(candidate.candidate_score), 0.0), 1.0),
        sector=None,
        beta_bucket=None,
        volatility_bucket="high" if atr_pct >= 0.05 else "medium",
        liquidity_bucket="thin" if average_daily_dollar_volume and average_daily_dollar_volume < 25_000_000 else "liquid",
        event_type=None,
        macro_sensitivity=None,
        price=price,
        atr_pct=atr_pct,
        average_daily_dollar_volume=average_daily_dollar_volume,
        signal_freshness=source_freshness,
        estimated_margin_requirement=max(price, 1.0),
        estimated_buying_power_effect=max(price, 1.0),
        estimated_initial_margin_requirement=max(price, 1.0),
        estimated_maintenance_margin_requirement=max(price * 0.5, 1.0),
    )


def _latest_price_from_sources(*, source_repository: Any, ticker: str, decision_time: datetime) -> float:
    technical_rows = source_repository.latest_available_by_family(ticker, "technical", decision_time)
    if not technical_rows:
        return 1.0
    bars = list((technical_rows[-1].payload or {}).get("bars") or [])
    if not bars:
        return 1.0
    last_bar = bars[-1]
    close = last_bar.get("close")
    if isinstance(close, (int, float)) and close > 0:
        return float(close)
    return 1.0
