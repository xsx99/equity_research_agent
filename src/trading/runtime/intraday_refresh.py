"""Live intraday refresh runtime assembly and orchestration."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable

from src.core import config as app_config
from src.trading.intraday.news_alerts import NewsAlertService
from src.trading.intraday.rebalance import IntradayRebalancePipeline, IntradayRebalanceRequest
from src.trading.intraday.signals import IntradaySignalScanRecord, build_intraday_signal_snapshot
from src.trading.runtime.support import build_execution_report, build_runtime_report
from src.trading.signals.sources import EventNewsItemRecord, SourceRecord


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


class LiveIntradayRefreshRuntime:
    """Run the live intraday signal refresh plus rebalance chain."""

    def __init__(
        self,
        *,
        dependencies: LiveIntradayRefreshDependencies,
        now: Callable[[], datetime] | None = None,
        execute_paper_orders: bool = False,
    ) -> None:
        self.dependencies = dependencies
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.execute_paper_orders = execute_paper_orders

    def run(self) -> dict[str, Any]:
        decision_time = self.now()
        tickers = self.dependencies.scope_loader.load_scope(decision_time=decision_time)
        if not tickers:
            return build_runtime_report(
                phase="intraday_refresh",
                as_of=decision_time,
                summary={
                    "ticker_count": 0,
                    "intraday_signal_snapshot_count": 0,
                    "news_alert_count": 0,
                    "intraday_rebalance_decision_count": 0,
                },
                execution=build_execution_report(mode="dry_run", orders_submitted=0),
            )

        baselines = self.dependencies.baseline_loader.load_for_tickers(
            tickers=tickers,
            decision_time=decision_time,
        )
        previous_by_ticker = self.dependencies.previous_snapshot_loader.load_for_tickers(
            tickers=tickers,
            decision_time=decision_time,
        )
        request_contexts = self.dependencies.request_context_loader.load_for_tickers(
            tickers=tickers,
            decision_time=decision_time,
        )
        portfolio_result = self.dependencies.portfolio_sync_workflow.run(as_of=decision_time)
        positions = tuple(getattr(portfolio_result, "positions", ()))

        scan = IntradaySignalScanRecord(
            intraday_signal_scan_id=str(uuid.uuid4()),
            started_at=decision_time,
            completed_at=decision_time,
            decision_time=decision_time,
            status="succeeded",
            scope_json={"tickers": list(tickers)},
            coverage_json={"ticker_count": len(tickers)},
            metadata_json={},
        )
        self.dependencies.trading_repository.save_intraday_signal_scan(scan)

        snapshots = []
        for ticker in tickers:
            baseline = baselines.get(ticker)
            if baseline is None:
                continue
            technical_rows = self.dependencies.source_repository.latest_available_by_family(
                ticker,
                "technical",
                decision_time,
            )
            refreshed_signals_json, source_freshness = _build_intraday_refresh_payload(
                baseline=baseline,
                technical_rows=technical_rows,
            )
            snapshot = build_intraday_signal_snapshot(
                intraday_signal_scan_id=scan.intraday_signal_scan_id,
                ticker=ticker,
                decision_time=decision_time,
                baseline_snapshot=baseline,
                previous_intraday_snapshot=previous_by_ticker.get(ticker),
                refreshed_signals_json=refreshed_signals_json,
                source_freshness_json=source_freshness,
            )
            self.dependencies.trading_repository.save_intraday_signal_snapshot(snapshot)
            snapshots.append(snapshot)

        existing_dedupe_keys = self.dependencies.existing_news_dedupe_key_loader(tickers, decision_time)
        affected_positions_by_ticker = self.dependencies.position_context_loader(tickers, positions)
        affected_candidates_by_ticker = self.dependencies.candidate_context_loader(tickers, decision_time)
        affected_themes_by_ticker = self.dependencies.theme_context_loader(tickers, decision_time)
        event_items = _load_event_items(
            source_repository=self.dependencies.source_repository,
            tickers=tickers,
            decision_time=decision_time,
        )
        alerts = self.dependencies.news_alert_service.build_alerts(
            event_items=event_items,
            existing_dedupe_keys=existing_dedupe_keys,
            affected_positions_by_ticker=affected_positions_by_ticker,
            affected_candidates_by_ticker=affected_candidates_by_ticker,
            affected_themes_by_ticker=affected_themes_by_ticker,
        )
        for alert in alerts:
            self.dependencies.trading_repository.save_news_alert(alert)

        alert_map: dict[str, list[dict[str, Any]]] = {}
        for alert in alerts:
            alert_map.setdefault(alert.ticker, []).append(
                {
                    "alert_type": alert.alert_type if hasattr(alert, "alert_type") else None,
                    "severity": getattr(alert, "severity", None),
                    "sentiment": getattr(alert, "sentiment", None),
                    "headline": getattr(alert, "headline", None),
                    "summary": getattr(alert, "summary", None),
                }
            )
        rebalance_requests = tuple(
            _build_rebalance_request(
                ticker=snapshot.ticker,
                baseline=baselines[snapshot.ticker],
                snapshot=snapshot,
                context=request_contexts.get(snapshot.ticker),
                position=_position_by_ticker(positions).get(snapshot.ticker),
                alerts=tuple(alert_map.get(snapshot.ticker, ())),
            )
            for snapshot in snapshots
        )
        rebalance_result = self.dependencies.rebalance_pipeline.run(
            rebalance_requests=rebalance_requests,
            portfolio_context=getattr(portfolio_result, "portfolio_context", portfolio_result),
            risk_appetite="balanced",
            trade_date=decision_time if self.execute_paper_orders else None,
            execute_approved=self.execute_paper_orders,
        )
        execution = build_execution_report(mode="execute" if self.execute_paper_orders else "dry_run", orders_submitted=0)
        return build_runtime_report(
            phase="intraday_refresh",
            as_of=decision_time,
            summary={
                "ticker_count": len(tickers),
                "intraday_signal_snapshot_count": len(snapshots),
                "news_alert_count": len(alerts),
                "intraday_rebalance_decision_count": len(tuple(getattr(rebalance_result, "decisions", ()))),
            },
            execution=execution,
        )


def run_live_intraday_refresh_once(
    *,
    dependencies: LiveIntradayRefreshDependencies | None = None,
    execute_paper_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Execute one live intraday refresh run with injected dependencies."""
    return run_intraday_refresh_once(
        dependencies=dependencies,
        execute_paper_orders=execute_paper_orders,
        now=now,
    )


