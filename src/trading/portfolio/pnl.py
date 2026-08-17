"""Pure weighted-average stock P&L replay helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Sequence


_BUY_ACTIONS = {"enter_long"}
_SELL_ACTIONS = {"reduce", "exit"}
_SUPPORTED_ACTIONS = _BUY_ACTIONS | _SELL_ACTIONS
_ZERO_TOLERANCE = 1e-12


class PortfolioPnlValidationError(ValueError):
    """Raised when persisted stock history cannot be replayed safely."""


@dataclass(frozen=True)
class StockFillEvent:
    execution_id: str
    ticker: str
    executed_at: datetime
    action: str
    quantity: float
    fill_price: float


@dataclass(frozen=True)
class OpenCostBasis:
    quantity: float
    average_cost: float


@dataclass(frozen=True)
class StockPnlReplay:
    realized_pnl: float
    open_cost_basis: dict[str, OpenCostBasis]
    fill_count: int


def replay_stock_fills(
    fills: Sequence[StockFillEvent],
    *,
    started_at: datetime,
    through: datetime,
) -> StockPnlReplay:
    """Replay long-stock fills through a point in time."""
    if through < started_at:
        raise PortfolioPnlValidationError("through_before_started_at")

    normalized = tuple(_validate_fill(fill) for fill in fills)
    execution_ids = [fill.execution_id for fill in normalized]
    if len(set(execution_ids)) != len(execution_ids):
        raise PortfolioPnlValidationError("duplicate_execution_id")

    active = sorted(
        (
            fill
            for fill in normalized
            if started_at <= fill.executed_at <= through
        ),
        key=lambda fill: (fill.executed_at, fill.execution_id),
    )
    open_cost_basis: dict[str, OpenCostBasis] = {}
    realized_pnl = 0.0
    for fill in active:
        current = open_cost_basis.get(fill.ticker, OpenCostBasis(0.0, 0.0))
        if fill.action in _BUY_ACTIONS:
            new_quantity = current.quantity + fill.quantity
            new_average_cost = (
                (current.quantity * current.average_cost) + (fill.quantity * fill.fill_price)
            ) / new_quantity
            open_cost_basis[fill.ticker] = OpenCostBasis(new_quantity, new_average_cost)
            continue

        if fill.quantity > current.quantity + _ZERO_TOLERANCE:
            raise PortfolioPnlValidationError(
                f"oversell:{fill.execution_id}:{fill.ticker}:{fill.quantity}>{current.quantity}"
            )
        realized_pnl += fill.quantity * (fill.fill_price - current.average_cost)
        remaining_quantity = current.quantity - fill.quantity
        if remaining_quantity <= _ZERO_TOLERANCE:
            open_cost_basis.pop(fill.ticker, None)
        else:
            open_cost_basis[fill.ticker] = OpenCostBasis(
                remaining_quantity,
                current.average_cost,
            )

    return StockPnlReplay(
        realized_pnl=realized_pnl,
        open_cost_basis=dict(sorted(open_cost_basis.items())),
        fill_count=len(active),
    )


def _validate_fill(fill: StockFillEvent) -> StockFillEvent:
    execution_id = str(fill.execution_id or "").strip()
    if not execution_id:
        raise PortfolioPnlValidationError("execution_id")
    ticker = str(fill.ticker or "").strip().upper()
    if not ticker:
        raise PortfolioPnlValidationError(f"ticker:{execution_id}")
    action = str(fill.action or "").strip().lower()
    if action not in _SUPPORTED_ACTIONS:
        raise PortfolioPnlValidationError(f"action:{execution_id}:{action}")
    quantity = float(fill.quantity)
    if not isfinite(quantity) or quantity <= 0:
        raise PortfolioPnlValidationError(f"quantity:{execution_id}:{quantity}")
    fill_price = float(fill.fill_price)
    if not isfinite(fill_price) or fill_price <= 0:
        raise PortfolioPnlValidationError(f"fill_price:{execution_id}:{fill_price}")
    if fill.executed_at.tzinfo is None:
        raise PortfolioPnlValidationError(f"executed_at_timezone:{execution_id}")
    return StockFillEvent(
        execution_id=execution_id,
        ticker=ticker,
        executed_at=fill.executed_at,
        action=action,
        quantity=quantity,
        fill_price=fill_price,
    )
