"""PR06 Alpaca-backed paper stock execution workflow."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.paper_stock_broker import PaperOrderRequest, PaperOrderRecord, PaperStockBroker
from src.trading.portfolio.state import (
    PortfolioSnapshot,
    build_portfolio_snapshot_from_account,
    build_positions_from_broker,
)
from src.trading.risk import RiskDecisionRecord
from src.trading.workflows.trading_decision import TradingDecisionRecord


@dataclass(frozen=True)
class PaperExecutionWorkflowResult:
    """Persisted artifacts produced by the PR06 stock paper broker path."""

    paper_orders: tuple[PaperOrderRecord, ...]
    portfolio_snapshots: tuple[PortfolioSnapshot, ...]


class PaperExecutionWorkflow:
    """Execute stock paper trades from validated PR05 decisions."""

    def __init__(
        self,
        *,
        repository: Any,
        broker: PaperStockBroker,
        manual_request_service: ManualTickerRequestService | None = None,
    ) -> None:
        self.repository = repository
        self.broker = broker
        self.manual_request_service = manual_request_service

    def run(
        self,
        *,
        trading_decisions: tuple[TradingDecisionRecord, ...],
        risk_decisions: tuple[RiskDecisionRecord, ...],
        trade_date: datetime,
    ) -> PaperExecutionWorkflowResult:
        risk_by_id = {decision.risk_decision_id: decision for decision in risk_decisions}
        orders: list[PaperOrderRecord] = []
        snapshots: list[PortfolioSnapshot] = []
        for trading_decision in trading_decisions:
            if trading_decision.instrument_type != "stock":
                continue
            if trading_decision.decision not in {"enter_long", "reduce", "exit", "enter_short"}:
                continue
            if not bool(trading_decision.metadata_json.get("paper_trade_authorized", False)) and trading_decision.manual_request_id is None:
                continue
            risk_decision = risk_by_id.get(trading_decision.risk_decision_id)
            if risk_decision is None:
                continue
            manual_request_mode = self._manual_request_mode(trading_decision.manual_request_id)
            order = self.broker.submit_order(
                PaperOrderRequest.from_trading_decision(
                    trading_decision=trading_decision,
                    risk_decision=risk_decision,
                    trade_date=trade_date.date(),
                    manual_request_mode=manual_request_mode,
                )
            )
            self.repository.save_paper_order(order)
            orders.append(order)
            execution = self.broker.find_execution_by_order_id(order.paper_order_id)
            if execution is None:
                continue
            if self.repository.has_paper_execution(execution.paper_execution_id):
                continue
            self.repository.save_paper_execution(execution)
            account_payload = self.broker.sync_account()
            broker_positions = self.broker.sync_positions()
            local_position_metadata = {
                position.ticker: {
                    "strategy_id": position.strategy_id,
                    "trade_identity": position.trade_identity,
                }
                for position in self.repository.paper_positions
            }
            local_position_metadata[trading_decision.ticker] = {
                "strategy_id": trading_decision.strategy_id,
                "trade_identity": trading_decision.trade_identity,
            }
            synced_positions = build_positions_from_broker(
                broker_positions=broker_positions,
                as_of=execution.executed_at,
                local_position_metadata=local_position_metadata,
            )
            self.repository.replace_paper_positions(synced_positions)
            snapshot = build_portfolio_snapshot_from_account(
                account_payload,
                as_of=execution.executed_at,
            )
            self.repository.save_portfolio_snapshot(snapshot)
            snapshots.append(snapshot)
        return PaperExecutionWorkflowResult(
            paper_orders=tuple(orders),
            portfolio_snapshots=tuple(snapshots),
        )

    def _manual_request_mode(self, request_id: str | None) -> str | None:
        if request_id is None or self.manual_request_service is None:
            return None
        for request in self.manual_request_service.load_active():
            if request.request_id == request_id:
                return request.mode
        return None
