from __future__ import annotations

from datetime import date, datetime, timezone

from src.trading.brokers.paper_option import PaperOptionBroker, PaperOptionOrderRequest


def test_paper_option_broker_fills_defined_risk_credit_spread():
    broker = PaperOptionBroker(now=lambda: datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc))

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

