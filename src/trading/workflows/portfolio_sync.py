"""Broker-backed portfolio sync workflow for live PR6 account state."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.trading.portfolio.state import (
    OptionPosition,
    PortfolioSnapshot,
    StockPosition,
    build_option_positions_from_broker,
    build_portfolio_context,
    build_portfolio_snapshot_from_account,
    build_positions_from_broker,
    is_option_position_payload,
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
        local_option_positions = tuple(getattr(self.repository, "load_paper_option_positions", lambda: ())())
        local_option_position_metadata = _local_option_position_metadata(local_option_positions)
        synced_positions = build_positions_from_broker(
            broker_positions=broker_positions,
            as_of=as_of,
            local_position_metadata=local_position_metadata,
        )
        option_positions = build_option_positions_from_broker(
            broker_positions=broker_positions,
            as_of=as_of,
            local_option_position_metadata=local_option_position_metadata,
        )
        snapshot = build_portfolio_snapshot_from_account(
            account_payload,
            as_of=as_of,
        )
        if persist:
            _reconcile_local_option_positions(
                repository=self.repository,
                as_of=as_of,
                local_option_positions=local_option_positions,
                broker_positions=broker_positions,
            )
            self.repository.replace_paper_positions(synced_positions)
            self.repository.save_portfolio_snapshot(snapshot)
        return BrokerPortfolioSyncResult(
            snapshot=snapshot,
            positions=synced_positions,
            portfolio_context=build_portfolio_context(
                snapshot=snapshot,
                positions=synced_positions,
                option_positions=option_positions,
                approved_core_tickers=approved_core_tickers,
            ),
        )


def _local_option_position_metadata(local_option_positions: tuple[Any, ...]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for position in local_option_positions:
        broker_leg_refs = list(position.metadata_json.get("broker_leg_refs") or [])
        for ref in broker_leg_refs:
            if not isinstance(ref, dict):
                continue
            contract_symbol = ref.get("contract_symbol")
            if not isinstance(contract_symbol, str) or not contract_symbol:
                continue
            metadata[contract_symbol.upper()] = {
                "ticker": position.ticker,
                "trade_identity": position.trade_identity,
                "strategy_id": position.strategy_id,
                "option_strategy_type": position.option_strategy_type,
                "opened_at": position.opened_at,
                "expiry": position.expiry,
                "max_loss": position.max_loss,
                "margin_requirement": position.margin_requirement,
                "buying_power_effect": position.buying_power_effect,
                "assignment_notional": position.assignment_notional,
            }
    return metadata


def _reconcile_local_option_positions(
    *,
    repository: Any,
    as_of: datetime,
    local_option_positions: tuple[Any, ...],
    broker_positions: list[dict[str, Any]],
) -> None:
    broker_option_symbols = {
        str(payload.get("symbol") or "").upper()
        for payload in broker_positions
        if is_option_position_payload(payload)
    }
    for position in local_option_positions:
        broker_leg_refs = list(position.metadata_json.get("broker_leg_refs") or [])
        contract_symbols = {
            str(ref.get("contract_symbol") or "").upper()
            for ref in broker_leg_refs
            if isinstance(ref, dict) and ref.get("contract_symbol")
        }
        if contract_symbols and contract_symbols & broker_option_symbols:
            continue
        if not contract_symbols:
            continue
        repository.save_paper_option_position(
            type(position)(
                paper_option_position_id=position.paper_option_position_id,
                option_strategy_decision_id=position.option_strategy_decision_id,
                ticker=position.ticker,
                strategy_id=position.strategy_id,
                option_strategy_type=position.option_strategy_type,
                trade_identity=position.trade_identity,
                quantity=position.quantity,
                opened_at=position.opened_at,
                updated_at=as_of,
                status="closed",
                expiry=position.expiry,
                max_loss=position.max_loss,
                margin_requirement=0.0,
                buying_power_effect=0.0,
                assignment_notional=0.0,
                metadata_json={
                    **dict(position.metadata_json),
                    "reconciliation_status": "broker_position_missing",
                    "reconciled_at": as_of.isoformat(),
                },
            )
        )
