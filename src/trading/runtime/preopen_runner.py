"""Runtime runner for the live preopen phase."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from src.trading.runtime.preopen_dependencies import LivePreopenDependencies
from src.trading.runtime.support import build_execution_report, build_runtime_report


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
