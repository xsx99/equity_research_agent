"""Runtime runner for the live intraday refresh phase."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable

from src.trading.intraday.signals import IntradaySignalScanRecord, build_intraday_signal_snapshot
from src.trading.risk import RiskConfigResolver
from src.trading.runtime.intraday_refresh_dependencies import LiveIntradayRefreshDependencies
from src.trading.runtime.intraday_refresh_helpers import (
    _build_alert_map,
    _build_intraday_refresh_payload,
    _build_rebalance_request,
    _load_social_macro_items,
    _load_event_items,
    _position_by_ticker,
    build_intraday_calendar_events,
    build_intraday_event_assessments,
    mark_material_event_assessment_changes,
)
from src.trading.runtime.support import build_execution_report, build_runtime_report


class LiveIntradayRefreshRuntime:
    """Run the live intraday signal refresh plus rebalance chain."""

    def __init__(
        self,
        *,
        dependencies: LiveIntradayRefreshDependencies,
        now: Callable[[], datetime] | None = None,
        execute_paper_orders: bool = False,
        execute_paper_option_orders: bool = False,
    ) -> None:
        self.dependencies = dependencies
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.execute_paper_orders = execute_paper_orders
        self.execute_paper_option_orders = execute_paper_option_orders

    def run(self) -> dict[str, Any]:
        self._validate_execution_policy()
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
                execution=build_execution_report(mode="dry_run", orders_submitted=0, option_orders_submitted=0),
            )
        if self.dependencies.source_ingestion_service is not None:
            self.dependencies.source_ingestion_service.refresh_tickers(
                tuple(tickers),
                as_of=decision_time,
                run_type="intraday_refresh",
                source_families=("technical", "events_news", "social_macro", "option_chain"),
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
        portfolio_context = getattr(portfolio_result, "portfolio_context", portfolio_result)
        positions = _intraday_positions(portfolio_result=portfolio_result, portfolio_context=portfolio_context)
        risk_portfolio_context = _portfolio_context_with_positions(
            portfolio_context=portfolio_context,
            positions=positions,
        )
        macro_snapshot = _load_intraday_macro_snapshot(self.dependencies, decision_time=decision_time)

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
        alert_source_items = []
        source_items_by_ticker: dict[str, list[object]] = {}
        positions_by_ticker = _position_by_ticker(positions)
        for ticker in tickers:
            baseline = baselines.get(ticker)
            if baseline is None:
                continue
            technical_rows = self.dependencies.source_repository.latest_available_by_family(
                ticker,
                "technical",
                decision_time,
            )
            event_news_rows = self.dependencies.source_repository.latest_available_by_family(
                ticker,
                "events_news",
                decision_time,
            )
            social_macro_rows = self.dependencies.source_repository.latest_available_by_family(
                ticker,
                "social_macro",
                decision_time,
            )
            insider_rows = self.dependencies.source_repository.latest_available_by_family(
                ticker,
                "insider",
                decision_time,
            )
            context = request_contexts.get(ticker)
            instrument_type = _intraday_instrument_type(context=context, position=positions_by_ticker.get(ticker))
            option_chain_rows = self.dependencies.source_repository.latest_available_by_family(
                ticker,
                "option_chain",
                decision_time,
            ) if instrument_type == "option" else ()
            refreshed_signals_json, source_freshness = _build_intraday_refresh_payload(
                baseline=baseline,
                decision_time=decision_time,
                technical_rows=technical_rows,
                event_news_rows=event_news_rows,
                social_macro_rows=social_macro_rows,
                insider_rows=insider_rows,
                option_chain_rows=option_chain_rows,
                instrument_type=instrument_type,
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
            event_items = _load_event_items(ticker=ticker, event_news_rows=event_news_rows)
            social_items = _load_social_macro_items(ticker=ticker, social_macro_rows=social_macro_rows)
            alert_source_items.extend(event_items)
            alert_source_items.extend(social_items)
            source_items_by_ticker.setdefault(ticker, []).extend(event_items)
            source_items_by_ticker.setdefault(ticker, []).extend(social_items)

        calendar_events = build_intraday_calendar_events(
            calendar_event_pipeline=self.dependencies.calendar_event_pipeline,
            source_items_by_ticker={ticker: tuple(items) for ticker, items in source_items_by_ticker.items()},
            decision_time=decision_time,
        )
        if calendar_events and hasattr(self.dependencies.trading_repository, "save_calendar_events"):
            self.dependencies.trading_repository.save_calendar_events(calendar_events)
        previous_assessments = ()
        if hasattr(self.dependencies.trading_repository, "load_portfolio_event_risk_assessments"):
            previous_assessments = self.dependencies.trading_repository.load_portfolio_event_risk_assessments(
                decision_time=decision_time,
            )
        event_assessments = build_intraday_event_assessments(
            event_risk_pipeline=self.dependencies.event_risk_pipeline,
            calendar_events=calendar_events,
            request_contexts=request_contexts,
            portfolio_context=risk_portfolio_context,
            decision_time=decision_time,
        )
        event_assessments = mark_material_event_assessment_changes(
            assessments=event_assessments,
            previous_assessments=previous_assessments,
        )
        if event_assessments and hasattr(self.dependencies.trading_repository, "save_portfolio_event_risk_assessments"):
            self.dependencies.trading_repository.save_portfolio_event_risk_assessments(event_assessments)

        existing_dedupe_keys = self.dependencies.existing_news_dedupe_key_loader(tickers, decision_time)
        affected_positions_by_ticker = self.dependencies.position_context_loader(tickers, positions)
        affected_candidates_by_ticker = self.dependencies.candidate_context_loader(tickers, decision_time)
        affected_themes_by_ticker = self.dependencies.theme_context_loader(tickers, decision_time)
        alerts = self.dependencies.news_alert_service.build_alerts(
            source_items=tuple(alert_source_items),
            existing_dedupe_keys=existing_dedupe_keys,
            affected_positions_by_ticker=affected_positions_by_ticker,
            affected_candidates_by_ticker=affected_candidates_by_ticker,
            affected_themes_by_ticker=affected_themes_by_ticker,
        )
        for alert in alerts:
            self.dependencies.trading_repository.save_news_alert(alert)

        alert_map = _build_alert_map(alerts)
        rebalance_requests = tuple(
            _build_rebalance_request(
                ticker=snapshot.ticker,
                baseline=baselines[snapshot.ticker],
                snapshot=snapshot,
                context=request_contexts.get(snapshot.ticker),
                position=positions_by_ticker.get(snapshot.ticker),
                alerts=tuple(alert_map.get(snapshot.ticker, ())),
            )
            for snapshot in snapshots
        )
        portfolio_context = getattr(portfolio_result, "portfolio_context", portfolio_result)
        portfolio_risk_intent = None
        if self.dependencies.lookahead_helper is not None:
            macro_risk_state = _intraday_macro_risk_state(
                macro_snapshot=macro_snapshot,
                fallback_loader=self.dependencies.macro_state_loader,
                decision_time=decision_time,
            )
            config = RiskConfigResolver().resolve(
                risk_appetite="balanced",
                portfolio_context=risk_portfolio_context,
                macro_risk_budget_multiplier=float(getattr(macro_snapshot, "risk_budget_multiplier", 1.0) or 1.0),
            )
            portfolio_risk_intent = _build_intraday_intent_with_optional_context(
                self.dependencies.lookahead_helper,
                rebalance_requests=rebalance_requests,
                portfolio_context=risk_portfolio_context,
                config=config,
                decision_time=decision_time,
                macro_risk_state=macro_risk_state,
                macro_snapshot=macro_snapshot,
                event_assessments=event_assessments,
            )
        rebalance_result = self.dependencies.rebalance_pipeline.run(
            rebalance_requests=rebalance_requests,
            portfolio_context=portfolio_context,
            risk_appetite="balanced",
            portfolio_risk_intent=portfolio_risk_intent,
            trade_date=decision_time if self.execute_paper_orders else None,
            execute_approved=self.execute_paper_orders,
        )
        execution = build_execution_report(
            mode="execute" if self.execute_paper_orders else "dry_run",
            orders_submitted=self._submitted_orders(rebalance_result),
            option_orders_submitted=self._submitted_option_orders(rebalance_result),
            orders_skipped=self._skipped_orders(rebalance_result),
            orders_failed=self._failed_orders(rebalance_result),
            skip_reasons=self._skip_reasons(rebalance_result),
        )
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

    def _submitted_orders(self, rebalance_result: object) -> int:
        summary = getattr(rebalance_result, "execution_summary", {}) or {}
        return int(summary.get("orders_submitted", 0) or 0) if self.execute_paper_orders else 0

    def _submitted_option_orders(self, rebalance_result: object) -> int:
        if not self.execute_paper_orders or not self.execute_paper_option_orders:
            return 0
        summary = getattr(rebalance_result, "execution_summary", {}) or {}
        return int(summary.get("option_orders_submitted", 0) or 0)

    def _skipped_orders(self, rebalance_result: object) -> int:
        if not self.execute_paper_orders:
            return 0
        summary = getattr(rebalance_result, "execution_summary", {}) or {}
        return int(summary.get("orders_skipped", 0) or 0)

    def _failed_orders(self, rebalance_result: object) -> int:
        if not self.execute_paper_orders:
            return 0
        summary = getattr(rebalance_result, "execution_summary", {}) or {}
        return int(summary.get("orders_failed", 0) or 0)

    def _skip_reasons(self, rebalance_result: object) -> dict[str, int]:
        if not self.execute_paper_orders:
            return {}
        summary = getattr(rebalance_result, "execution_summary", {}) or {}
        return {
            str(reason): int(count)
            for reason, count in dict(summary.get("skip_reasons", {}) or {}).items()
        }

    def _validate_execution_policy(self) -> None:
        if self.execute_paper_option_orders and not self.execute_paper_orders:
            raise ValueError("option_execution_requires_paper_order_execution")


def _intraday_positions(
    *,
    portfolio_result: object,
    portfolio_context: object,
) -> tuple[object, ...]:
    context_positions = tuple(getattr(portfolio_context, "positions", ()) or ())
    if context_positions:
        return context_positions
    return tuple(getattr(portfolio_result, "positions", ()) or ())


def _intraday_instrument_type(
    *,
    context: object | None,
    position: object | None,
) -> str:
    instrument_type = str(getattr(context, "instrument_type", "stock") or "stock")
    if instrument_type == "option":
        return "option"
    trade_identity = str(getattr(position, "trade_identity", "") or "")
    if trade_identity in {"tactical_option_trade", "risk_hedge_overlay"}:
        return "option"
    return instrument_type


def _portfolio_context_with_positions(
    *,
    portfolio_context: object,
    positions: tuple[object, ...],
) -> object:
    if hasattr(portfolio_context, "positions"):
        return portfolio_context
    if isinstance(portfolio_context, SimpleNamespace):
        values = dict(vars(portfolio_context))
        values["positions"] = positions
        return SimpleNamespace(**values)
    values = dict(getattr(portfolio_context, "__dict__", {}) or {})
    values["positions"] = positions
    return SimpleNamespace(**values)


def _load_intraday_macro_snapshot(
    dependencies: LiveIntradayRefreshDependencies,
    *,
    decision_time: datetime,
) -> object | None:
    loader = getattr(dependencies, "macro_snapshot_loader", None)
    snapshot = loader(decision_time) if callable(loader) else None
    if not _should_refresh_intraday_macro_snapshot(snapshot):
        return snapshot
    pipeline = getattr(dependencies, "macro_snapshot_pipeline", None)
    if pipeline is None:
        return snapshot
    refreshed = pipeline.build_snapshot(as_of=decision_time)
    if hasattr(dependencies.trading_repository, "save_macro_snapshot"):
        dependencies.trading_repository.save_macro_snapshot(refreshed)
    return refreshed


def _should_refresh_intraday_macro_snapshot(snapshot: object | None) -> bool:
    if snapshot is None:
        return True
    freshness = dict(getattr(snapshot, "source_freshness", {}) or {}).get("global_context", {})
    status = str(dict(freshness or {}).get("status") or "").lower()
    return status in {"failed", "missing", "stale"}


def _intraday_macro_risk_state(
    *,
    macro_snapshot: object | None,
    fallback_loader: Callable[[datetime], str | None],
    decision_time: datetime,
) -> str | None:
    regime = str(getattr(macro_snapshot, "regime", "") or "").lower()
    if regime == "risk_off":
        return "high"
    if regime == "unavailable":
        return "watch"
    return fallback_loader(decision_time)


def _build_intraday_intent_with_optional_context(
    lookahead_helper: Any,
    *,
    rebalance_requests: tuple[object, ...],
    portfolio_context: object,
    config: object,
    decision_time: datetime,
    macro_risk_state: str | None,
    macro_snapshot: object | None,
    event_assessments: tuple[object, ...],
) -> object:
    try:
        return lookahead_helper.build_intraday_portfolio_risk_intent(
            rebalance_requests=rebalance_requests,
            portfolio_context=portfolio_context,
            config=config,
            decision_time=decision_time,
            macro_risk_state=macro_risk_state,
            macro_snapshot=macro_snapshot,
            event_assessments=event_assessments,
        )
    except TypeError as exc:
        message = str(exc)
        if "macro_snapshot" not in message and "event_assessments" not in message:
            raise
        return lookahead_helper.build_intraday_portfolio_risk_intent(
            rebalance_requests=rebalance_requests,
            portfolio_context=portfolio_context,
            config=config,
            decision_time=decision_time,
            macro_risk_state=macro_risk_state,
        )
