from datetime import datetime, timezone

from scripts.run_trading_paper_order_smoke import run_smoke


class _FakeBroker:
    def submit_fractional_market_buy(self, *, ticker: str, qty: float, strategy_id: str):
        return {
            "order": {
                "ticker": ticker,
                "status": "filled",
                "broker_order_id": "broker-order-1",
                "client_order_id": "client-order-1",
            },
            "execution": {
                "fill_price": 227.15,
                "quantity": qty,
                "executed_at": "2026-06-02T16:31:02+00:00",
            },
            "account": {
                "cash": 999997.73,
                "buying_power": 1999995.46,
                "equity": 1000000.12,
            },
            "positions": [{"ticker": ticker, "quantity": qty}],
        }


def test_run_trading_paper_order_smoke_uses_broker_without_network():
    result = run_smoke(
        ticker="aapl",
        qty=0.01,
        strategy_id="smoke_test_v1",
        broker=_FakeBroker(),
        as_of=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
    )

    assert result["status"] == "passed"
    assert result["ticker"] == "AAPL"
    assert result["qty"] == 0.01
    assert result["order"]["status"] == "filled"
    assert result["account"]["buying_power"] == 1999995.46
    assert result["positions"][0]["ticker"] == "AAPL"
