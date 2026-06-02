"""Broker-backed portfolio sync workflow for live PR6 account state."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.trading.portfolio.state import (
    PortfolioSnapshot,
    StockPosition,
    build_portfolio_context,
    build_portfolio_snapshot_from_account,
    build_positions_from_broker,
)
from src.trading.risk import PortfolioContext


@dataclass(frozen=True)
class BrokerPortfolioSyncResult:
    """Broker-sourced portfolio state plus the derived PR04 portfolio context."""

    snapshot: PortfolioSnapshot
    positions: tuple[StockPosition, ...]
    portfolio_context: PortfolioContext


class BrokerPortfolioSyncWorkflow:
    """Sync broker account state into local portfolio mirrors and risk context."""

    def __init__(self, *, repository: Any, broker: Any) -> None:
        self.repository = repository
        self.broker = broker

    def run(
        self,
        *,
        as_of: datetime,
        approved_core_tickers: tuple[str, ...] = (),
        extra_position_metadata: dict[str, dict[str, Any]] | None = None,
        persist: bool = True,
    ) -> BrokerPortfolioSyncResult:
        account_payload = self.broker.sync_account()
        broker_positions = self.broker.sync_positions()
        local_position_metadata = {
            position.ticker: {
                "strategy_id": position.strategy_id,
                "trade_identity": position.trade_identity,
            }
            for position in self.repository.load_paper_positions()
        }
        for ticker, metadata in (extra_position_metadata or {}).items():
            local_position_metadata[ticker.upper()] = dict(metadata)
        synced_positions = build_positions_from_broker(
            broker_positions=broker_positions,
            as_of=as_of,
            local_position_metadata=local_position_metadata,
        )
        snapshot = build_portfolio_snapshot_from_account(
            account_payload,
            as_of=as_of,
        )
        if persist:
            self.repository.replace_paper_positions(synced_positions)
            self.repository.save_portfolio_snapshot(snapshot)
        return BrokerPortfolioSyncResult(
            snapshot=snapshot,
            positions=synced_positions,
            portfolio_context=build_portfolio_context(
                snapshot=snapshot,
                positions=synced_positions,
                approved_core_tickers=approved_core_tickers,
            ),
        )
