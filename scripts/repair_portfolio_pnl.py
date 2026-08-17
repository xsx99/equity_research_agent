"""Safely preview or repair cumulative stock P&L in portfolio history."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import text

from src.core.config import PAPER_ACCOUNT_STARTING_EQUITY
from src.db.connection import SessionLocal
from src.db.models.trading import PaperExecution, PaperOrder, PaperPosition, PortfolioSnapshot
from src.trading.portfolio.pnl import (
    AVERAGE_COST_TOLERANCE,
    CURRENCY_TOLERANCE,
    QUANTITY_TOLERANCE,
    RECONCILIATION_RESIDUAL_TOLERANCE,
    PortfolioPnlPoint,
    PortfolioPnlValidationError,
    StockFillEvent,
    _validate_positions,
    replay_stock_fills,
    select_active_lifecycle_boundary,
)
from src.trading.portfolio.state import StockPosition

_PNL_METHOD = "weighted_average_stock_fills_v1"
_UNSAFE_DATA_ROOTS = (PurePosixPath("/tmp"), PurePosixPath("/run"), PurePosixPath("/dev/shm"))


def run_repair(*, session: Any, apply: bool, starting_equity: float) -> dict[str, object]:
    """Preview or atomically repair the latest clean account lifecycle."""
    try:
        snapshots = _load_rows(session, PortfolioSnapshot, apply=apply)
        orders = _load_rows(session, PaperOrder, apply=apply)
        executions = _load_rows(session, PaperExecution, apply=apply)
        positions = _load_rows(session, PaperPosition, apply=apply, status="open")
        points = tuple(
            PortfolioPnlPoint(
                snapshot_time=row.snapshot_time,
                account_equity=float(row.account_equity),
                stock_market_value=float(row.stock_market_value),
                option_market_value=float(row.option_market_value),
            )
            for row in sorted(snapshots, key=lambda item: item.snapshot_time)
        )
        fills, execution_actions = _build_fills(orders=orders, executions=executions)
        boundary = select_active_lifecycle_boundary(
            points,
            fills,
            starting_equity=starting_equity,
        )
        _reject_ambiguous_boundary(points=points, fills=fills, boundary=boundary, starting_equity=starting_equity)

        active_snapshots = sorted(
            (row for row in snapshots if row.snapshot_time >= boundary),
            key=lambda item: item.snapshot_time,
        )
        if not active_snapshots:
            raise PortfolioPnlValidationError("missing_active_snapshots")

        latest_snapshot = active_snapshots[-1]
        latest_replay = replay_stock_fills(
            fills,
            started_at=boundary,
            through=latest_snapshot.snapshot_time,
        )
        cost_diagnostics = _validate_positions(
            positions=_stock_positions(positions, as_of=latest_snapshot.snapshot_time),
            open_cost_basis=latest_replay.open_cost_basis,
        )

        excluded_fill_count = sum(fill.executed_at < boundary for fill in fills)
        excluded_snapshot_count = sum(point.snapshot_time < boundary for point in points)
        proposed_snapshots: list[tuple[Any, Decimal, Decimal, dict[str, object]]] = []
        residuals: list[float] = []
        for row in active_snapshots:
            replay = replay_stock_fills(
                fills,
                started_at=boundary,
                through=row.snapshot_time,
            )
            snapshot_has_inventory = abs(float(row.stock_market_value)) > CURRENCY_TOLERANCE
            replay_has_inventory = any(
                basis.quantity > QUANTITY_TOLERANCE
                for basis in replay.open_cost_basis.values()
            )
            if snapshot_has_inventory != replay_has_inventory:
                raise PortfolioPnlValidationError(
                    "historical_inventory_mismatch:"
                    f"{row.snapshot_time.isoformat()}:"
                    f"snapshot={snapshot_has_inventory}:replay={replay_has_inventory}"
                )
            open_cost = sum(
                basis.quantity * basis.average_cost
                for basis in replay.open_cost_basis.values()
            )
            unrealized = float(row.stock_market_value) - open_cost
            residual = (
                float(row.account_equity)
                - float(starting_equity)
                - replay.realized_pnl
                - unrealized
            )
            residuals.append(residual)
            metadata = {
                **dict(row.metadata_json or {}),
                "pnl_calculation_method": _PNL_METHOD,
                "pnl_starting_equity": float(starting_equity),
                "pnl_tracking_started_at": boundary.isoformat(),
                "pnl_reconciliation_residual": residual,
                "pnl_reconciled": abs(residual) <= RECONCILIATION_RESIDUAL_TOLERANCE,
                "pnl_fill_count": replay.fill_count,
                "pnl_excluded_pre_boundary_fill_count": excluded_fill_count,
                "pnl_excluded_pre_boundary_snapshot_count": excluded_snapshot_count,
                "pnl_tolerances": _tolerances(),
                "pnl_cost_basis_diagnostics": (
                    cost_diagnostics if row is latest_snapshot else []
                ),
            }
            proposed_snapshots.append(
                (
                    row,
                    Decimal(str(replay.realized_pnl)),
                    Decimal(str(unrealized)),
                    metadata,
                )
            )

        snapshot_repairs = [
            proposal
            for proposal in proposed_snapshots
            if _snapshot_differs(*proposal)
        ]
        cash_repairs = _cash_effect_repairs(
            executions=executions,
            execution_actions=execution_actions,
            boundary=boundary,
        )
        data_directory = _read_postgres_data_directory(session)
        if apply:
            validate_persistent_postgres_storage(session, data_directory=data_directory)
            for row, realized, unrealized, metadata in snapshot_repairs:
                row.realized_pnl = realized
                row.unrealized_pnl = unrealized
                row.metadata_json = metadata
            for row, repaired_cash_effect in cash_repairs:
                row.net_cash_effect = repaired_cash_effect
            session.commit()
        else:
            session.rollback()

        latest_realized = float(proposed_snapshots[-1][1])
        latest_unrealized = float(proposed_snapshots[-1][2])
        latest_residual = residuals[-1]
        return {
            "status": "applied" if apply else "dry_run",
            "applied": apply,
            "boundary": boundary.isoformat(),
            "data_directory": data_directory,
            "excluded_pre_boundary_snapshot_count": excluded_snapshot_count,
            "excluded_pre_boundary_fill_count": excluded_fill_count,
            "active_snapshot_count": len(active_snapshots),
            "active_fill_count": latest_replay.fill_count,
            "snapshot_repair_count": len(snapshot_repairs),
            "cash_effect_repair_count": len(cash_repairs),
            "earliest_snapshot_to_update": (
                snapshot_repairs[0][0].snapshot_time.isoformat()
                if snapshot_repairs
                else None
            ),
            "latest_snapshot_to_update": (
                snapshot_repairs[-1][0].snapshot_time.isoformat()
                if snapshot_repairs
                else None
            ),
            "latest_realized_pnl": latest_realized,
            "latest_unrealized_pnl": latest_unrealized,
            "latest_reconciliation_residual": latest_residual,
            "maximum_absolute_residual": max(abs(value) for value in residuals),
            "tolerances": _tolerances(),
            "position_mismatches": [],
            "cost_basis_diagnostics": cost_diagnostics,
            "validation_errors": [],
        }
    except PortfolioPnlValidationError as exc:
        session.rollback()
        if apply:
            raise
        return {
            "status": "blocked",
            "applied": False,
            "data_directory": _safe_read_postgres_data_directory(session),
            "validation_errors": [str(exc)],
            "position_mismatches": _structured_position_mismatches(exc),
        }
    except Exception:
        session.rollback()
        raise


def validate_persistent_postgres_storage(
    session: Any,
    *,
    data_directory: str | None = None,
) -> str:
    """Reject known temporary PostgreSQL data-directory roots."""
    path_text = data_directory or _read_postgres_data_directory(session)
    path = PurePosixPath(path_text)
    if not path.is_absolute() or any(path == root or root in path.parents for root in _UNSAFE_DATA_ROOTS):
        raise RuntimeError(f"unsafe_postgres_data_directory:{path_text}")
    return path_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the repair atomically")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument(
        "--starting-equity",
        type=float,
        default=PAPER_ACCOUNT_STARTING_EQUITY,
    )
    args = parser.parse_args(argv)
    session = SessionLocal()
    try:
        report = run_repair(
            session=session,
            apply=args.apply,
            starting_equity=args.starting_equity,
        )
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True, default=str))
        else:
            print(f"portfolio P&L repair: {report['status']}")
        return 0
    finally:
        session.close()


def _load_rows(session: Any, model: Any, *, apply: bool, **filters: object) -> list[Any]:
    query = session.query(model)
    if filters:
        query = query.filter_by(**filters)
    if apply:
        query = query.with_for_update()
    return list(query.all())


def _build_fills(*, orders: list[Any], executions: list[Any]) -> tuple[tuple[StockFillEvent, ...], dict[object, str]]:
    orders_by_id = {row.paper_order_id: row for row in orders}
    fills: list[StockFillEvent] = []
    actions: dict[object, str] = {}
    for row in executions:
        order = orders_by_id.get(row.paper_order_id)
        if order is None:
            raise PortfolioPnlValidationError(
                f"orphan_execution:{row.paper_execution_id}:{row.paper_order_id}"
            )
        if str(order.status).lower() != "filled":
            continue
        action = str(order.action).lower()
        fills.append(
            StockFillEvent(
                execution_id=str(row.paper_execution_id),
                ticker=row.ticker,
                executed_at=row.executed_at,
                action=action,
                quantity=float(row.quantity),
                fill_price=float(row.fill_price),
            )
        )
        actions[row.paper_execution_id] = action
    return (
        tuple(sorted(fills, key=lambda fill: (fill.executed_at, fill.execution_id))),
        actions,
    )


def _reject_ambiguous_boundary(
    *,
    points: tuple[PortfolioPnlPoint, ...],
    fills: tuple[StockFillEvent, ...],
    boundary: Any,
    starting_equity: float,
) -> None:
    fill_times = {fill.executed_at for fill in fills}
    candidates_at_boundary = [
        point
        for point in points
        if point.snapshot_time == boundary
        and abs(point.account_equity - starting_equity) <= CURRENCY_TOLERANCE
        and abs(point.stock_market_value) <= CURRENCY_TOLERANCE
        and abs(point.option_market_value) <= CURRENCY_TOLERANCE
        and point.snapshot_time not in fill_times
    ]
    if len(candidates_at_boundary) != 1:
        raise PortfolioPnlValidationError(f"ambiguous_clean_reset:{boundary.isoformat()}")


def _stock_positions(rows: list[Any], *, as_of: Any) -> tuple[StockPosition, ...]:
    return tuple(
        StockPosition(
            ticker=row.ticker,
            quantity=float(row.quantity),
            average_cost=float(row.average_cost),
            market_price=float(row.average_cost),
            market_value=float(row.quantity) * float(row.average_cost),
            trade_identity="tactical_stock_trade",
            strategy_id=None,
            opened_at=as_of,
            updated_at=as_of,
        )
        for row in rows
    )


def _snapshot_differs(
    row: Any,
    realized: Decimal,
    unrealized: Decimal,
    metadata: dict[str, object],
) -> bool:
    return (
        Decimal(str(row.realized_pnl)) != realized
        or Decimal(str(row.unrealized_pnl)) != unrealized
        or dict(row.metadata_json or {}) != metadata
    )


def _cash_effect_repairs(
    *,
    executions: list[Any],
    execution_actions: dict[object, str],
    boundary: Any,
) -> list[tuple[Any, Decimal]]:
    repairs: list[tuple[Any, Decimal]] = []
    for row in executions:
        action = execution_actions.get(row.paper_execution_id)
        if action not in {"reduce", "exit"} or row.executed_at < boundary:
            continue
        expected = Decimal(str(float(row.quantity) * float(row.fill_price)))
        if Decimal(str(row.net_cash_effect)) != expected:
            repairs.append((row, expected))
    return repairs


def _read_postgres_data_directory(session: Any) -> str:
    value = session.execute(text("SHOW data_directory")).scalar_one()
    return str(value)


def _safe_read_postgres_data_directory(session: Any) -> str | None:
    try:
        return _read_postgres_data_directory(session)
    except Exception:
        return None


def _structured_position_mismatches(
    error: PortfolioPnlValidationError,
) -> list[dict[str, object]]:
    parts = str(error).split(":")
    if len(parts) != 3 or parts[0] not in {"quantity_mismatch", "average_cost_mismatch"}:
        return []
    values = parts[2].split("!=", maxsplit=1)
    if len(values) != 2:
        return []
    return [
        {
            "kind": "quantity" if parts[0] == "quantity_mismatch" else "average_cost",
            "ticker": parts[1],
            "mirrored": float(values[0]),
            "replayed": float(values[1]),
        }
    ]


def _tolerances() -> dict[str, float]:
    return {
        "quantity": QUANTITY_TOLERANCE,
        "currency": CURRENCY_TOLERANCE,
        "average_cost": AVERAGE_COST_TOLERANCE,
        "reconciliation_residual": RECONCILIATION_RESIDUAL_TOLERANCE,
    }


if __name__ == "__main__":
    raise SystemExit(main())
