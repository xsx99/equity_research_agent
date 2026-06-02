"""Paper-only option execution simulator for PR7."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable


_SUPPORTED_ACTIONS = {
    "open_option_strategy",
    "close_option_strategy",
    "roll_option_strategy",
    "adjust_option_strategy",
    "avoid_event_option",
}


@dataclass(frozen=True)
class PaperOptionOrderRequest:
    trading_decision_id: str
    risk_decision_id: str
    option_strategy_decision_id: str
    ticker: str
    strategy_id: str
    option_strategy_type: str
    action: str
    trade_date: date
    quantity: int
    limit_price: float
    max_loss: float
    margin_requirement: float
    buying_power_effect: float
    trade_identity: str


@dataclass(frozen=True)
class PaperOptionOrderRecord:
    paper_option_order_id: str
    trading_decision_id: str
    risk_decision_id: str
    option_strategy_decision_id: str
    ticker: str
    strategy_id: str
    option_strategy_type: str
    action: str
    trade_identity: str
    trade_date: date
    quantity: int
    limit_price: float
    status: str
    rejection_reason: str | None
    margin_requirement: float
    buying_power_effect: float
    created_at: datetime


@dataclass(frozen=True)
class PaperOptionExecutionRecord:
    paper_option_execution_id: str
    paper_option_order_id: str
    ticker: str
    quantity: int
    fill_price: float
    trade_date: date
    executed_at: datetime
    net_cash_effect: float


@dataclass(frozen=True)
class PaperOptionPosition:
    paper_option_position_id: str
    option_strategy_decision_id: str
    ticker: str
    strategy_id: str
    option_strategy_type: str
    trade_identity: str
    quantity: int
    opened_at: datetime
    updated_at: datetime
    status: str
    expiry: date
    max_loss: float
    margin_requirement: float
    buying_power_effect: float
    assignment_notional: float
    metadata_json: dict[str, Any] = field(default_factory=dict)


class PaperOptionBroker:
    """Paper-only local option fill simulator for whitelisted structures."""

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.orders: list[PaperOptionOrderRecord] = []
        self.executions: list[PaperOptionExecutionRecord] = []
        self._orders_by_key: dict[str, PaperOptionOrderRecord] = {}
        self._executions_by_order_id: dict[str, PaperOptionExecutionRecord] = {}

    def submit_order(self, request: PaperOptionOrderRequest) -> PaperOptionOrderRecord:
        key = self._idempotency_key(request)
        existing = self._orders_by_key.get(key)
        if existing is not None:
            return existing

        rejection_reason = self._rejection_reason(request)
        status = "rejected" if rejection_reason else "filled"
        now = self._now()
        order = PaperOptionOrderRecord(
            paper_option_order_id=str(uuid.uuid4()),
            trading_decision_id=request.trading_decision_id,
            risk_decision_id=request.risk_decision_id,
            option_strategy_decision_id=request.option_strategy_decision_id,
            ticker=request.ticker,
            strategy_id=request.strategy_id,
            option_strategy_type=request.option_strategy_type,
            action=request.action,
            trade_identity=request.trade_identity,
            trade_date=request.trade_date,
            quantity=request.quantity,
            limit_price=request.limit_price,
            status=status,
            rejection_reason=rejection_reason,
            margin_requirement=request.margin_requirement,
            buying_power_effect=request.buying_power_effect,
            created_at=now,
        )
        self.orders.append(order)
        self._orders_by_key[key] = order
        if rejection_reason is None:
            execution = PaperOptionExecutionRecord(
                paper_option_execution_id=str(uuid.uuid4()),
                paper_option_order_id=order.paper_option_order_id,
                ticker=order.ticker,
                quantity=order.quantity,
                fill_price=order.limit_price,
                trade_date=order.trade_date,
                executed_at=now,
                net_cash_effect=-(order.limit_price * 100.0 * order.quantity),
            )
            self.executions.append(execution)
            self._executions_by_order_id[order.paper_option_order_id] = execution
        return order

    def find_execution_by_order_id(self, paper_option_order_id: str) -> PaperOptionExecutionRecord | None:
        return self._executions_by_order_id.get(paper_option_order_id)

    def _idempotency_key(self, request: PaperOptionOrderRequest) -> str:
        return ":".join(
            [
                request.trade_date.isoformat(),
                request.ticker,
                request.strategy_id,
                request.option_strategy_type,
                request.action,
            ]
        )

    def _rejection_reason(self, request: PaperOptionOrderRequest) -> str | None:
        if request.action not in _SUPPORTED_ACTIONS:
            return "unsupported_option_action"
        if request.quantity <= 0:
            return "non_positive_quantity"
        if request.action == "avoid_event_option":
            return "event_risk_blocked"
        return None
