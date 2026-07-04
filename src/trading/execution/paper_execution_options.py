"""Option execution helper functions for the paper execution workflow."""
from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from src.trading.brokers.paper_option import (
    PaperOptionOrderLeg,
    PaperOptionOrderRequest,
    PaperOptionPosition,
)
from src.trading.options.strategy import OptionStrategyDecisionRecord
from src.trading.risk import (
    OptionLegRiskInput,
    OptionRiskInput,
    RiskDecisionRecord,
    TradeRiskRequest,
)
from src.trading.strategies.definitions import load_all_trading_definitions
from src.trading.decision.pipeline import TradingDecisionRecord


def _hedge_trading_decision_from_generated_action(
    *,
    risk_decision: RiskDecisionRecord,
    hedge_action: dict[str, Any],
    trade_date: datetime,
) -> TradingDecisionRecord | None:
    decision_action = _hedge_decision_action(hedge_action)
    if decision_action is None:
        return None
    ticker = str(hedge_action.get("target_underlier") or "").strip().upper()
    if not ticker:
        return None
    option_strategy_payload = _generated_hedge_option_strategy_payload(
        hedge_action=hedge_action,
        trade_date=trade_date,
    )
    metadata_json = {
        "paper_trade_authorized": True,
        "generated_hedge_action": dict(hedge_action),
        "option_strategy": option_strategy_payload,
    }
    return TradingDecisionRecord(
        trading_decision_id=str(uuid.uuid4()),
        candidate_score_id=risk_decision.candidate_score_id,
        trade_classification_id=None,
        risk_decision_id=risk_decision.risk_decision_id,
        ticker=ticker,
        decision=decision_action,
        strategy_id="risk_manager_hedge_overlay_v1",
        strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="risk_hedge_overlay",
        instrument_type="option",
        selection_source="risk_manager",
        manual_request_id=None,
        confidence=1.0,
        target_weight=0.0,
        approved_weight=0.0,
        max_loss_pct=1.0,
        time_horizon="1d-5d",
        thesis="Risk hedge overlay generated from residual portfolio risk.",
        prompt_template=object(),
        prompt_run=None,
        usage_events=[],
        decision_time=trade_date,
        available_for_decision_at=trade_date,
        paper_trade_authorized=True,
        key_drivers=[str(hedge_action.get("reason_code") or "risk_overlay")],
        counterarguments=[],
        invalidators=[],
        context_snapshot_json={
            "generated_by": "risk_manager",
            "source_risk_decision_id": risk_decision.risk_decision_id,
        },
        metadata_json=metadata_json,
    )


def _hedge_risk_decision_from_generated_action(
    *,
    risk_decision: RiskDecisionRecord,
    hedge_action: dict[str, Any],
) -> RiskDecisionRecord:
    underlying_price = max(float(hedge_action.get("underlying_price") or 100.0), 1.0)
    protected_notional = max(float(hedge_action.get("protected_notional") or 0.0), underlying_price * 100.0)
    contracts = max(1.0, round(protected_notional / (underlying_price * 100.0)))
    return RiskDecisionRecord(
        risk_decision_id=risk_decision.risk_decision_id,
        candidate_score_id=risk_decision.candidate_score_id,
        trade_classification_id=None,
        position_sizing_decision_id=risk_decision.position_sizing_decision_id,
        ticker=str(hedge_action.get("target_underlier") or risk_decision.ticker),
        status=risk_decision.status,
        reason_code=str(hedge_action.get("reason_code") or risk_decision.reason_code),
        approved_weight=0.0,
        approved_notional=protected_notional,
        approved_quantity=contracts,
        portfolio_risk_snapshot_id=risk_decision.portfolio_risk_snapshot_id,
        applied_rules=[*list(risk_decision.applied_rules), "generated_risk_hedge_overlay"],
        generated_hedge_action=dict(hedge_action),
        decision_time=risk_decision.decision_time,
        metadata_json=dict(risk_decision.metadata_json),
    )


def _hedge_decision_action(hedge_action: dict[str, Any]) -> str | None:
    action = str(hedge_action.get("action") or "")
    return {
        "open_hedge": "open_option_strategy",
        "close_hedge": "close_option_strategy",
        "adjust_hedge": "adjust_option_strategy",
    }.get(action)


