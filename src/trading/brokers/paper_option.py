"""Option paper broker with Alpaca-backed and local-simulation modes."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable

import httpx


DEFAULT_ALPACA_PAPER_TRADING_BASE_URL = "https://paper-api.alpaca.markets"
_TERMINAL_ORDER_STATUSES = {"filled", "canceled", "expired", "rejected"}
_SUPPORTED_ACTIONS = {
    "open_option_strategy",
    "close_option_strategy",
    "roll_option_strategy",
    "adjust_option_strategy",
    "avoid_event_option",
}


@dataclass(frozen=True)
class PaperOptionOrderLeg:
    contract_symbol: str
    ratio_qty: int = 1
    position_intent: str | None = None


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
    contract_symbol: str | None = None
    position_intent: str | None = None
    order_class: str = "simple"
    legs: tuple[PaperOptionOrderLeg, ...] = ()


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
    broker_order_id: str | None = None
    client_order_id: str | None = None
    order_class: str = "simple"


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
    broker_order_id: str | None = None


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


class LocalPaperOptionBroker:
    """Local immediate-fill helper for tests and offline option paths."""

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.orders: list[PaperOptionOrderRecord] = []
        self.executions: list[PaperOptionExecutionRecord] = []
        self._orders_by_key: dict[str, PaperOptionOrderRecord] = {}
        self._executions_by_order_id: dict[str, PaperOptionExecutionRecord] = {}

    def submit_order(self, request: PaperOptionOrderRequest) -> PaperOptionOrderRecord:
        key = _idempotency_key(request)
        existing = self._orders_by_key.get(key)
        if existing is not None:
            return existing

        rejection_reason = _rejection_reason(request)
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
            client_order_id=key,
            order_class=request.order_class,
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
                broker_order_id=order.broker_order_id,
            )
            self.executions.append(execution)
            self._executions_by_order_id[order.paper_option_order_id] = execution
        return order

    def find_execution_by_order_id(self, paper_option_order_id: str) -> PaperOptionExecutionRecord | None:
        return self._executions_by_order_id.get(paper_option_order_id)


class PaperOptionBroker:
    """Option broker that uses Alpaca when configured, otherwise local simulation."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        secret_key: str | None = None,
        trading_base_url: str | None = None,
        client: httpx.Client | Any | None = None,
        now: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        max_poll_attempts: int = 5,
        poll_interval_seconds: float = 0.0,
    ) -> None:
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")
        self.trading_base_url = (
            trading_base_url or os.getenv("ALPACA_TRADING_BASE_URL") or DEFAULT_ALPACA_PAPER_TRADING_BASE_URL
        ).rstrip("/")
        self._client = client or httpx.Client(timeout=10.0)
        self._owns_client = client is None
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._sleeper = sleeper or (lambda seconds: None)
        self._max_poll_attempts = max_poll_attempts
        self._poll_interval_seconds = poll_interval_seconds
        use_broker = any(
            value is not None
            for value in (
                api_key,
                secret_key,
                client,
                trading_base_url,
            )
        )
        self._local = None if use_broker else LocalPaperOptionBroker(now=self._now)
        self.orders = [] if self._local is None else self._local.orders
        self.executions = [] if self._local is None else self._local.executions
        self._orders_by_key: dict[str, PaperOptionOrderRecord] = {} if self._local is None else self._local._orders_by_key
        self._executions_by_order_id: dict[str, PaperOptionExecutionRecord] = (
            {} if self._local is None else self._local._executions_by_order_id
        )

    def close(self) -> None:
        if self._local is not None:
            return
        if self._owns_client and hasattr(self._client, "close"):
            self._client.close()

    def submit_order(self, request: PaperOptionOrderRequest) -> PaperOptionOrderRecord:
        if self._local is not None:
            return self._local.submit_order(request)

        key = _idempotency_key(request)
        existing = self._orders_by_key.get(key)
        if existing is not None:
            return existing

        rejection_reason = _rejection_reason(request)
        if rejection_reason is not None:
            return self._store_local_order(
                request=request,
                client_order_id=key,
                broker_order_id=None,
                status="rejected",
                rejection_reason=rejection_reason,
                filled_avg_price=None,
                filled_qty=None,
                submitted_at=self._now(),
                filled_at=None,
            )

        response = self._client.post(
            f"{self.trading_base_url}/v2/orders",
            json=_alpaca_order_payload(request, client_order_id=key),
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        latest_payload = self._poll_until_terminal(client_order_id=key, initial_payload=response.json())
        return self._store_local_order(
            request=request,
            client_order_id=key,
            broker_order_id=_string_or_none(latest_payload.get("id")),
            status=str(latest_payload.get("status", "accepted")),
            rejection_reason=_string_or_none(latest_payload.get("reject_reason")),
            filled_avg_price=_float_or_none(latest_payload.get("filled_avg_price")),
            filled_qty=_float_or_none(latest_payload.get("filled_qty")),
            submitted_at=_datetime_or_now(latest_payload.get("submitted_at"), fallback=self._now()),
            filled_at=_datetime_or_none(latest_payload.get("filled_at")),
        )

    def find_execution_by_order_id(self, paper_option_order_id: str) -> PaperOptionExecutionRecord | None:
        if self._local is not None:
            return self._local.find_execution_by_order_id(paper_option_order_id)
        return self._executions_by_order_id.get(paper_option_order_id)

    def _store_local_order(
        self,
        *,
        request: PaperOptionOrderRequest,
        client_order_id: str,
        broker_order_id: str | None,
        status: str,
        rejection_reason: str | None,
        filled_avg_price: float | None,
        filled_qty: float | None,
        submitted_at: datetime,
        filled_at: datetime | None,
    ) -> PaperOptionOrderRecord:
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
            created_at=submitted_at,
            broker_order_id=broker_order_id,
            client_order_id=client_order_id,
            order_class=request.order_class,
        )
        self.orders.append(order)
        self._orders_by_key[client_order_id] = order
        if status == "filled" and filled_qty not in (None, 0) and filled_avg_price not in (None, 0):
            signed_fill_price = _signed_fill_price(request, float(filled_avg_price))
            execution = PaperOptionExecutionRecord(
                paper_option_execution_id=str(uuid.uuid4()),
                paper_option_order_id=order.paper_option_order_id,
                broker_order_id=broker_order_id,
                ticker=order.ticker,
                quantity=int(round(float(filled_qty))),
                fill_price=signed_fill_price,
                trade_date=order.trade_date,
                executed_at=filled_at or submitted_at,
                net_cash_effect=-(int(round(float(filled_qty))) * signed_fill_price * 100.0),
            )
            self.executions.append(execution)
            self._executions_by_order_id[order.paper_option_order_id] = execution
        return order

    def _poll_until_terminal(self, *, client_order_id: str, initial_payload: dict[str, Any]) -> dict[str, Any]:
        latest = initial_payload
        status = str(initial_payload.get("status", ""))
        attempts = 0
        while status not in _TERMINAL_ORDER_STATUSES and attempts < self._max_poll_attempts:
            if attempts > 0 or self._poll_interval_seconds > 0:
                self._sleeper(self._poll_interval_seconds)
            response = self._client.get(
                f"{self.trading_base_url}/v2/orders:by_client_order_id",
                params={"client_order_id": client_order_id},
                headers=self._auth_headers(),
            )
            response.raise_for_status()
            latest = response.json()
            status = str(latest.get("status", ""))
            attempts += 1
        return latest

    def _auth_headers(self) -> dict[str, str]:
        if not self.api_key or not self.secret_key:
            raise RuntimeError("missing_alpaca_credentials")
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }


