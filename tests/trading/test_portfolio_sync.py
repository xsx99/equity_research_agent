from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.trading.brokers.paper_option import PaperOptionPosition
from src.trading.brokers.paper_stock import PaperOrderRecord, PaperStockBroker
from src.trading.portfolio.state import StockPosition
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.workflows.portfolio_sync import BrokerPortfolioSyncWorkflow


class _BrokerStub:
    def sync_account(self) -> dict[str, Any]:
        return {
            "cash": "999997.73",
            "equity": "1000000.12",
            "portfolio_value": "1000000.12",
            "buying_power": "1999995.46",
            "long_market_value": "2.27",
            "initial_margin": "1.14",
            "maintenance_margin": "0.68",
            "last_equity": "1000000.00",
        }

    def sync_positions(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "avg_entry_price": "227.15",
                "current_price": "227.27",
                "market_value": "2.27",
                "side": "long",
            }
        ]


class _BrokerWithOptionStub:
    def sync_account(self) -> dict[str, Any]:
        return {
            "cash": "999497.73",
            "equity": "1000000.12",
            "portfolio_value": "1000000.12",
            "buying_power": "1999495.46",
            "long_market_value": "2.27",
            "options_market_value": "500.00",
            "initial_margin": "501.14",
            "maintenance_margin": "500.68",
            "last_equity": "1000000.00",
        }

    def sync_positions(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "avg_entry_price": "227.15",
                "current_price": "227.27",
                "market_value": "2.27",
                "side": "long",
                "asset_class": "us_equity",
            },
            {
                "symbol": "NVDA260717P00110000",
                "qty": "1",
                "avg_entry_price": "1.50",
                "current_price": "1.70",
                "market_value": "500.00",
                "side": "short",
                "asset_class": "option",
            },
        ]


class _LateFilledOrderClient:
    def get(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str]):
        if url.endswith("/v2/orders:by_client_order_id"):
            return _ResponseStub(
                {
                    "id": "broker-order-1",
                    "client_order_id": (params or {})["client_order_id"],
                    "symbol": "AAPL",
                    "qty": "0.01",
                    "filled_qty": "0.01",
                    "filled_avg_price": "227.15",
                    "side": "buy",
                    "status": "filled",
                    "submitted_at": "2026-06-02T16:31:00+00:00",
                    "filled_at": "2026-06-02T16:32:00+00:00",
                }
            )
        if url.endswith("/v2/account"):
            return _ResponseStub(
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
            return _ResponseStub(
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


class _ResponseStub:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


def test_broker_portfolio_sync_workflow_persists_broker_state_and_builds_portfolio_context():
    opened_at = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    synced_at = datetime(2026, 6, 3, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    repository.save_paper_position(
        StockPosition(
            ticker="AAPL",
            quantity=0.01,
            average_cost=227.15,
            market_price=227.15,
            market_value=2.2715,
            trade_identity="tactical_stock_trade",
            strategy_id="relative_strength_rotation_v1",
            opened_at=opened_at,
            updated_at=opened_at,
            direction="long",
        )
    )
    workflow = BrokerPortfolioSyncWorkflow(
        repository=repository,
        broker=_BrokerStub(),
    )

    result = workflow.run(as_of=synced_at, approved_core_tickers=("MSFT",))

    assert result.snapshot.margin_requirement_source == "broker_reported"
    assert result.positions[0].ticker == "AAPL"
    assert result.positions[0].trade_identity == "tactical_stock_trade"
    assert result.positions[0].opened_at == opened_at
    assert result.positions[0].updated_at == synced_at
    assert result.portfolio_context.buying_power == 1999995.46
    assert result.portfolio_context.margin_model_profile == "alpaca_paper_account"
    assert repository.paper_positions[0].strategy_id == "relative_strength_rotation_v1"
    assert repository.paper_positions[0].opened_at == opened_at
    assert repository.portfolio_snapshots[-1].account_equity == 1000000.12


def test_broker_portfolio_sync_workflow_reconciles_late_filled_stock_orders():
    submitted_at = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    synced_at = datetime(2026, 6, 2, 16, 33, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    repository.save_paper_order(
        PaperOrderRecord(
            paper_order_id="paper-order-1",
            broker_order_id="broker-order-1",
            client_order_id="2026-06-02:AAPL:relative_strength_rotation_v1:enter_long",
            trading_decision_id="11111111-1111-4111-8111-111111111111",
            risk_decision_id="22222222-2222-4222-8222-222222222222",
            ticker="AAPL",
            strategy_id="relative_strength_rotation_v1",
            action="enter_long",
            trade_date=submitted_at.date(),
            quantity=0.01,
            limit_price=None,
            status="accepted",
            rejection_reason=None,
            created_at=submitted_at,
        )
    )
    workflow = BrokerPortfolioSyncWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_LateFilledOrderClient()),
    )

    workflow.run(as_of=synced_at)

    assert repository.paper_orders[0].status == "filled"
    assert len(repository.paper_executions) == 1
    assert repository.paper_executions[0].paper_order_id == "paper-order-1"
    assert repository.paper_positions[0].strategy_id == "relative_strength_rotation_v1"


def test_broker_portfolio_sync_workflow_uses_broker_option_positions_without_local_overlay():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="option-position-1",
            option_strategy_decision_id="option-decision-1",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="put_credit_spread",
            trade_identity="tactical_option_trade",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=now.date(),
            max_loss=500.0,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            assignment_notional=11_000.0,
            metadata_json={
                "broker_leg_refs": [
                    {
                        "contract_symbol": "NVDA260717P00110000",
                        "ratio_qty": 1,
                        "position_intent": "sell_to_open",
                    }
                ]
            },
        )
    )
    workflow = BrokerPortfolioSyncWorkflow(
        repository=repository,
        broker=_BrokerWithOptionStub(),
    )

    result = workflow.run(as_of=now, approved_core_tickers=("MSFT",))

    assert result.snapshot.option_market_value == 500.0
    assert result.snapshot.option_margin_requirement == 500.0
    assert result.snapshot.total_margin_requirement == 501.14
    assert result.snapshot.buying_power == 1999495.46
    assert result.snapshot.excess_liquidity == 999499.44
    assert result.snapshot.margin_requirement_source == "broker_reported"
    assert result.snapshot.metadata_json.get("option_overlay_source") != "local_simulation"
    assert result.portfolio_context.option_margin_requirement == 500.0
    assert result.portfolio_context.buying_power == 1999495.46
    assert any(position.ticker == "NVDA" and position.assignment_notional == 11_000.0 for position in result.portfolio_context.positions)


