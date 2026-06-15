#!/usr/bin/env python3
"""Run a standalone Alpaca-backed option paper execution smoke."""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import config as app_config  # noqa: F401
from src.trading.brokers.paper_option import (
    DEFAULT_ALPACA_PAPER_TRADING_BASE_URL,
    PaperOptionBroker,
)
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.risk import RiskDecisionRecord
from src.trading.workflows.paper_execution import PaperExecutionWorkflow
from src.trading.workflows.trading_decision import TradingDecisionRecord


def run_execution(
    *,
    ticker: str,
    contract_symbol: str,
    strategy_type: str,
    option_broker: Any,
    stock_broker: Any,
    as_of: datetime | None = None,
    quantity: int = 1,
    limit_price: float = 2.15,
    strategy_id: str = "manual_option_execution_v1",
) -> dict[str, Any]:
    now = as_of or datetime.now(timezone.utc)
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=stock_broker,
        option_broker=option_broker,
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )
    trading_decision = _build_trading_decision(
        ticker=ticker.upper(),
        contract_symbol=contract_symbol,
        strategy_type=strategy_type,
        strategy_id=strategy_id,
        quantity=quantity,
        limit_price=limit_price,
        as_of=now,
    )
    risk_decision = _build_risk_decision(
        ticker=ticker.upper(),
        quantity=quantity,
        as_of=now,
    )
    result = workflow.run(
        trading_decisions=(trading_decision,),
        risk_decisions=(risk_decision,),
        trade_date=now,
    )
    order = result.paper_option_orders[-1] if result.paper_option_orders else None
    execution = repository.paper_option_executions[-1] if repository.paper_option_executions else None
    return {
        "status": "passed" if order is not None and getattr(order, "status", None) == "filled" else "failed",
        "order": _order_json(order),
        "execution": _execution_json(execution),
        "positions": [_position_json(position) for position in repository.paper_option_positions],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-symbol", required=True)
    parser.add_argument("--ticker", help="Optional underlying ticker override. Defaults to the OCC root in --contract-symbol.")
    parser.add_argument("--strategy-type", choices=("long_call", "long_put"), default="long_call")
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--limit-price", type=float, default=2.15)
    parser.add_argument("--strategy-id", default="manual_option_execution_v1")
    parser.add_argument("--env-file", help="Optional dotenv file to load before constructing the broker.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.env_file:
        load_dotenv(args.env_file)

    ticker = (args.ticker or _parse_contract_symbol(args.contract_symbol)["ticker"]).upper()
    broker = PaperOptionBroker(trading_base_url=DEFAULT_ALPACA_PAPER_TRADING_BASE_URL)
    try:
        result = run_execution(
            ticker=ticker,
            contract_symbol=args.contract_symbol.upper(),
            strategy_type=args.strategy_type,
            option_broker=broker,
            stock_broker=_NoopStockBroker(),
            quantity=args.quantity,
            limit_price=args.limit_price,
            strategy_id=args.strategy_id,
        )
    finally:
        if hasattr(broker, "close"):
            broker.close()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)
    return 0 if result["status"] == "passed" else 1


class _NoopStockBroker:
    pass


def _build_trading_decision(
    *,
    ticker: str,
    contract_symbol: str,
    strategy_type: str,
    strategy_id: str,
    quantity: int,
    limit_price: float,
    as_of: datetime,
) -> TradingDecisionRecord:
    contract = _parse_contract_symbol(contract_symbol)
    strike = contract["strike"]
    option_type = "call" if strategy_type == "long_call" else "put"
    breakeven = strike + limit_price if option_type == "call" else strike - limit_price
    max_loss = limit_price * 100.0 * quantity
    return TradingDecisionRecord(
        trading_decision_id=str(uuid.uuid4()),
        candidate_score_id=None,
        trade_classification_id=None,
        risk_decision_id="manual-option-risk-decision",
        ticker=ticker,
        decision="open_option_strategy",
        strategy_id=strategy_id,
        strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        instrument_type="option",
        selection_source="manual_request",
        manual_request_id=None,
        confidence=1.0,
        target_weight=0.0,
        approved_weight=0.0,
        max_loss_pct=0.0,
        time_horizon="manual",
        thesis="manual option paper execution",
        invalidators=[],
        prompt_template=object(),
        prompt_run=object(),
        usage_events=[],
        decision_time=as_of,
        available_for_decision_at=as_of,
        metadata_json={
            "paper_trade_authorized": True,
            "option_strategy": {
                "option_strategy_decision_id": str(uuid.uuid4()),
                "option_strategy_type": strategy_type,
                "status": "ready",
                "underlying_price": strike,
                "net_debit_or_credit": limit_price,
                "max_loss": max_loss,
                "max_profit": None,
                "breakevens": [breakeven],
                "margin_requirement": max_loss,
                "buying_power_effect": max_loss,
                "assignment_notional": 0.0,
                "portfolio_delta": 0.25 if option_type == "call" else -0.25,
                "portfolio_gamma": 0.03,
                "portfolio_theta": -0.02,
                "portfolio_vega": 0.11,
                "event_through_expiry": False,
                "strategy_pairing_method": "single_leg",
                "assignment_plan": None,
                "metadata_json": {
                    "legs": [
                        _build_leg_payload(
                            contract_symbol=contract_symbol,
                            option_type=option_type,
                            strike=strike,
                            expiry=contract["expiry"],
                            quantity=quantity,
                            limit_price=limit_price,
                            decision_date=as_of.date(),
                        )
                    ]
                },
            },
        },
    )


def _build_risk_decision(
    *,
    ticker: str,
    quantity: int,
    as_of: datetime,
) -> RiskDecisionRecord:
    return RiskDecisionRecord(
        risk_decision_id="manual-option-risk-decision",
        candidate_score_id=None,
        trade_classification_id=None,
        position_sizing_decision_id=None,
        ticker=ticker,
        status="approved",
        reason_code="manual_execution",
        approved_weight=0.0,
        approved_notional=0.0,
        approved_quantity=float(quantity),
        portfolio_risk_snapshot_id=None,
        applied_rules=["manual_execution"],
        generated_hedge_action=None,
        decision_time=as_of,
        metadata_json={},
    )


def _build_leg_payload(
    *,
    contract_symbol: str,
    option_type: str,
    strike: float,
    expiry: date,
    quantity: int,
    limit_price: float,
    decision_date: date,
) -> dict[str, Any]:
    spread = 0.05
    bid = max(limit_price - spread, 0.01)
    ask = limit_price + spread
    return {
        "contract_symbol": contract_symbol,
        "option_type": option_type,
        "side": "buy",
        "quantity": quantity,
        "ratio_qty": 1,
        "strike": strike,
        "expiry": expiry.isoformat(),
        "dte": max((expiry - decision_date).days, 0),
        "delta": 0.25 if option_type == "call" else -0.25,
        "gamma": 0.03,
        "theta": -0.02,
        "vega": 0.11,
        "iv_rank": 0.5,
        "bid": bid,
        "ask": ask,
        "mid": limit_price,
        "chosen_price": limit_price,
    }


def _parse_contract_symbol(contract_symbol: str) -> dict[str, Any]:
    normalized = contract_symbol.strip().upper()
    match = re.fullmatch(r"(?P<ticker>[A-Z]+)(?P<expiry>\d{6})(?P<option_type>[CP])(?P<strike>\d{8})", normalized)
    if match is None:
        raise ValueError("invalid_option_contract_symbol")
    expiry_raw = match.group("expiry")
    expiry = date(
        year=2000 + int(expiry_raw[:2]),
        month=int(expiry_raw[2:4]),
        day=int(expiry_raw[4:6]),
    )
    return {
        "ticker": match.group("ticker"),
        "expiry": expiry,
        "option_type": match.group("option_type"),
        "strike": int(match.group("strike")) / 1000.0,
    }


def _order_json(order: Any) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "paper_option_order_id": order.paper_option_order_id,
        "broker_order_id": order.broker_order_id,
        "client_order_id": order.client_order_id,
        "ticker": order.ticker,
        "status": order.status,
        "option_strategy_type": order.option_strategy_type,
    }


def _execution_json(execution: Any) -> dict[str, Any] | None:
    if execution is None:
        return None
    return {
        "paper_option_execution_id": execution.paper_option_execution_id,
        "broker_order_id": execution.broker_order_id,
        "ticker": execution.ticker,
        "quantity": execution.quantity,
        "fill_price": execution.fill_price,
        "executed_at": execution.executed_at.isoformat(),
    }


def _position_json(position: Any) -> dict[str, Any]:
    return {
        "paper_option_position_id": position.paper_option_position_id,
        "ticker": position.ticker,
        "quantity": position.quantity,
        "status": position.status,
        "option_strategy_type": position.option_strategy_type,
        "metadata": position.metadata_json,
    }


if __name__ == "__main__":
    raise SystemExit(main())
