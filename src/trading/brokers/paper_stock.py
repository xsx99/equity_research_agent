"""Alpaca-backed paper stock broker for PR06."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

import httpx

from src.trading.risk import RiskDecisionRecord

if TYPE_CHECKING:
    from src.trading.workflows.trading_decision import TradingDecisionRecord

DEFAULT_ALPACA_PAPER_TRADING_BASE_URL = "https://paper-api.alpaca.markets"
_TERMINAL_ORDER_STATUSES = {"filled", "canceled", "expired", "rejected"}


@dataclass(frozen=True)
class PaperOrderRequest:
    """Order request derived from a validated trading decision and final risk approval."""

    trading_decision_id: str
    risk_decision_id: str
    ticker: str
    strategy_id: str
    action: str
    trade_date: date
    quantity: float
    manual_request_mode: str | None

    @classmethod
    def from_trading_decision(
        cls,
        *,
        trading_decision: TradingDecisionRecord,
        risk_decision: RiskDecisionRecord,
        trade_date: date,
        manual_request_mode: str | None,
    ) -> "PaperOrderRequest":
        return cls(
            trading_decision_id=trading_decision.trading_decision_id,
            risk_decision_id=risk_decision.risk_decision_id,
            ticker=trading_decision.ticker,
            strategy_id=trading_decision.strategy_id,
            action=trading_decision.decision,
            trade_date=trade_date,
            quantity=float(risk_decision.approved_quantity),
            manual_request_mode=manual_request_mode,
        )


@dataclass(frozen=True)
class PaperOrderRecord:
    """Persistable paper order keyed by the client order ID sent to Alpaca."""

    paper_order_id: str
    broker_order_id: str | None
    client_order_id: str
    trading_decision_id: str
    risk_decision_id: str
    ticker: str
    strategy_id: str
    action: str
    trade_date: date
    quantity: float
    limit_price: float | None
    status: str
    rejection_reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class PaperExecutionRecord:
    """Persisted paper fill from the broker-reported order state."""

    paper_execution_id: str
    paper_order_id: str
    broker_order_id: str | None
    ticker: str
    quantity: float
    fill_price: float
    trade_date: date
    executed_at: datetime
    net_cash_effect: float


class PaperStockBroker:
    """Alpaca paper trading broker with local guardrails and audit artifacts."""

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
        self.orders: list[PaperOrderRecord] = []
        self.executions: list[PaperExecutionRecord] = []
        self._orders_by_key: dict[str, PaperOrderRecord] = {}
        self._executions_by_order_id: dict[str, PaperExecutionRecord] = {}

    def close(self) -> None:
        if self._owns_client and hasattr(self._client, "close"):
            self._client.close()

    def submit_order(self, request: PaperOrderRequest) -> PaperOrderRecord:
        key = self._idempotency_key(request)
        existing = self._orders_by_key.get(key)
        if existing is not None:
            return existing

        rejection_reason = self._rejection_reason(request)
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
            json={
                "symbol": request.ticker,
                "qty": self._format_quantity(request.quantity),
                "side": self._side_for_action(request.action),
                "type": "market",
                "time_in_force": "day",
                "client_order_id": key,
            },
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        order_payload = response.json()
        latest_payload = self._poll_until_terminal(client_order_id=key, initial_payload=order_payload)
        order = self._store_local_order(
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
        return order

    def find_execution_by_order_id(self, paper_order_id: str) -> PaperExecutionRecord | None:
        return self._executions_by_order_id.get(paper_order_id)

    def sync_account(self) -> dict[str, Any]:
        response = self._client.get(
            f"{self.trading_base_url}/v2/account",
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("unexpected_alpaca_account_payload")
        return payload

    def sync_positions(self) -> list[dict[str, Any]]:
        response = self._client.get(
            f"{self.trading_base_url}/v2/positions",
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("unexpected_alpaca_positions_payload")
        return [item for item in payload if isinstance(item, dict)]

    def submit_fractional_market_buy(self, *, ticker: str, qty: float, strategy_id: str) -> dict[str, Any]:
        request = PaperOrderRequest(
            trading_decision_id="smoke-trading-decision",
            risk_decision_id="smoke-risk-decision",
            ticker=ticker.upper(),
            strategy_id=strategy_id,
            action="enter_long",
            trade_date=self._now().date(),
            quantity=qty,
            manual_request_mode=None,
        )
        order = self.submit_order(request)
        execution = self.find_execution_by_order_id(order.paper_order_id)
        account = self.sync_account()
        positions = self.sync_positions()
        return {
            "order": order,
            "execution": execution,
            "account": account,
            "positions": positions,
        }

    def _store_local_order(
        self,
        *,
        request: PaperOrderRequest,
        client_order_id: str,
        broker_order_id: str | None,
        status: str,
        rejection_reason: str | None,
        filled_avg_price: float | None,
        filled_qty: float | None,
        submitted_at: datetime,
        filled_at: datetime | None,
    ) -> PaperOrderRecord:
        order = PaperOrderRecord(
            paper_order_id=str(uuid.uuid4()),
            broker_order_id=broker_order_id,
            client_order_id=client_order_id,
            trading_decision_id=request.trading_decision_id,
            risk_decision_id=request.risk_decision_id,
            ticker=request.ticker,
            strategy_id=request.strategy_id,
            action=request.action,
            trade_date=request.trade_date,
            quantity=request.quantity,
            limit_price=filled_avg_price,
            status=status,
            rejection_reason=rejection_reason,
            created_at=submitted_at,
        )
        self.orders.append(order)
        self._orders_by_key[client_order_id] = order
        if status == "filled" and filled_qty not in (None, 0) and filled_avg_price not in (None, 0):
            execution = PaperExecutionRecord(
                paper_execution_id=str(uuid.uuid4()),
                paper_order_id=order.paper_order_id,
                broker_order_id=broker_order_id,
                ticker=order.ticker,
                quantity=float(filled_qty),
                fill_price=float(filled_avg_price),
                trade_date=order.trade_date,
                executed_at=filled_at or submitted_at,
                net_cash_effect=-float(filled_qty) * float(filled_avg_price),
            )
            self.executions.append(execution)
            self._executions_by_order_id[order.paper_order_id] = execution
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

    def _rejection_reason(self, request: PaperOrderRequest) -> str | None:
        if request.manual_request_mode == "review_only":
            return "manual_request_review_only"
        if request.action == "enter_short":
            return "long_only_common_stock_v2"
        if request.action not in {"enter_long", "reduce", "exit"}:
            return "unsupported_stock_action"
        if request.quantity <= 0:
            return "non_positive_quantity"
        return None

    def _idempotency_key(self, request: PaperOrderRequest) -> str:
        return f"{request.trade_date.isoformat()}:{request.ticker}:{request.strategy_id}:{request.action}"

    def _side_for_action(self, action: str) -> str:
        if action == "enter_long":
            return "buy"
        if action in {"reduce", "exit"}:
            return "sell"
        raise ValueError(f"unsupported_stock_action:{action}")

    def _format_quantity(self, quantity: float) -> str:
        return f"{quantity:.8f}".rstrip("0").rstrip(".")


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