def test_broker_portfolio_sync_workflow_persists_broker_option_positions_without_local_overlay():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    workflow = BrokerPortfolioSyncWorkflow(
        repository=repository,
        broker=_BrokerWithOptionStub(),
    )

    workflow.run(as_of=now)
    workflow.run(as_of=now)

    option_positions = repository.load_paper_option_positions()
    assert len(option_positions) == 1
    position = option_positions[0]
    assert position.ticker == "NVDA"
    assert position.option_strategy_type == "broker_option_position"
    assert position.trade_identity == "tactical_option_trade"
    assert position.quantity == 1
    assert position.status == "open"
    assert position.metadata_json["broker_leg_refs"] == [
        {
            "contract_symbol": "NVDA260717P00110000",
            "position_intent": "broker_position",
        }
    ]


def test_broker_portfolio_sync_workflow_reconciles_missing_broker_option_positions():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="option-position-1",
            option_strategy_decision_id="option-decision-1",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="put_credit_spread",
            trade_identity="tactical_option_trade",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=now.date(),
            max_loss=500.0,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            assignment_notional=11_000.0,
            metadata_json={
                "broker_leg_refs": [
                    {
                        "contract_symbol": "NVDA260717P00110000",
                        "ratio_qty": 1,
                        "position_intent": "sell_to_open",
                    }
                ]
            },
        )
    )
    workflow = BrokerPortfolioSyncWorkflow(
        repository=repository,
        broker=_BrokerStub(),
    )

    result = workflow.run(as_of=now, approved_core_tickers=("MSFT",))
    reconciled = next(position for position in repository.paper_option_positions if position.paper_option_position_id == "option-position-1")

    assert result.snapshot.option_market_value == 0.0
    assert reconciled.status == "closed"
    assert reconciled.metadata_json["reconciliation_status"] == "broker_position_missing"
