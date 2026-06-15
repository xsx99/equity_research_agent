from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from src.trading.brokers.paper_option import (
    LocalPaperOptionBroker,
    PaperOptionBroker,
    PaperOptionOrderLeg,
    PaperOptionOrderRequest,
)


class _StubResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _CapturingOptionClient:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []
        self.gets: list[dict[str, Any]] = []

    def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        self.posts.append({"url": url, "json": json, "headers": headers})
        payload = {
            "id": "alpaca-order-1",
            "client_order_id": json["client_order_id"],
            "status": "accepted",
            "submitted_at": "2026-06-02T14:00:00+00:00",
            "filled_at": "2026-06-02T14:00:02+00:00",
            "filled_qty": json["qty"],
            "filled_avg_price": str(json.get("limit_price", "2.2")),
        }
        if "symbol" in json:
            payload["symbol"] = json["symbol"]
        if "legs" in json:
            payload["legs"] = list(json["legs"])
        return _StubResponse(payload)

    def get(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str]) -> _StubResponse:
        self.gets.append({"url": url, "params": params, "headers": headers})
        return _StubResponse(
            {
                "id": "alpaca-order-1",
                "client_order_id": (params or {})["client_order_id"],
                "status": "filled",
                "submitted_at": "2026-06-02T14:00:00+00:00",
                "filled_at": "2026-06-02T14:00:02+00:00",
                "filled_qty": "1",
                "filled_avg_price": "2.2",
            }
        )


def test_local_paper_option_broker_fills_defined_risk_credit_spread():
    broker = LocalPaperOptionBroker(now=lambda: datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc))

    order = broker.submit_order(
        PaperOptionOrderRequest(
            trading_decision_id="decision-1",
            risk_decision_id="risk-1",
            option_strategy_decision_id="option-decision-1",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="put_credit_spread",
            action="open_option_strategy",
            trade_date=date(2026, 6, 2),
            quantity=1,
            limit_price=-1.5,
            max_loss=500.0,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            trade_identity="tactical_option_trade",
        )
    )
    execution = broker.find_execution_by_order_id(order.paper_option_order_id)

    assert order.status == "filled"
    assert execution is not None
    assert execution.net_cash_effect == 150.0
    assert execution.fill_price == -1.5


def test_paper_option_broker_submits_simple_long_call_to_alpaca():
    client = _CapturingOptionClient()
    broker = PaperOptionBroker(
        api_key="key",
        secret_key="secret",
        client=client,
        now=lambda: datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc),
    )

    order = broker.submit_order(
        PaperOptionOrderRequest(
            trading_decision_id="decision-1",
            risk_decision_id="risk-1",
            option_strategy_decision_id="option-decision-1",
            ticker="AAPL",
            strategy_id="strong_theme_catalyst_continuation_v1",
            option_strategy_type="long_call",
            action="open_option_strategy",
            trade_date=date(2026, 6, 2),
            quantity=1,
            limit_price=2.2,
            max_loss=220.0,
            margin_requirement=220.0,
            buying_power_effect=220.0,
            trade_identity="tactical_option_trade",
            contract_symbol="AAPL260717C00200000",
            position_intent="buy_to_open",
        )
    )

    assert client.posts[0]["url"] == "https://paper-api.alpaca.markets/v2/orders"
    assert client.posts[0]["json"] == {
        "symbol": "AAPL260717C00200000",
        "qty": "1",
        "type": "limit",
        "limit_price": "2.2",
        "time_in_force": "day",
        "client_order_id": "2026-06-02:AAPL:strong_theme_catalyst_continuation_v1:long_call:open_option_strategy",
        "position_intent": "buy_to_open",
    }
    assert client.gets[0]["url"] == "https://paper-api.alpaca.markets/v2/orders:by_client_order_id"
    assert order.status == "filled"
    assert order.broker_order_id == "alpaca-order-1"
    assert order.client_order_id == "2026-06-02:AAPL:strong_theme_catalyst_continuation_v1:long_call:open_option_strategy"


def test_paper_option_broker_submits_mleg_credit_spread():
    client = _CapturingOptionClient()
    broker = PaperOptionBroker(
        api_key="key",
        secret_key="secret",
        client=client,
        now=lambda: datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc),
    )

    order = broker.submit_order(
        PaperOptionOrderRequest(
            trading_decision_id="decision-2",
            risk_decision_id="risk-2",
            option_strategy_decision_id="option-decision-2",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="put_credit_spread",
            action="open_option_strategy",
            trade_date=date(2026, 6, 2),
            quantity=1,
            limit_price=-1.5,
            max_loss=500.0,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            trade_identity="tactical_option_trade",
            order_class="mleg",
            legs=(
                PaperOptionOrderLeg(
                    contract_symbol="NVDA260717P00105000",
                    ratio_qty=1,
                    position_intent="buy_to_open",
                ),
                PaperOptionOrderLeg(
                    contract_symbol="NVDA260717P00110000",
                    ratio_qty=1,
                    position_intent="sell_to_open",
                ),
            ),
        )
    )

    payload = client.posts[0]["json"]

    assert payload["order_class"] == "mleg"
    assert payload["qty"] == "1"
    assert payload["limit_price"] == "1.5"
    assert payload["legs"][0]["position_intent"] == "buy_to_open"
    assert payload["legs"][1]["position_intent"] == "sell_to_open"
    assert payload["legs"][0]["symbol"] == "NVDA260717P00105000"
    assert payload["legs"][1]["symbol"] == "NVDA260717P00110000"
    assert order.order_class == "mleg"