def run_intraday_refresh_once(
    *,
    dependencies: LiveIntradayRefreshDependencies | None = None,
    execute_paper_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Execute one live intraday refresh run with injected dependencies."""
    if dependencies is not None:
        return LiveIntradayRefreshRuntime(
            dependencies=dependencies,
            now=now,
            execute_paper_orders=execute_paper_orders,
        ).run()

    from src.db.connection import get_session

    with get_session() as session:
        return LiveIntradayRefreshRuntime(
            dependencies=build_live_intraday_refresh_dependencies(session),
            now=now,
            execute_paper_orders=execute_paper_orders,
        ).run()


def build_live_intraday_refresh_dependencies(session: Any | None = None) -> LiveIntradayRefreshDependencies:
    """Build the default production dependency graph for one live intraday refresh run."""
    if session is None:
        raise RuntimeError("db_session_required_for_live_intraday_refresh_dependencies")

    from src.agents.prompt_registry import PromptRegistry
    from src.agents.trading import _default_agent_runner
    from src.trading.brokers.paper_stock import PaperStockBroker
    from src.trading.repositories.source_sqlalchemy import SQLAlchemySignalSourceRepository
    from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
    from src.trading.workflows.portfolio_sync import BrokerPortfolioSyncWorkflow

    trading_repository = SqlAlchemyTradingRepository(session)
    source_repository = SQLAlchemySignalSourceRepository(session)
    broker = PaperStockBroker()
    return LiveIntradayRefreshDependencies(
        scope_loader=_RepositoryIntradayScopeLoader(trading_repository),
        baseline_loader=_RepositoryBaselineLoader(trading_repository),
        previous_snapshot_loader=_RepositoryPreviousIntradaySnapshotLoader(trading_repository),
        request_context_loader=_RepositoryIntradayRequestContextLoader(trading_repository),
        source_repository=source_repository,
        portfolio_sync_workflow=BrokerPortfolioSyncWorkflow(repository=trading_repository, broker=broker),
        news_alert_service=NewsAlertService(),
        rebalance_pipeline=IntradayRebalancePipeline(
            repository=trading_repository,
            prompt_registry=PromptRegistry.get_default(),
            model_name=app_config.TRADING_MODEL_NAME,
            agent_runner=_default_agent_runner,
            broker=broker,
        ),
        trading_repository=trading_repository,
        existing_news_dedupe_key_loader=lambda tickers, decision_time: trading_repository.load_existing_news_alert_dedupe_keys(
            tickers=tickers,
            trade_date=decision_time.date(),
        ),
        candidate_context_loader=lambda tickers, decision_time: trading_repository.load_intraday_candidate_context(
            tickers=tickers,
            trade_date=decision_time.date(),
        ),
        position_context_loader=lambda tickers, positions: {
            ticker: (ticker,)
            for ticker in tickers
            if ticker in {getattr(position, "ticker", None) for position in positions}
        },
        theme_context_loader=lambda tickers, decision_time: {},
    )


class _RepositoryIntradayScopeLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def load_scope(self, *, decision_time: datetime) -> tuple[str, ...]:
        return self.repository.load_intraday_scope(trade_date=decision_time.date())


class _RepositoryBaselineLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def load_for_tickers(self, *, tickers: tuple[str, ...], decision_time: datetime) -> dict[str, Any]:
        return self.repository.load_latest_signal_snapshots_for_tickers(
            tickers=tickers,
            snapshot_type="pre_open",
            trade_date=decision_time.date(),
        )


class _RepositoryPreviousIntradaySnapshotLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def load_for_tickers(self, *, tickers: tuple[str, ...], decision_time: datetime) -> dict[str, Any]:
        return self.repository.load_latest_intraday_signal_snapshots_for_tickers(
            tickers=tickers,
            trade_date=decision_time.date(),
        )


class _RepositoryIntradayRequestContextLoader:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def load_for_tickers(self, *, tickers: tuple[str, ...], decision_time: datetime) -> dict[str, Any]:
        return self.repository.load_intraday_request_contexts(
            tickers=tickers,
            trade_date=decision_time.date(),
        )


def _build_intraday_refresh_payload(
    *,
    baseline: Any,
    technical_rows: tuple[SourceRecord, ...],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    bars = list((technical_rows[-1].payload or {}).get("bars") or []) if technical_rows else []
    last_bar = bars[-1] if bars else {}
    refreshed = {
        "technical": {
            "last_price": float(last_bar.get("close") or baseline.signal_json.get("technical", {}).get("last_price") or 0.0),
            "atr_pct": float(baseline.signal_json.get("technical", {}).get("atr_pct") or 0.0),
            "dollar_volume": float(baseline.signal_json.get("technical", {}).get("dollar_volume") or 0.0),
        }
    }
    freshness = {"technical": "fresh" if technical_rows else "missing"}
    return refreshed, freshness


def _load_event_items(*, source_repository: Any, tickers: tuple[str, ...], decision_time: datetime) -> tuple[EventNewsItemRecord, ...]:
    items: list[EventNewsItemRecord] = []
    for ticker in tickers:
        rows = source_repository.latest_available_by_family(ticker, "events_news", decision_time)
        for row in rows:
            items.append(_event_item_from_source_record(ticker=ticker, record=row))
    return tuple(items)


def _event_item_from_source_record(*, ticker: str, record: SourceRecord) -> EventNewsItemRecord:
    payload = dict(record.payload or {})
    return EventNewsItemRecord(
        event_news_item_id=str(payload.get("event_news_item_id") or record.source_record_id),
        ticker=str(payload.get("ticker") or ticker),
        source_ticker=payload.get("source_ticker"),
        event_type=str(payload.get("event_type") or "news"),
        direction=payload.get("direction"),
        sentiment=payload.get("sentiment"),
        importance=payload.get("importance"),
        headline=payload.get("headline"),
        summary=payload.get("summary"),
        provider=str(payload.get("provider") or record.source),
        source_refs_json=list(payload.get("source_refs_json") or []),
        dedupe_key=str(payload.get("dedupe_key") or record.source_record_id),
        event_time=record.event_time,
        published_at=record.published_at,
        ingested_at=record.ingested_at,
        available_for_decision_at=record.available_for_decision_at,
        raw_payload_ref=None,
        metadata_json=dict(payload.get("metadata_json") or {}),
    )


def _build_rebalance_request(
    *,
    ticker: str,
    baseline: Any,
    snapshot: Any,
    context: Any,
    position: Any | None,
    alerts: tuple[dict[str, Any], ...],
) -> IntradayRebalanceRequest:
    context = context or SimpleNamespace(
        selection_source=baseline.selection_source,
        strategy_id="intraday_refresh_unknown",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        candidate_score=0.0,
        target_weight=0.0,
        allow_open_new=False,
    )
    technical = dict(snapshot.refreshed_signals_json.get("technical", {}))
    event_signals = list(alerts)
    return IntradayRebalanceRequest(
        ticker=ticker,
        baseline_signal_snapshot_id=baseline.signal_snapshot_id,
        intraday_signal_snapshot_id=snapshot.intraday_signal_snapshot_id,
        previous_intraday_snapshot_id=snapshot.previous_intraday_snapshot_id,
        selection_source=str(getattr(context, "selection_source", baseline.selection_source)),
        strategy_id=str(getattr(context, "strategy_id", "intraday_refresh_unknown")),
        strategy_version=str(getattr(context, "strategy_version", "v1")),
        expression_bucket_id=str(getattr(context, "expression_bucket_id", "long_stock")),
        expression_bucket_version=str(getattr(context, "expression_bucket_version", "v1")),
        trade_identity=str(getattr(context, "trade_identity", "tactical_stock_trade")),
        instrument_type=str(getattr(context, "instrument_type", "stock")),
        decision_time=snapshot.decision_time,
        available_for_decision_at=snapshot.decision_time,
        current_price=float(technical.get("last_price") or 0.0),
        atr_pct=float(technical.get("atr_pct") or 0.0),
        average_daily_dollar_volume=float(technical.get("dollar_volume") or 0.0),
        existing_position=position is not None,
        current_position_quantity=float(getattr(position, "quantity", 0.0) or 0.0),
        current_position_market_value=float(getattr(position, "market_value", 0.0) or 0.0),
        candidate_score=float(getattr(context, "candidate_score", 0.0) or 0.0),
        target_weight=float(getattr(context, "target_weight", 0.0) or 0.0),
        signal_freshness=dict(snapshot.source_freshness_json),
        delta_vs_baseline_json=dict(snapshot.delta_vs_baseline_json),
        delta_vs_previous_json=dict(snapshot.delta_vs_previous_json),
        alerts=event_signals,
        allow_open_new=bool(getattr(context, "allow_open_new", False)),
        direct_company_negative_evidence=any(alert.get("sentiment") == "negative" for alert in alerts),
        bearish_signal_sources=tuple(
            "events_news"
            for alert in alerts
            if alert.get("sentiment") == "negative"
        ),
        metadata_json={},
    )


def _position_by_ticker(positions: tuple[object, ...]) -> dict[str, object]:
    return {getattr(position, "ticker"): position for position in positions}