def _generated_hedge_option_strategy_payload(
    *,
    hedge_action: dict[str, Any],
    trade_date: datetime,
) -> dict[str, Any]:
    option_strategy_type = str(hedge_action.get("option_strategy_type") or "long_put")
    underlying_price = max(float(hedge_action.get("underlying_price") or 100.0), 1.0)
    chosen_price = round(max(1.0, underlying_price * 0.02), 2)
    if option_strategy_type == "long_call":
        option_type = "call"
        delta = 0.30
    else:
        option_type = "put"
        delta = -0.30
    strike = round(underlying_price * 0.95, 2) if option_type == "put" else round(underlying_price * 1.05, 2)
    leg_payload = {
        "option_type": option_type,
        "side": "buy",
        "quantity": 1,
        "strike": strike,
        "expiry": trade_date.date().isoformat(),
        "dte": 5,
        "delta": delta,
        "gamma": 0.02,
        "theta": -0.01,
        "vega": 0.05,
        "iv_rank": None,
        "bid": round(chosen_price * 0.95, 2),
        "ask": round(chosen_price * 1.05, 2),
        "mid": chosen_price,
        "chosen_price": chosen_price,
        "implied_volatility": None,
    }
    max_loss = chosen_price * 100.0
    return {
        "option_strategy_decision_id": str(uuid.uuid4()),
        "option_strategy_type": option_strategy_type,
        "status": "ready",
        "rejection_reason": None,
        "underlying_price": underlying_price,
        "net_debit_or_credit": chosen_price,
        "max_loss": max_loss,
        "max_profit": None,
        "breakevens": (),
        "margin_requirement": max_loss,
        "buying_power_effect": max_loss,
        "assignment_notional": 0.0,
        "portfolio_delta": delta,
        "portfolio_gamma": 0.02,
        "portfolio_theta": -0.01,
        "portfolio_vega": 0.05,
        "event_through_expiry": False,
        "strategy_pairing_method": "single_leg",
        "assignment_plan": None,
        "margin_model_profile": "estimated_fidelity_like_conservative_v1",
        "margin_model_version": "v1",
        "margin_requirement_source": "simulated_formula",
        "profit_target_pct": 0.0,
        "max_loss_rule": "",
        "roll_conditions": (),
        "close_conditions": (),
        "metadata_json": {"legs": [leg_payload], "hedge_action": dict(hedge_action)},
    }


def _matching_open_option_position(
    *,
    repository: Any,
    trading_decision: TradingDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
) -> PaperOptionPosition | None:
    positions = getattr(repository, "load_paper_option_positions", lambda: ())()
    hedge_overlay_fallback: PaperOptionPosition | None = None
    for position in positions:
        if position.status != "open":
            continue
        if position.ticker != trading_decision.ticker:
            continue
        if position.trade_identity != trading_decision.trade_identity:
            continue
        if position.strategy_id != trading_decision.strategy_id:
            continue
        if (
            trading_decision.trade_identity == "risk_hedge_overlay"
            and trading_decision.strategy_id == "risk_manager_hedge_overlay_v1"
            and hedge_overlay_fallback is None
        ):
            hedge_overlay_fallback = position
        if position.option_strategy_type != option_decision.option_strategy_type:
            continue
        return position
    return hedge_overlay_fallback


