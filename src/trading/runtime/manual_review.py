"""Live manual-review runtime assembly and orchestration."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable

from src.trading.runtime.preopen import build_live_preopen_dependencies
from src.trading.runtime.support import build_execution_report, build_runtime_report, summarize_execution_attempts


@dataclass(frozen=True)
class LiveManualReviewDependencies:
    universe_filter_loader: Any
    manual_request_loader: Any
    universe_scan_pipeline: Any
    signal_pipeline: Any
    strategy_pipeline: Any
    portfolio_sync_workflow: Any
    risk_workflow: Any
    trading_decision_pipeline: Any
    paper_execution_workflow: Any | None = None
    trading_repository: Any | None = None


@dataclass(frozen=True)
class ManualReviewExecutionResult:
    report: dict[str, Any]
    submitted_order_tickers: frozenset[str]


class LiveManualReviewRuntime:
    """Run the live trading chain for active manual-review requests only."""

    def __init__(
        self,
        *,
        dependencies: LiveManualReviewDependencies,
        now: Callable[[], datetime] | None = None,
        execute_paper_orders: bool = False,
    ) -> None:
        self.dependencies = dependencies
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.execute_paper_orders = execute_paper_orders

    def run(self) -> dict[str, Any]:
        decision_time = self.now()
        manual_requests = self.dependencies.manual_request_loader.load_active()
        if not manual_requests:
            return build_runtime_report(
                phase="manual_review",
                as_of=decision_time,
                summary={
                    "manual_request_count": 0,
                    "review_only_request_count": 0,
                    "paper_trade_eligible_request_count": 0,
                    "signal_snapshot_count": 0,
                    "candidate_count": 0,
                    "classification_count": 0,
                    "risk_decision_count": 0,
                    "trading_decision_count": 0,
                },
                execution=build_execution_report(mode="dry_run", orders_submitted=0),
            )
        config = self._scope_config(self.dependencies.universe_filter_loader.load_active())
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
        decision_rows = tuple(getattr(decision_result, "decisions", ()))
        risk_rows = tuple(getattr(risk_result, "risk_decisions", ()))
        operational_counts = _manual_review_operational_counts(
            manual_requests=manual_requests,
            decisions=decision_rows,
            risk_decisions=risk_rows,
            submitted_order_tickers=execution.submitted_order_tickers,
        )
        return build_runtime_report(
            phase="manual_review",
            as_of=decision_time,
            summary={
                "manual_request_count": len(manual_requests),
                "review_only_request_count": sum(1 for request in manual_requests if request.mode == "review_only"),
                "paper_trade_eligible_request_count": sum(
                    1 for request in manual_requests if request.mode == "paper_trade_eligible"
                ),
                "signal_snapshot_count": len(snapshots),
                "candidate_count": len(tuple(getattr(strategy_result, "candidates", ()))),
                "classification_count": len(tuple(getattr(strategy_result, "classifications", ()))),
                "risk_decision_count": len(risk_rows),
                "trading_decision_count": len(decision_rows),
                **operational_counts,
            },
            execution=execution.report,
        )

    def _scope_config(self, config: Any) -> Any:
        if hasattr(config, "manual_include"):
            return replace(config, manual_include=())
        return config

    def _run_execution(
        self,
        *,
        decisions: tuple[object, ...],
        risk_decisions: tuple[object, ...],
        as_of: datetime,
    ) -> ManualReviewExecutionResult:
        if not self.execute_paper_orders:
            return ManualReviewExecutionResult(
                report=build_execution_report(mode="dry_run", orders_submitted=0, option_orders_submitted=0),
                submitted_order_tickers=frozenset(),
            )
        workflow = self.dependencies.paper_execution_workflow
        if workflow is None:
            raise RuntimeError("paper_execution_workflow_not_configured")
        result = workflow.run(
            trading_decisions=decisions,
            risk_decisions=risk_decisions,
            trade_date=as_of,
            phase="manual_review",
        )
        submitted_orders = tuple(getattr(result, "paper_orders", ()))
        submitted_option_orders = tuple(getattr(result, "paper_option_orders", ()))
        attempts = tuple(getattr(result, "execution_attempts", ()))
        attempt_summary = summarize_execution_attempts(attempts)
        return ManualReviewExecutionResult(
            report=build_execution_report(
                mode="execute",
                orders_submitted=(
                    int(attempt_summary["orders_submitted"])
                    if attempts
                    else len(submitted_orders)
                ),
                option_orders_submitted=(
                    int(attempt_summary["option_orders_submitted"])
                    if attempts
                    else len(submitted_option_orders)
                ),
                orders_skipped=int(attempt_summary["orders_skipped"]),
                orders_failed=int(attempt_summary["orders_failed"]),
                skip_reasons=dict(attempt_summary["skip_reasons"]),
            ),
            submitted_order_tickers=frozenset(
                str(getattr(order, "ticker", "") or "").strip().upper()
                for order in submitted_orders
                if str(getattr(order, "ticker", "") or "").strip()
            ),
        )


def build_live_manual_review_dependencies(session: Any | None = None) -> LiveManualReviewDependencies:
    """Build the default production dependency graph for one live manual-review run."""
    if session is None:
        raise RuntimeError("db_session_required_for_live_manual_review_dependencies")
    preopen_dependencies = build_live_preopen_dependencies(session)
    return LiveManualReviewDependencies(
        universe_filter_loader=preopen_dependencies.universe_filter_loader,
        manual_request_loader=preopen_dependencies.manual_request_loader,
        universe_scan_pipeline=preopen_dependencies.universe_scan_pipeline,
        signal_pipeline=preopen_dependencies.signal_pipeline,
        strategy_pipeline=preopen_dependencies.strategy_pipeline,
        portfolio_sync_workflow=preopen_dependencies.portfolio_sync_workflow,
        risk_workflow=preopen_dependencies.risk_workflow,
        trading_decision_pipeline=preopen_dependencies.trading_decision_pipeline,
        paper_execution_workflow=preopen_dependencies.paper_execution_workflow,
        trading_repository=preopen_dependencies.trading_repository,
    )


def run_live_manual_review_once(
    *,
    dependencies: LiveManualReviewDependencies | None = None,
    execute_paper_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Execute one live manual-review run with injected dependencies."""
    return run_manual_review_once(
        dependencies=dependencies,
        execute_paper_orders=execute_paper_orders,
        now=now,
    )


