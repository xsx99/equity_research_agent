#!/usr/bin/env python3
"""Submit a tiny real Alpaca paper order and print broker-sourced account state."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import config as app_config  # noqa: F401
from src.trading.brokers.paper_stock import PaperStockBroker


def run_smoke(
    *,
    ticker: str,
    qty: float,
    strategy_id: str,
    broker: Any,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    now = as_of or datetime.now(timezone.utc)
    result = broker.submit_fractional_market_buy(
        ticker=ticker.upper(),
        qty=qty,
        strategy_id=strategy_id,
    )
    order = result["order"]
    execution = result["execution"]
    account = result["account"]
    positions = result["positions"]
    order_status = order["status"] if isinstance(order, dict) else getattr(order, "status", None)
    return {
        "status": "passed" if order_status == "filled" else "failed",
        "ticker": ticker.upper(),
        "qty": qty,
        "as_of": now.isoformat(),
        "order": _order_json(order),
        "execution": _execution_json(execution),
        "account": _account_json(account),
        "positions": _positions_json(positions),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--qty", type=float, default=0.01)
    parser.add_argument("--strategy-id", default="alpaca_paper_smoke_v1")
    parser.add_argument("--env-file", help="Optional dotenv file to load before constructing the broker.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    if args.env_file:
        load_dotenv(args.env_file)

    broker = PaperStockBroker()
    try:
        report = run_smoke(
            ticker=args.ticker,
            qty=args.qty,
            strategy_id=args.strategy_id,
            broker=broker,
        )
    finally:
        broker.close()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"[{report['status'].upper()}] alpaca paper order smoke ticker={report['ticker']} qty={report['qty']}")
        print(f"order={report['order']}")
        print(f"account={report['account']}")
        print(f"positions={report['positions']}")
    return 0 if report["status"] == "passed" else 1


def _order_json(order: Any) -> dict[str, Any]:
    if isinstance(order, dict):
        return order
    return {
        "paper_order_id": order.paper_order_id,
        "broker_order_id": order.broker_order_id,
        "client_order_id": order.client_order_id,
        "ticker": order.ticker,
        "status": order.status,
        "rejection_reason": order.rejection_reason,
    }


def _execution_json(execution: Any) -> dict[str, Any] | None:
    if execution is None:
        return None
    if isinstance(execution, dict):
        return execution
    return {
        "paper_execution_id": execution.paper_execution_id,
        "broker_order_id": execution.broker_order_id,
        "ticker": execution.ticker,
        "quantity": execution.quantity,
        "fill_price": execution.fill_price,
        "executed_at": execution.executed_at.isoformat(),
    }


def _account_json(account: Any) -> dict[str, Any]:
    if isinstance(account, dict):
        return {
            "cash": float(account.get("cash", 0.0)),
            "buying_power": float(account.get("buying_power", 0.0)),
            "equity": float(account.get("equity", 0.0)),
        }
    return account


def _positions_json(positions: Any) -> list[dict[str, Any]]:
    if isinstance(positions, list):
        return [
            {
                "ticker": str(item.get("symbol", item.get("ticker", ""))).upper(),
                "quantity": float(item.get("qty", item.get("quantity", 0.0))),
            }
            for item in positions
        ]
    return positions


if __name__ == "__main__":
    raise SystemExit(main())