def _build_option_order_request(
    *,
    trading_decision: TradingDecisionRecord,
    risk_decision: RiskDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
    trade_date: datetime,
    existing_position: PaperOptionPosition | None,
) -> PaperOptionOrderRequest | None:
    quantity = max(1, int(round(risk_decision.approved_quantity or 1)))
    open_legs = _paper_option_order_legs_from_decision(option_decision, action=trading_decision.decision)
    close_legs = _paper_option_close_legs_from_position(
        existing_position=existing_position,
        option_decision=option_decision,
    )
    action = trading_decision.decision
    if action == "open_option_strategy":
        return _open_option_order_request(
            trading_decision=trading_decision,
            risk_decision=risk_decision,
            option_decision=option_decision,
            trade_date=trade_date,
            quantity=quantity,
            legs=open_legs,
        )
    if action == "close_option_strategy":
        return _close_option_order_request(
            trading_decision=trading_decision,
            risk_decision=risk_decision,
            option_decision=option_decision,
            trade_date=trade_date,
            quantity=quantity,
            close_legs=close_legs,
        )
    if action in {"roll_option_strategy", "adjust_option_strategy"}:
        if not close_legs or not open_legs:
            return None
        return PaperOptionOrderRequest(
            trading_decision_id=trading_decision.trading_decision_id,
            risk_decision_id=risk_decision.risk_decision_id,
            option_strategy_decision_id=option_decision.option_strategy_decision_id,
            ticker=trading_decision.ticker,
            strategy_id=trading_decision.strategy_id,
            option_strategy_type=option_decision.option_strategy_type,
            action=action,
            trade_date=trade_date.date(),
            quantity=quantity,
            limit_price=option_decision.net_debit_or_credit,
            max_loss=option_decision.max_loss,
            margin_requirement=option_decision.margin_requirement,
            buying_power_effect=option_decision.buying_power_effect,
            trade_identity=trading_decision.trade_identity,
            order_class="mleg",
            legs=tuple([*close_legs, *open_legs]),
        )
    return PaperOptionOrderRequest(
        trading_decision_id=trading_decision.trading_decision_id,
        risk_decision_id=risk_decision.risk_decision_id,
        option_strategy_decision_id=option_decision.option_strategy_decision_id,
        ticker=trading_decision.ticker,
        strategy_id=trading_decision.strategy_id,
        option_strategy_type=option_decision.option_strategy_type,
        action=action,
        trade_date=trade_date.date(),
        quantity=quantity,
        limit_price=option_decision.net_debit_or_credit,
        max_loss=option_decision.max_loss,
        margin_requirement=option_decision.margin_requirement,
        buying_power_effect=option_decision.buying_power_effect,
        trade_identity=trading_decision.trade_identity,
    )


def _open_option_order_request(
    *,
    trading_decision: TradingDecisionRecord,
    risk_decision: RiskDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
    trade_date: datetime,
    quantity: int,
    legs: tuple[PaperOptionOrderLeg, ...],
) -> PaperOptionOrderRequest | None:
    if not legs:
        return None
    shared_kwargs = dict(
        trading_decision_id=trading_decision.trading_decision_id,
        risk_decision_id=risk_decision.risk_decision_id,
        option_strategy_decision_id=option_decision.option_strategy_decision_id,
        ticker=trading_decision.ticker,
        strategy_id=trading_decision.strategy_id,
        option_strategy_type=option_decision.option_strategy_type,
        action=trading_decision.decision,
        trade_date=trade_date.date(),
        quantity=quantity,
        limit_price=option_decision.net_debit_or_credit,
        max_loss=option_decision.max_loss,
        margin_requirement=option_decision.margin_requirement,
        buying_power_effect=option_decision.buying_power_effect,
        trade_identity=trading_decision.trade_identity,
    )
    if len(legs) == 1:
        leg = legs[0]
        return PaperOptionOrderRequest(
            **shared_kwargs,
            contract_symbol=leg.contract_symbol,
            position_intent=leg.position_intent,
        )
    return PaperOptionOrderRequest(
        **shared_kwargs,
        order_class="mleg",
        legs=legs,
    )


def _close_option_order_request(
    *,
    trading_decision: TradingDecisionRecord,
    risk_decision: RiskDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
    trade_date: datetime,
    quantity: int,
    close_legs: tuple[PaperOptionOrderLeg, ...],
) -> PaperOptionOrderRequest | None:
    if not close_legs:
        return None
    shared_kwargs = dict(
        trading_decision_id=trading_decision.trading_decision_id,
        risk_decision_id=risk_decision.risk_decision_id,
        option_strategy_decision_id=option_decision.option_strategy_decision_id,
        ticker=trading_decision.ticker,
        strategy_id=trading_decision.strategy_id,
        option_strategy_type=option_decision.option_strategy_type,
        action=trading_decision.decision,
        trade_date=trade_date.date(),
        quantity=quantity,
        limit_price=option_decision.net_debit_or_credit,
        max_loss=option_decision.max_loss,
        margin_requirement=option_decision.margin_requirement,
        buying_power_effect=option_decision.buying_power_effect,
        trade_identity=trading_decision.trade_identity,
    )
    if len(close_legs) == 1:
        leg = close_legs[0]
        return PaperOptionOrderRequest(
            **shared_kwargs,
            contract_symbol=leg.contract_symbol,
            position_intent=leg.position_intent,
        )
    return PaperOptionOrderRequest(
        **shared_kwargs,
        order_class="mleg",
        legs=close_legs,
    )