def _alpaca_order_payload(request: PaperOptionOrderRequest, *, client_order_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "qty": _format_int_quantity(request.quantity),
        "type": "limit",
        "limit_price": _format_limit_price(request.limit_price),
        "time_in_force": "day",
        "client_order_id": client_order_id,
    }
    if request.order_class == "mleg":
        if not request.legs:
            raise ValueError("missing_option_legs_for_mleg_order")
        payload["order_class"] = "mleg"
        payload["legs"] = [
            {
                "symbol": leg.contract_symbol,
                "ratio_qty": str(leg.ratio_qty),
                "position_intent": leg.position_intent or "buy_to_open",
            }
            for leg in request.legs
        ]
        return payload
    contract_symbol = request.contract_symbol
    if not contract_symbol:
        raise ValueError("missing_option_contract_symbol")
    payload["symbol"] = contract_symbol
    payload["position_intent"] = request.position_intent or _default_position_intent(request)
    return payload


def _default_position_intent(request: PaperOptionOrderRequest) -> str:
    if request.action == "open_option_strategy":
        return "buy_to_open"
    if request.action == "close_option_strategy":
        return "sell_to_close"
    raise ValueError(f"missing_position_intent_for_action:{request.action}")


def _signed_fill_price(request: PaperOptionOrderRequest, filled_avg_price: float) -> float:
    if request.limit_price < 0:
        return -abs(filled_avg_price)
    return abs(filled_avg_price)


def _idempotency_key(request: PaperOptionOrderRequest) -> str:
    return ":".join(
        [
            request.trade_date.isoformat(),
            request.ticker,
            request.strategy_id,
            request.option_strategy_type,
            request.action,
        ]
    )


def _rejection_reason(request: PaperOptionOrderRequest) -> str | None:
    if request.action not in _SUPPORTED_ACTIONS:
        return "unsupported_option_action"
    if request.quantity <= 0:
        return "non_positive_quantity"
    if request.action == "avoid_event_option":
        return "event_risk_blocked"
    return None


def _format_int_quantity(quantity: int) -> str:
    return str(max(1, int(quantity)))


def _format_limit_price(limit_price: float) -> str:
    return f"{abs(limit_price):.8f}".rstrip("0").rstrip(".")


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _datetime_or_none(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _datetime_or_now(value: Any, *, fallback: datetime) -> datetime:
    return _datetime_or_none(value) or fallback
