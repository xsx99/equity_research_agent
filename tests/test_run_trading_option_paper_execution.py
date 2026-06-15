from datetime import datetime, timezone

from scripts.run_trading_option_paper_execution import run_execution


class _FakeOptionBroker:
    def submit_order(self, request):
        self.last_request = request
        return type(
            "Order",
            (),
            {
                "paper_option_order_id": "paper-option-order-1",
                "broker_order_id": "alpaca-option-order-1",
                "client_order_id": "client-option-order-1",
                "ticker": request.ticker,
                "strategy_id": request.strategy_id,
                "trade_identity": request.trade_identity,
                "status": "filled",
                "quantity": request.quantity,
                "option_strategy_type": request.option_strategy_type,
                "rejection_reason": None,
            },
        )()

    def find_execution_by_order_id(self, paper_option_order_id):
        return type(
            "Execution",
            (),
            {
                "paper_option_execution_id": "exec-1",
                "paper_option_order_id": paper_option_order_id,
                "broker_order_id": "alpaca-option-order-1",
                "ticker": "AAPL",
                "quantity": 1,
                "fill_price": 2.15,
                "trade_date": datetime(2026, 6, 2, tzinfo=timezone.utc).date(),
                "executed_at": datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
                "net_cash_effect": -215.0,
            },
        )()


class _UnusedStockBroker:
    pass


def test_run_trading_option_paper_execution_outputs_broker_ids():
    result = run_execution(
        ticker="aapl",
        contract_symbol="AAPL250117C00190000",
        strategy_type="long_call",
        option_broker=_FakeOptionBroker(),
        stock_broker=_UnusedStockBroker(),
        as_of=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
    )

    assert result["status"] == "passed"
    assert result["order"]["broker_order_id"] == "alpaca-option-order-1"
    assert result["order"]["client_order_id"] == "client-option-order-1"
    assert result["execution"]["broker_order_id"] == "alpaca-option-order-1"
    assert result["positions"][0]["metadata"]["broker_leg_refs"][0]["contract_symbol"] == "AAPL250117C00190000"