def _paper_option_order_legs_from_decision(
    option_decision: OptionStrategyDecisionRecord,
    *,
    action: str,
) -> tuple[PaperOptionOrderLeg, ...]:
    position_intent_map = {
        "buy": "buy_to_open",
        "sell": "sell_to_open",
    }
    legs: list[PaperOptionOrderLeg] = []
    for payload in option_decision.metadata_json.get("legs", []):
        if not isinstance(payload, dict):
            continue
        side = str(payload.get("side") or "")
        position_intent = position_intent_map.get(side)
        if position_intent is None:
            continue
        legs.append(
            PaperOptionOrderLeg(
                contract_symbol=_option_contract_symbol_from_payload(option_decision.ticker, payload),
                ratio_qty=int(payload.get("ratio_qty") or payload.get("quantity") or 1),
                position_intent=position_intent,
            )
        )
    return tuple(legs)


def _paper_option_close_legs_from_position(
    *,
    existing_position: PaperOptionPosition | None,
    option_decision: OptionStrategyDecisionRecord,
) -> tuple[PaperOptionOrderLeg, ...]:
    if existing_position is not None:
        broker_leg_refs = existing_position.metadata_json.get("broker_leg_refs")
        if isinstance(broker_leg_refs, list):
            refs = _paper_option_legs_from_broker_refs(broker_leg_refs, close_existing=True)
            if refs:
                return refs
    fallback_payloads = option_decision.metadata_json.get("legs", [])
    refs: list[PaperOptionOrderLeg] = []
    for payload in fallback_payloads:
        if not isinstance(payload, dict):
            continue
        side = str(payload.get("side") or "")
        if side not in {"buy", "sell"}:
            continue
        refs.append(
            PaperOptionOrderLeg(
                contract_symbol=_option_contract_symbol_from_payload(option_decision.ticker, payload),
                ratio_qty=int(payload.get("ratio_qty") or payload.get("quantity") or 1),
                position_intent="sell_to_close" if side == "buy" else "buy_to_close",
            )
        )
    return tuple(refs)


def _paper_option_legs_from_broker_refs(
    refs_payload: list[Any],
    *,
    close_existing: bool,
) -> tuple[PaperOptionOrderLeg, ...]:
    legs: list[PaperOptionOrderLeg] = []
    for item in refs_payload:
        if not isinstance(item, dict):
            continue
        contract_symbol = item.get("contract_symbol")
        if not isinstance(contract_symbol, str) or not contract_symbol:
            continue
        raw_intent = str(item.get("position_intent") or "")
        if close_existing:
            position_intent = _closing_position_intent(raw_intent)
        else:
            position_intent = raw_intent or "buy_to_open"
        legs.append(
            PaperOptionOrderLeg(
                contract_symbol=contract_symbol,
                ratio_qty=int(item.get("ratio_qty") or 1),
                position_intent=position_intent,
            )
        )
    return tuple(legs)


def _closing_position_intent(raw_intent: str) -> str:
    return {
        "buy_to_open": "sell_to_close",
        "sell_to_open": "buy_to_close",
        "buy_to_close": "buy_to_close",
        "sell_to_close": "sell_to_close",
    }.get(raw_intent, "sell_to_close")


def _option_contract_symbol_from_payload(ticker: str, payload: dict[str, Any]) -> str:
    contract_symbol = payload.get("contract_symbol")
    if isinstance(contract_symbol, str) and contract_symbol:
        return contract_symbol
    expiry = datetime.fromisoformat(str(payload["expiry"])).date()
    option_code = "C" if str(payload.get("option_type")) == "call" else "P"
    strike_component = f"{int(round(float(payload['strike']) * 1000)):08d}"
    return f"{ticker.upper()}{expiry.strftime('%y%m%d')}{option_code}{strike_component}"


def _broker_leg_refs_from_request(request: PaperOptionOrderRequest) -> list[dict[str, Any]]:
    if request.order_class == "mleg":
        return [
            {
                "contract_symbol": leg.contract_symbol,
                "ratio_qty": leg.ratio_qty,
                "position_intent": leg.position_intent,
            }
            for leg in request.legs
        ]
    if request.contract_symbol is None:
        return []
    return [
        {
            "contract_symbol": request.contract_symbol,
            "ratio_qty": 1,
            "position_intent": request.position_intent,
        }
    ]


