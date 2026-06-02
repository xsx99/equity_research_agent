from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.brokers.paper_stock import PaperOrderRequest, PaperStockBroker
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.risk import RiskDecisionRecord
from src.trading.workflows.paper_execution import PaperExecutionWorkflow
from src.trading.workflows.trading_decision import TradingDecisionRecord


class _StubResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _CapturingClient:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []
        self.gets: list[dict[str, Any]] = []

    def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        self.posts.append({"url": url, "json": json, "headers": headers})
        return _StubResponse(
            {
                "id": "broker-order-1",
                "client_order_id": json["client_order_id"],
                "symbol": json["symbol"],
                "qty": json["qty"],
                "side": json["side"],
                "type": json["type"],
                "time_in_force": json["time_in_force"],
                "status": "accepted",
                "submitted_at": "2026-06-02T16:31:00+00:00",
            }
        )

    def get(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str]) -> _StubResponse:
        self.gets.append({"url": url, "params": params, "headers": headers})
        if url.endswith("/v2/orders:by_client_order_id"):
            client_order_id = (params or {})["client_order_id"]
            return _StubResponse(
                {
                    "id": "broker-order-1",
                    "client_order_id": client_order_id,
                    "symbol": "AAPL",
                    "qty": "0.01",
                    "filled_qty": "0.01",
                    "filled_avg_price": "227.15",
                    "side": "buy",
                    "type": "market",
                    "time_in_force": "day",
                    "status": "filled",
                    "submitted_at": "2026-06-02T16:31:00+00:00",
                    "filled_at": "2026-06-02T16:31:02+00:00",
                }
            )
        if url.endswith("/v2/account"):
            return _StubResponse(
                {
                    "cash": "999997.73",
                    "equity": "1000000.12",
                    "portfolio_value": "1000000.12",
                    "buying_power": "1999995.46",
                    "long_market_value": "2.27",
                    "initial_margin": "1.14",
                    "maintenance_margin": "0.68",
                    "last_equity": "1000000.00",
                }
            )
        if url.endswith("/v2/positions"):
            return _StubResponse(
                [
                    {
                        "symbol": "AAPL",
                        "qty": "0.01",
                        "avg_entry_price": "227.15",
                        "current_price": "227.27",
                        "market_value": "2.27",
                        "side": "long",
                    }
                ]
            )
        raise AssertionError(f"unexpected_get:{url}")


def _trading_decision(*, decision: str = "enter_long", manual_request_id: str | None = None) -> TradingDecisionRecord:
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    return TradingDecisionRecord(
        trading_decision_id="decision-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        risk_decision_id="risk-1",
        ticker="AAPL",
        decision=decision,
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        selection_source="manual_request" if manual_request_id else "scanner",
        manual_request_id=manual_request_id,
        confidence=0.78,
        target_weight=0.05,
        approved_weight=0.04,
        max_loss_pct=0.02,
        time_horizon="2w-3m",
        thesis="Relative strength remains intact.",
        invalidators=["trend break"],
        prompt_template=object(),
        prompt_run=object(),
        usage_events=[],
        decision_time=now,
        available_for_decision_at=now,
        metadata_json={"paper_trade_authorized": True},
    )


def _risk_decision(*, approved_quantity: float = 0.01, status: str = "approved") -> RiskDecisionRecord:
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    return RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="AAPL",
        status=status,
        reason_code="within_limits",
        approved_weight=0.000002,
        approved_notional=2.27,
        approved_quantity=approved_quantity,
        portfolio_risk_snapshot_id="portfolio-risk-1",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )


def test_paper_stock_broker_rejects_review_only_manual_request_without_hitting_broker():
    client = _CapturingClient()
    broker = PaperStockBroker(api_key="key", secret_key="secret", client=client)
    decision = _trading_decision(manual_request_id="manual-1")
    risk = _risk_decision()

    order = broker.submit_order(
        PaperOrderRequest.from_trading_decision(
            trading_decision=decision,
            risk_decision=risk,
            trade_date=decision.decision_time.date(),
            manual_request_mode="review_only",
        )
    )

    assert order.status == "rejected"
    assert order.rejection_reason == "manual_request_review_only"
    assert client.posts == []


def test_paper_stock_broker_submits_alpaca_market_day_order_and_reads_fill_by_client_order_id():
    client = _CapturingClient()
    broker = PaperStockBroker(api_key="key", secret_key="secret", client=client)
    decision = _trading_decision()
    risk = _risk_decision()

    order = broker.submit_order(
        PaperOrderRequest.from_trading_decision(
            trading_decision=decision,
            risk_decision=risk,
            trade_date=decision.decision_time.date(),
            manual_request_mode=None,
        )
    )
    execution = broker.find_execution_by_order_id(order.paper_order_id)

    assert client.posts[0]["url"] == "https://paper-api.alpaca.markets/v2/orders"
    assert client.posts[0]["json"] == {
        "symbol": "AAPL",
        "qty": "0.01",
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
        "client_order_id": "2026-06-02:AAPL:relative_strength_rotation_v1:enter_long",
    }
    assert client.gets[0]["url"] == "https://paper-api.alpaca.markets/v2/orders:by_client_order_id"
    assert client.gets[0]["params"] == {
        "client_order_id": "2026-06-02:AAPL:relative_strength_rotation_v1:enter_long"
    }
    assert order.status == "filled"
    assert order.broker_order_id == "broker-order-1"
    assert execution is not None
    assert execution.fill_price == 227.15
    assert execution.quantity == 0.01


def test_paper_stock_broker_submits_sell_order_for_exit_action():
    client = _CapturingClient()
    broker = PaperStockBroker(api_key="key", secret_key="secret", client=client)
    decision = _trading_decision(decision="exit")
    risk = _risk_decision()

    order = broker.submit_order(
        PaperOrderRequest.from_trading_decision(
            trading_decision=decision,
            risk_decision=risk,
            trade_date=decision.decision_time.date(),
            manual_request_mode=None,
        )
    )

    assert client.posts[0]["json"]["side"] == "sell"
    assert order.status == "filled"


def test_paper_execution_workflow_persists_broker_sourced_order_account_and_positions():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    result = workflow.run(
        trading_decisions=(_trading_decision(),),
        risk_decisions=(_risk_decision(),),
        trade_date=now,
    )

    assert len(result.paper_orders) == 1
    assert len(repository.paper_orders) == 1
    assert len(repository.paper_executions) == 1
    assert repository.paper_positions[0].ticker == "AAPL"
    assert repository.paper_positions[0].quantity == 0.01
    assert result.portfolio_snapshots[-1].cash_balance == 999997.73
    assert result.portfolio_snapshots[-1].buying_power == 1999995.46
