from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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


def test_broker_portfolio_sync_workflow_persists_broker_state_and_builds_portfolio_context():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
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
            opened_at=now,
            updated_at=now,
            direction="long",
        )
    )
    workflow = BrokerPortfolioSyncWorkflow(
        repository=repository,
        broker=_BrokerStub(),
    )

    result = workflow.run(as_of=now, approved_core_tickers=("MSFT",))

    assert result.snapshot.margin_requirement_source == "broker_reported"
    assert result.positions[0].ticker == "AAPL"
    assert result.positions[0].trade_identity == "tactical_stock_trade"
    assert result.portfolio_context.buying_power == 1999995.46
    assert result.portfolio_context.margin_model_profile == "alpaca_paper_account"
    assert repository.paper_positions[0].strategy_id == "relative_strength_rotation_v1"
    assert repository.portfolio_snapshots[-1].account_equity == 1000000.12