def _opening_broker_leg_refs_from_request(request: PaperOptionOrderRequest) -> list[dict[str, Any]]:
    refs = _broker_leg_refs_from_request(request)
    open_refs = [item for item in refs if str(item.get("position_intent") or "").endswith("_open")]
    return open_refs or refs


def _risk_hedge_option_strategy_type(
    *,
    trading_decision: TradingDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
    existing_position: PaperOptionPosition | None,
) -> str:
    if (
        trading_decision.trade_identity == "risk_hedge_overlay"
        and existing_position is not None
        and trading_decision.decision in {"close_option_strategy", "adjust_option_strategy"}
    ):
        return existing_position.option_strategy_type
    return option_decision.option_strategy_type


def _materialized_option_positions(
    *,
    trading_decision: TradingDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
    order_request: PaperOptionOrderRequest,
    order: PaperOptionOrderRequest | Any,
    execution: Any,
    existing_position: PaperOptionPosition | None,
) -> tuple[PaperOptionPosition, ...]:
    action = trading_decision.decision
    if action == "close_option_strategy":
        if existing_position is None:
            return ()
        return (
            PaperOptionPosition(
                paper_option_position_id=existing_position.paper_option_position_id,
                option_strategy_decision_id=existing_position.option_strategy_decision_id,
                ticker=existing_position.ticker,
                strategy_id=existing_position.strategy_id,
                option_strategy_type=existing_position.option_strategy_type,
                trade_identity=existing_position.trade_identity,
                quantity=existing_position.quantity,
                opened_at=existing_position.opened_at,
                updated_at=execution.executed_at,
                status="closed",
                expiry=existing_position.expiry,
                max_loss=existing_position.max_loss,
                margin_requirement=0.0,
                buying_power_effect=0.0,
                assignment_notional=0.0,
                metadata_json={
                    **dict(existing_position.metadata_json),
                    "lifecycle_action": action,
                    "closing_order_id": order.paper_option_order_id,
                    "closing_broker_order_id": order.broker_order_id,
                },
            ),
        )
    if action == "roll_option_strategy":
        positions: list[PaperOptionPosition] = []
        if existing_position is not None:
            positions.append(
                PaperOptionPosition(
                    paper_option_position_id=existing_position.paper_option_position_id,
                    option_strategy_decision_id=existing_position.option_strategy_decision_id,
                    ticker=existing_position.ticker,
                    strategy_id=existing_position.strategy_id,
                    option_strategy_type=existing_position.option_strategy_type,
                    trade_identity=existing_position.trade_identity,
                    quantity=existing_position.quantity,
                    opened_at=existing_position.opened_at,
                    updated_at=execution.executed_at,
                    status="closed",
                    expiry=existing_position.expiry,
                    max_loss=existing_position.max_loss,
                    margin_requirement=0.0,
                    buying_power_effect=0.0,
                    assignment_notional=0.0,
                    metadata_json={
                        **dict(existing_position.metadata_json),
                        "lifecycle_action": action,
                        "replacement_order_id": order.paper_option_order_id,
                        "closing_broker_order_id": order.broker_order_id,
                    },
                )
            )
        positions.append(
            PaperOptionPosition(
                paper_option_position_id=order.paper_option_order_id,
                option_strategy_decision_id=option_decision.option_strategy_decision_id,
                ticker=order.ticker,
                strategy_id=order.strategy_id,
                option_strategy_type=order.option_strategy_type,
                trade_identity=order.trade_identity,
                quantity=order.quantity,
                opened_at=execution.executed_at,
                updated_at=execution.executed_at,
                status="open",
                expiry=option_decision.expiry,
                max_loss=option_decision.max_loss,
                margin_requirement=option_decision.margin_requirement,
                buying_power_effect=option_decision.buying_power_effect,
                assignment_notional=option_decision.assignment_notional,
                metadata_json={
                    **dict(option_decision.metadata_json),
                    "lifecycle_action": action,
                    "broker_leg_refs": _opening_broker_leg_refs_from_request(order_request),
                    "opening_broker_order_id": order.broker_order_id,
                    **(
                        {"supersedes_option_position_id": existing_position.paper_option_position_id}
                        if existing_position is not None
                        else {}
                    ),
                },
            )
        )
        return tuple(positions)
    if action == "adjust_option_strategy" and existing_position is not None:
        return (
            PaperOptionPosition(
                paper_option_position_id=existing_position.paper_option_position_id,
                option_strategy_decision_id=option_decision.option_strategy_decision_id,
                ticker=existing_position.ticker,
                strategy_id=existing_position.strategy_id,
                option_strategy_type=existing_position.option_strategy_type,
                trade_identity=existing_position.trade_identity,
                quantity=order.quantity,
                opened_at=existing_position.opened_at,
                updated_at=execution.executed_at,
                status="open",
                expiry=option_decision.expiry,
                max_loss=option_decision.max_loss,
                margin_requirement=option_decision.margin_requirement,
                buying_power_effect=option_decision.buying_power_effect,
                assignment_notional=option_decision.assignment_notional,
                metadata_json={
                    **dict(existing_position.metadata_json),
                    **dict(option_decision.metadata_json),
                    "lifecycle_action": action,
                    "broker_leg_refs": _opening_broker_leg_refs_from_request(order_request),
                    "opening_broker_order_id": order.broker_order_id,
                },
            ),
        )
    return (
        PaperOptionPosition(
            paper_option_position_id=order.paper_option_order_id,
            option_strategy_decision_id=option_decision.option_strategy_decision_id,
            ticker=order.ticker,
            strategy_id=order.strategy_id,
            option_strategy_type=order.option_strategy_type,
            trade_identity=order.trade_identity,
            quantity=order.quantity,
            opened_at=execution.executed_at,
            updated_at=execution.executed_at,
            status="open",
            expiry=option_decision.expiry,
            max_loss=option_decision.max_loss,
            margin_requirement=option_decision.margin_requirement,
            buying_power_effect=option_decision.buying_power_effect,
            assignment_notional=option_decision.assignment_notional,
            metadata_json={
                **dict(option_decision.metadata_json),
                "broker_leg_refs": _opening_broker_leg_refs_from_request(order_request),
                "opening_broker_order_id": order.broker_order_id,
            },
        ),
    )


