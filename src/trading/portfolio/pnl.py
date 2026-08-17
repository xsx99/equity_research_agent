"""Pure weighted-average stock P&L replay helpers."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from math import isfinite
from typing import Sequence

from src.trading.portfolio.state import PortfolioSnapshot, StockPosition


_BUY_ACTIONS = {"enter_long"}
_SELL_ACTIONS = {"reduce", "exit"}
_SUPPORTED_ACTIONS = _BUY_ACTIONS | _SELL_ACTIONS
_ZERO_TOLERANCE = 1e-12

QUANTITY_TOLERANCE = 1e-6
CURRENCY_TOLERANCE = 0.01
AVERAGE_COST_TOLERANCE = 0.01
RECONCILIATION_RESIDUAL_TOLERANCE = 0.01


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
class PortfolioPnlPoint:
    snapshot_time: datetime
    account_equity: float
    stock_market_value: float
    option_market_value: float


@dataclass(frozen=True)
class OpenCostBasis:
    quantity: float
    average_cost: float


@dataclass(frozen=True)
class StockPnlReplay:
    realized_pnl: float
    open_cost_basis: dict[str, OpenCostBasis]
    fill_count: int


def select_active_lifecycle_boundary(
    points: Sequence[PortfolioPnlPoint],
    fills: Sequence[StockFillEvent],
    *,
    starting_equity: float,
    currency_tolerance: float = CURRENCY_TOLERANCE,
) -> datetime:
    """Select the latest unambiguous flat snapshot at starting equity."""
    fill_times = {fill.executed_at for fill in fills}
    candidates = [
        point.snapshot_time
        for point in points
        if abs(float(point.account_equity) - float(starting_equity)) <= currency_tolerance
        and abs(float(point.stock_market_value)) <= currency_tolerance
        and abs(float(point.option_market_value)) <= currency_tolerance
        and point.snapshot_time not in fill_times
    ]
    if not candidates:
        raise PortfolioPnlValidationError("missing_clean_reset")
    return max(candidates)


def enrich_snapshot_with_stock_pnl(
    snapshot: PortfolioSnapshot,
    *,
    positions: Sequence[StockPosition],
    points: Sequence[PortfolioPnlPoint],
    fills: Sequence[StockFillEvent],
    starting_equity: float,
) -> PortfolioSnapshot:
    """Return a broker snapshot enriched from the canonical local fill replay."""
    started_at = select_active_lifecycle_boundary(
        points,
        fills,
        starting_equity=starting_equity,
    )
    replay = replay_stock_fills(
        fills,
        started_at=started_at,
        through=snapshot.as_of,
    )
    cost_diagnostics = _validate_positions(
        positions=positions,
        open_cost_basis=replay.open_cost_basis,
    )
    replayed_open_cost = sum(
        basis.quantity * basis.average_cost
        for basis in replay.open_cost_basis.values()
    )
    unrealized_pnl = float(snapshot.stock_market_value) - replayed_open_cost
    total_pnl = float(snapshot.account_equity) - float(starting_equity)
    residual = total_pnl - replay.realized_pnl - unrealized_pnl
    metadata = {
        **dict(snapshot.metadata_json),
        "pnl_calculation_method": "weighted_average_stock_fills_v1",
        "pnl_starting_equity": float(starting_equity),
        "pnl_tracking_started_at": started_at.isoformat(),
        "pnl_reconciliation_residual": residual,
        "pnl_reconciled": abs(residual) <= RECONCILIATION_RESIDUAL_TOLERANCE,
        "pnl_fill_count": replay.fill_count,
        "pnl_excluded_pre_boundary_fill_count": sum(
            1 for fill in fills if fill.executed_at < started_at
        ),
        "pnl_excluded_pre_boundary_snapshot_count": sum(
            1 for point in points if point.snapshot_time < started_at
        ),
        "pnl_tolerances": {
            "quantity": QUANTITY_TOLERANCE,
            "currency": CURRENCY_TOLERANCE,
            "average_cost": AVERAGE_COST_TOLERANCE,
            "reconciliation_residual": RECONCILIATION_RESIDUAL_TOLERANCE,
        },
        "pnl_cost_basis_diagnostics": cost_diagnostics,
    }
    return replace(
        snapshot,
        realized_pnl=replay.realized_pnl,
        unrealized_pnl=unrealized_pnl,
        metadata_json=metadata,
    )


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


def _validate_positions(
    *,
    positions: Sequence[StockPosition],
    open_cost_basis: dict[str, OpenCostBasis],
) -> list[dict[str, float | str]]:
    broker_by_ticker = {str(position.ticker).upper(): position for position in positions}
    diagnostics: list[dict[str, float | str]] = []
    for ticker in sorted(set(broker_by_ticker) | set(open_cost_basis)):
        position = broker_by_ticker.get(ticker)
        basis = open_cost_basis.get(ticker)
        broker_quantity = float(position.quantity) if position is not None else 0.0
        replayed_quantity = float(basis.quantity) if basis is not None else 0.0
        if abs(broker_quantity - replayed_quantity) > QUANTITY_TOLERANCE:
            raise PortfolioPnlValidationError(
                f"quantity_mismatch:{ticker}:{broker_quantity}!={replayed_quantity}"
            )
        if position is None or basis is None or replayed_quantity <= QUANTITY_TOLERANCE:
            continue
        broker_average_cost = float(position.average_cost)
        replayed_average_cost = float(basis.average_cost)
        difference = broker_average_cost - replayed_average_cost
        if abs(difference) > AVERAGE_COST_TOLERANCE + _ZERO_TOLERANCE:
            raise PortfolioPnlValidationError(
                f"average_cost_mismatch:{ticker}:{broker_average_cost}!={replayed_average_cost}"
            )
        if abs(difference) > _ZERO_TOLERANCE:
            diagnostics.append(
                {
                    "ticker": ticker,
                    "broker_average_cost": broker_average_cost,
                    "replayed_average_cost": replayed_average_cost,
                    "difference": difference,
                }
            )
    return diagnostics
