#!/usr/bin/env python3
"""Run the PR06 Alpaca-backed paper execution workflow from simple CLI inputs."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import config as app_config  # noqa: F401
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.brokers.paper_stock import PaperStockBroker
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.risk import RiskDecisionRecord
from src.trading.workflows.paper_execution import PaperExecutionWorkflow
from src.trading.workflows.trading_decision import TradingDecisionRecord


def run_execution(
    *,
    ticker: str,
    strategy_id: str,
    trade_identity: str,
    decision: str,
    quantity: float,
    broker: Any,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    now = as_of or datetime.now(timezone.utc)
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=broker,
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )
    trading_decision = _build_trading_decision(
        ticker=ticker.upper(),
        strategy_id=strategy_id,
        trade_identity=trade_identity,
        decision=decision,
        as_of=now,
    )
    risk_decision = _build_risk_decision(
        ticker=ticker.upper(),
        quantity=quantity,
        decision=decision,
        as_of=now,
    )
    result = workflow.run(
        trading_decisions=(trading_decision,),
        risk_decisions=(risk_decision,),
        trade_date=now,
    )
    snapshot = result.portfolio_snapshots[-1] if result.portfolio_snapshots else None
    order = result.paper_orders[-1] if result.paper_orders else None
    return {
        "status": "passed" if order is not None and getattr(order, "status", None) == "filled" else "failed",
        "order": _order_json(order),
        "portfolio_snapshot": _snapshot_json(snapshot),
        "positions": [_position_json(position) for position in repository.paper_positions],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--quantity", type=float, required=True)
    parser.add_argument("--strategy-id", default="manual_execution_v1")
    parser.add_argument("--trade-identity", default="tactical_stock_trade")
    parser.add_argument("--decision", choices=("enter_long", "exit"), default="enter_long")
    parser.add_argument("--env-file", help="Optional dotenv file to load before constructing the broker.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.env_file:
        load_dotenv(args.env_file)

    broker = PaperStockBroker()
    try:
        result = run_execution(
            ticker=args.ticker,
            strategy_id=args.strategy_id,
            trade_identity=args.trade_identity,
            decision=args.decision,
            quantity=args.quantity,
            broker=broker,
        )
    finally:
        if hasattr(broker, "close"):
            broker.close()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)
    return 0 if result["status"] == "passed" else 1


def _build_trading_decision(
    *,
    ticker: str,
    strategy_id: str,
    trade_identity: str,
    decision: str,
    as_of: datetime,
) -> TradingDecisionRecord:
    return TradingDecisionRecord(
        trading_decision_id=str(uuid.uuid4()),
        candidate_score_id=None,
        trade_classification_id=None,
        risk_decision_id="manual-risk-decision",
        ticker=ticker,
        decision=decision,
        strategy_id=strategy_id,
        strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity=trade_identity,
        instrument_type="stock",
        selection_source="manual_request",
        manual_request_id=None,
        confidence=1.0,
        target_weight=0.0,
        approved_weight=0.0,
        max_loss_pct=0.0,
        time_horizon="manual",
        thesis="manual paper execution",
        invalidators=[],
        prompt_template=object(),
        prompt_run=object(),
        usage_events=[],
        decision_time=as_of,
        available_for_decision_at=as_of,
        paper_trade_authorized=True,
        metadata_json={"paper_trade_authorized": True},
    )


def _build_risk_decision(*, ticker: str, quantity: float, decision: str, as_of: datetime) -> RiskDecisionRecord:
    signed_quantity = abs(quantity)
    return RiskDecisionRecord(
        risk_decision_id="manual-risk-decision",
        candidate_score_id=None,
        trade_classification_id=None,
        position_sizing_decision_id=None,
        ticker=ticker,
        status="approved",
        reason_code="manual_execution",
        approved_weight=0.0,
        approved_notional=0.0,
        approved_quantity=signed_quantity,
        portfolio_risk_snapshot_id=None,
        applied_rules=["manual_execution"],
        generated_hedge_action=None,
        decision_time=as_of,
        metadata_json={"decision": decision},
    )


def _order_json(order: Any) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "paper_order_id": order.paper_order_id,
        "broker_order_id": order.broker_order_id,
        "client_order_id": order.client_order_id,
        "ticker": order.ticker,
        "status": order.status,
        "rejection_reason": order.rejection_reason,
    }


def _snapshot_json(snapshot: Any) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "cash_balance": snapshot.cash_balance,
        "buying_power": snapshot.buying_power,
        "account_equity": snapshot.account_equity,
        "margin_requirement_source": snapshot.margin_requirement_source,
    }


def _position_json(position: Any) -> dict[str, Any]:
    return {
        "ticker": position.ticker,
        "quantity": position.quantity,
        "direction": position.direction,
        "trade_identity": position.trade_identity,
    }


if __name__ == "__main__":
    raise SystemExit(main())