def _build_execution_fallback_trade_risk_request(
    trading_decision: TradingDecisionRecord,
) -> TradeRiskRequest:
    candidate_context = dict(trading_decision.context_snapshot_json.get("candidate_context") or {})
    risk_context = dict(trading_decision.context_snapshot_json.get("risk_context") or {})
    candidate = SimpleNamespace(
        candidate_score_id=trading_decision.candidate_score_id,
        ticker=trading_decision.ticker,
        candidate_score=float(candidate_context.get("candidate_score", trading_decision.confidence)),
        decision_time=trading_decision.decision_time,
        direction="bullish" if trading_decision.decision != "enter_short" else "bearish",
        strategy_lifecycle_status=_resolve_strategy_lifecycle_status(trading_decision),
    )
    classification = SimpleNamespace(
        trade_classification_id=trading_decision.trade_classification_id,
        trade_identity=trading_decision.trade_identity,
    )
    price = float(
        trading_decision.metadata_json.get("option_strategy", {}).get("underlying_price")
        or risk_context.get("price")
        or 1.0
    )
    return TradeRiskRequest(
        candidate=candidate,
        classification=classification,
        instrument_type="stock",
        target_weight=float(risk_context.get("approved_weight") or trading_decision.approved_weight or trading_decision.target_weight or 0.0),
        confidence=float(trading_decision.confidence),
        sector=None,
        beta_bucket=None,
        volatility_bucket="medium",
        liquidity_bucket="liquid",
        event_type=None,
        macro_sensitivity=None,
        price=price,
        atr_pct=0.0,
        average_daily_dollar_volume=0.0,
        signal_freshness={},
        estimated_margin_requirement=max(price, 1.0),
        estimated_buying_power_effect=max(price, 1.0),
        estimated_initial_margin_requirement=max(price, 1.0),
        estimated_maintenance_margin_requirement=max(price * 0.5, 1.0),
    )