def run_manual_review_once(
    *,
    dependencies: LiveManualReviewDependencies | None = None,
    execute_paper_orders: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Execute one live manual-review run with injected dependencies."""
    if dependencies is not None:
        runtime = LiveManualReviewRuntime(
            dependencies=dependencies,
            now=now,
            execute_paper_orders=execute_paper_orders,
        )
        return runtime.run()

    from src.db.connection import get_session

    with get_session() as session:
        runtime = LiveManualReviewRuntime(
            dependencies=build_live_manual_review_dependencies(session),
            now=now,
            execute_paper_orders=execute_paper_orders,
        )
        return runtime.run()


def _manual_review_operational_counts(
    *,
    manual_requests: tuple[object, ...],
    decisions: tuple[object, ...],
    risk_decisions: tuple[object, ...],
    submitted_order_tickers: frozenset[str],
) -> dict[str, int]:
    risk_by_ticker = {
        str(getattr(risk, "ticker", "") or "").strip().upper(): risk
        for risk in risk_decisions
        if str(getattr(risk, "ticker", "") or "").strip()
    }
    decision_by_request_id: dict[str, object] = {}
    for decision in decisions:
        request_id = str(getattr(decision, "manual_request_id", "") or "").strip()
        if not request_id:
            continue
        decision_by_request_id[request_id] = decision

    risk_blocked_request_count = 0
    eligible_no_order_request_count = 0
    actionable_request_count = 0
    for request in manual_requests:
        request_id = str(getattr(request, "request_id", "") or "").strip()
        ticker = str(getattr(request, "ticker", "") or "").strip().upper()
        mode = str(getattr(request, "mode", "") or "").strip()
        decision = decision_by_request_id.get(request_id)
        risk = risk_by_ticker.get(ticker)
        if risk is not None and str(getattr(risk, "status", "") or "") == "rejected":
            risk_blocked_request_count += 1
            continue
        if decision is None:
            continue
        metadata_json = dict(getattr(decision, "metadata_json", {}) or {})
        action = str(
            getattr(decision, "decision", getattr(decision, "action", "")) or ""
        ).strip()
        is_actionable = bool(metadata_json.get("paper_trade_authorized", False)) and action not in {"", "hold", "no_trade"}
        if is_actionable:
            actionable_request_count += 1
        if mode == "paper_trade_eligible" and is_actionable and ticker not in submitted_order_tickers:
            eligible_no_order_request_count += 1
    return {
        "risk_blocked_request_count": risk_blocked_request_count,
        "eligible_no_order_request_count": eligible_no_order_request_count,
        "actionable_request_count": actionable_request_count,
    }
