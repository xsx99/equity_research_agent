from datetime import datetime, timezone

from scripts.run_trading_paper_execution import run_execution


class _FakeBroker:
    def submit_order(self, request):
        self.last_request = request
        return type(
            "Order",
            (),
            {
                "paper_order_id": "paper-order-1",
                "broker_order_id": "broker-order-1",
                "client_order_id": "client-order-1",
                "ticker": request.ticker,
                "status": "filled",
                "rejection_reason": None,
            },
        )()

    def find_execution_by_order_id(self, paper_order_id):
        return type(
            "Execution",
            (),
            {
                "paper_execution_id": "exec-1",
                "paper_order_id": paper_order_id,
                "broker_order_id": "broker-order-1",
                "ticker": "AAPL",
                "quantity": 0.01,
                "fill_price": 315.0,
                "trade_date": datetime(2026, 6, 2, tzinfo=timezone.utc).date(),
                "executed_at": datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
                "net_cash_effect": -3.15,
            },
        )()

    def sync_account(self):
        return {
            "cash": "999996.85",
            "equity": "1000000.00",
            "portfolio_value": "1000000.00",
            "buying_power": "1999996.85",
            "long_market_value": "3.15",
            "initial_margin": "1.58",
            "maintenance_margin": "0.95",
            "last_equity": "1000000.00",
        }

    def sync_positions(self):
        return [
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "avg_entry_price": "315.00",
                "current_price": "315.00",
                "market_value": "3.15",
                "side": "long",
            }
        ]


def test_run_trading_paper_execution_uses_workflow_and_returns_persisted_artifacts():
    result = run_execution(
        ticker="aapl",
        strategy_id="relative_strength_rotation_v1",
        trade_identity="tactical_stock_trade",
        decision="enter_long",
        quantity=0.01,
        broker=_FakeBroker(),
        as_of=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
    )

    assert result["status"] == "passed"
    assert result["order"]["ticker"] == "AAPL"
    assert result["order"]["status"] == "filled"
    assert result["portfolio_snapshot"]["cash_balance"] == 999996.85
    assert result["positions"][0]["ticker"] == "AAPL"