def _option_decision_from_trading_decision(
    *,
    trading_decision: TradingDecisionRecord,
    trade_date: datetime,
) -> OptionStrategyDecisionRecord | None:
    option_strategy_payload = trading_decision.metadata_json.get("option_strategy")
    if not isinstance(option_strategy_payload, dict):
        return None
    return OptionStrategyDecisionRecord(
        option_strategy_decision_id=str(option_strategy_payload["option_strategy_decision_id"]),
        trading_decision_id=trading_decision.trading_decision_id,
        ticker=trading_decision.ticker,
        trade_identity=trading_decision.trade_identity,
        decision_action=trading_decision.decision,
        option_strategy_type=str(option_strategy_payload["option_strategy_type"]),
        status=str(option_strategy_payload.get("status", "ready")),
        rejection_reason=option_strategy_payload.get("rejection_reason"),
        strategy_id=trading_decision.strategy_id,
        strategy_version=trading_decision.strategy_version,
        expression_bucket_id=trading_decision.expression_bucket_id,
        expression_bucket_version=trading_decision.expression_bucket_version,
        underlying_price=float(option_strategy_payload["underlying_price"]),
        expiry=trade_date.date(),
        net_debit_or_credit=float(option_strategy_payload["net_debit_or_credit"]),
        max_loss=float(option_strategy_payload["max_loss"]),
        max_profit=float(option_strategy_payload.get("max_profit")) if option_strategy_payload.get("max_profit") is not None else None,
        breakevens=tuple(float(item) for item in option_strategy_payload.get("breakevens", [])),
        margin_requirement=float(option_strategy_payload["margin_requirement"]),
        buying_power_effect=float(option_strategy_payload["buying_power_effect"]),
        assignment_notional=float(option_strategy_payload.get("assignment_notional", 0.0)),
        portfolio_delta=float(option_strategy_payload.get("portfolio_delta", 0.0)),
        portfolio_gamma=float(option_strategy_payload.get("portfolio_gamma", 0.0)),
        portfolio_theta=float(option_strategy_payload.get("portfolio_theta", 0.0)),
        portfolio_vega=float(option_strategy_payload.get("portfolio_vega", 0.0)),
        earnings_date=None,
        event_through_expiry=bool(option_strategy_payload.get("event_through_expiry", False)),
        strategy_pairing_method=str(option_strategy_payload.get("strategy_pairing_method", "single_leg")),
        assignment_plan=option_strategy_payload.get("assignment_plan"),
        margin_model_profile=str(option_strategy_payload.get("margin_model_profile", "estimated_fidelity_like_conservative_v1")),
        margin_model_version=str(option_strategy_payload.get("margin_model_version", "v1")),
        margin_requirement_source=str(option_strategy_payload.get("margin_requirement_source", "simulated_formula")),
        profit_target_pct=float(option_strategy_payload.get("profit_target_pct", 0.0)),
        max_loss_rule=str(option_strategy_payload.get("max_loss_rule", "")),
        roll_conditions=tuple(option_strategy_payload.get("roll_conditions", [])),
        close_conditions=tuple(option_strategy_payload.get("close_conditions", [])),
        metadata_json=dict(option_strategy_payload.get("metadata_json", {})),
        created_at=trade_date,
    )


def _fallback_option_strategy_payload(
    trading_decision: TradingDecisionRecord,
    *,
    expression_bucket_id: str,
) -> dict[str, Any] | None:
    payload = trading_decision.metadata_json.get("option_strategy_fallbacks", {}).get(expression_bucket_id)
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def _remaining_fallback_expression_bucket_ids(
    trading_decision: TradingDecisionRecord,
) -> list[str]:
    plan = trading_decision.context_snapshot_json.get("classification_context", {}).get("expression_fallback_plan") or []
    current_expression_id = trading_decision.expression_bucket_id
    matched = False
    remaining: list[str] = []
    for item in plan:
        expression_bucket_id = str(item.get("expression_bucket_id") or "")
        if not matched:
            if expression_bucket_id == current_expression_id:
                matched = True
            continue
        if expression_bucket_id:
            remaining.append(expression_bucket_id)
    return remaining


