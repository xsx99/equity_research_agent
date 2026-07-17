"""Broker-backed portfolio sync workflow for live PR6 account state."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import uuid

from src.trading.brokers.paper_option import PaperOptionPosition
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

_BROKER_OPTION_POSITION_NAMESPACE = uuid.UUID("6e4d0f64-f761-4e8f-9b2e-410cc093ca3b")


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
                "opened_at": position.opened_at,
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
            _persist_broker_option_positions(
                repository=self.repository,
                as_of=as_of,
                broker_positions=broker_positions,
                local_option_position_metadata=local_option_position_metadata,
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
                "paper_option_position_id": position.paper_option_position_id,
                "option_strategy_decision_id": position.option_strategy_decision_id,
                "trade_identity": position.trade_identity,
                "strategy_id": position.strategy_id,
                "option_strategy_type": position.option_strategy_type,
                "opened_at": position.opened_at,
                "expiry": position.expiry,
                "max_loss": position.max_loss,
                "margin_requirement": position.margin_requirement,
                "buying_power_effect": position.buying_power_effect,
                "assignment_notional": position.assignment_notional,
                "metadata_json": dict(position.metadata_json),
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


def _persist_broker_option_positions(
    *,
    repository: Any,
    as_of: datetime,
    broker_positions: list[dict[str, Any]],
    local_option_position_metadata: dict[str, dict[str, Any]],
) -> None:
    save_position = getattr(repository, "save_paper_option_position", None)
    if not callable(save_position):
        return
    for payload in broker_positions:
        if not is_option_position_payload(payload):
            continue
        contract_symbol = str(payload.get("symbol") or "").upper()
        if not contract_symbol:
            continue
        position_metadata = local_option_position_metadata.get(contract_symbol, {})
        if position_metadata and position_metadata.get("option_strategy_type") != "broker_option_position":
            continue
        option_positions = build_option_positions_from_broker(
            broker_positions=[payload],
            as_of=as_of,
            local_option_position_metadata=local_option_position_metadata,
        )
        if not option_positions:
            continue
        option_position = option_positions[0]
        metadata_json = dict(position_metadata.get("metadata_json") or {})
        metadata_json["broker_leg_refs"] = [
            {
                "contract_symbol": contract_symbol,
                "position_intent": "broker_position",
            }
        ]
        save_position(
            PaperOptionPosition(
                paper_option_position_id=str(
                    position_metadata.get("paper_option_position_id")
                    or uuid.uuid5(
                        _BROKER_OPTION_POSITION_NAMESPACE,
                        contract_symbol,
                    )
                ),
                option_strategy_decision_id=position_metadata.get("option_strategy_decision_id"),
                ticker=option_position.ticker,
                strategy_id=option_position.strategy_id or "broker_option_position",
                option_strategy_type=option_position.option_strategy_type,
                trade_identity=option_position.trade_identity,
                quantity=option_position.quantity,
                opened_at=option_position.opened_at,
                updated_at=option_position.updated_at,
                status="open",
                expiry=option_position.expiry,
                max_loss=option_position.max_loss,
                margin_requirement=option_position.margin_requirement,
                buying_power_effect=option_position.buying_power_effect,
                assignment_notional=option_position.assignment_notional,
                metadata_json=metadata_json,
            )
        )