def _build_execution_fallback_option_trade_risk_request(
    trading_decision: TradingDecisionRecord,
) -> TradeRiskRequest:
    candidate_context = dict(trading_decision.context_snapshot_json.get("candidate_context") or {})
    risk_context = dict(trading_decision.context_snapshot_json.get("risk_context") or {})
    option_strategy_payload = dict(trading_decision.metadata_json.get("option_strategy") or {})
    candidate = SimpleNamespace(
        candidate_score_id=trading_decision.candidate_score_id,
        ticker=trading_decision.ticker,
        candidate_score=float(candidate_context.get("candidate_score", trading_decision.confidence)),
        decision_time=trading_decision.decision_time,
        direction="bullish" if trading_decision.decision != "enter_short" else "bearish",
        strategy_lifecycle_status=_resolve_strategy_lifecycle_status(trading_decision),
    )
    classification = SimpleNamespace(
        trade_classification_id=trading_decision.trade_classification_id,
        trade_identity=trading_decision.trade_identity,
    )
    per_contract_price = max(abs(float(option_strategy_payload.get("net_debit_or_credit") or 0.0)) * 100.0, 1.0)
    estimated_margin_requirement = option_strategy_payload.get("margin_requirement")
    estimated_buying_power_effect = option_strategy_payload.get("buying_power_effect")
    return TradeRiskRequest(
        candidate=candidate,
        classification=classification,
        instrument_type="option",
        target_weight=float(risk_context.get("approved_weight") or trading_decision.approved_weight or trading_decision.target_weight or 0.0),
        confidence=float(trading_decision.confidence),
        sector=None,
        beta_bucket=None,
        volatility_bucket="high" if option_strategy_payload.get("event_through_expiry") else "medium",
        liquidity_bucket="liquid",
        event_type=None,
        macro_sensitivity=None,
        price=per_contract_price,
        atr_pct=0.0,
        average_daily_dollar_volume=0.0,
        signal_freshness={},
        estimated_margin_requirement=float(estimated_margin_requirement) if estimated_margin_requirement is not None else None,
        estimated_buying_power_effect=float(estimated_buying_power_effect) if estimated_buying_power_effect is not None else None,
        estimated_initial_margin_requirement=float(estimated_margin_requirement) if estimated_margin_requirement is not None else None,
        estimated_maintenance_margin_requirement=float(estimated_buying_power_effect) if estimated_buying_power_effect is not None else None,
        assignment_notional=float(option_strategy_payload.get("assignment_notional", 0.0)),
        option_risk_metadata_complete=bool(option_strategy_payload.get("metadata_json", {}).get("legs")),
    )


def _build_execution_fallback_option_risk_input(
    option_decision: OptionStrategyDecisionRecord,
    *,
    contracts: int,
) -> OptionRiskInput:
    legs = []
    for payload in option_decision.metadata_json.get("legs", []):
        legs.append(
            OptionLegRiskInput(
                option_type=str(payload["option_type"]),
                side=str(payload["side"]),
                quantity=int(payload["quantity"]) * contracts,
                strike=float(payload["strike"]),
                expiry=datetime.fromisoformat(f"{payload['expiry']}T00:00:00").date(),
                delta=float(payload["delta"]),
                gamma=float(payload["gamma"]),
                theta=float(payload["theta"]),
                vega=float(payload["vega"]),
                premium=float(payload["chosen_price"]),
            )
        )
    return OptionRiskInput(
        ticker=option_decision.ticker,
        trade_identity=option_decision.trade_identity,
        option_strategy_type=option_decision.option_strategy_type,
        underlying_price=option_decision.underlying_price,
        sector=None,
        event_type=None,
        event_through_expiry=option_decision.event_through_expiry,
        margin_requirement=option_decision.margin_requirement * contracts,
        buying_power_effect=option_decision.buying_power_effect * contracts,
        max_loss=option_decision.max_loss * contracts,
        max_profit=option_decision.max_profit * contracts if option_decision.max_profit is not None else None,
        net_debit_or_credit=option_decision.net_debit_or_credit * contracts,
        legs=tuple(legs),
    )


def _resolve_strategy_lifecycle_status(trading_decision: TradingDecisionRecord) -> str:
    metadata_value = str(trading_decision.metadata_json.get("strategy_lifecycle_status") or "").strip()
    if metadata_value:
        return metadata_value
    candidate_context = dict(trading_decision.context_snapshot_json.get("candidate_context") or {})
    candidate_value = str(candidate_context.get("strategy_lifecycle_status") or "").strip()
    if candidate_value:
        return candidate_value
    for row in load_all_trading_definitions():
        if str(row.get("strategy_id") or "") != trading_decision.strategy_id:
            continue
        version = str(row.get("version") or row.get("strategy_version") or "").strip()
        if version and version != trading_decision.strategy_version:
            continue
        lifecycle_status = str(row.get("lifecycle_status") or "").strip()
        if lifecycle_status:
            return lifecycle_status
    return "active"
