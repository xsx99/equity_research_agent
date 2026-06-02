"""Whitelisted paper option strategy builder for PR7."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


_WHITELIST = {
    "long_call",
    "long_put",
    "put_credit_spread",
    "call_credit_spread",
    "long_straddle",
    "long_strangle",
}


@dataclass(frozen=True)
class OptionLegDefinition:
    option_type: str
    side: str
    quantity: int
    strike: float
    expiry: date
    dte: int
    delta: float
    gamma: float
    theta: float
    vega: float
    iv_rank: float | None
    bid: float
    ask: float
    mid: float
    chosen_price: float


@dataclass(frozen=True)
class OptionStrategyDecisionInput:
    trading_decision_id: str
    ticker: str
    trade_identity: str
    option_strategy_type: str
    decision_action: str
    strategy_id: str
    strategy_version: str
    expression_bucket_id: str
    expression_bucket_version: str
    decision_time: datetime
    expiry: date
    underlying_price: float
    earnings_date: date | None
    event_through_expiry: bool
    profit_target_pct: float
    max_loss_rule: str
    roll_conditions: tuple[str, ...] | list[str]
    close_conditions: tuple[str, ...] | list[str]
    margin_model_profile: str
    margin_model_version: str
    margin_requirement_source: str
    strategy_pairing_method: str
    assignment_plan: str | None
    legs: tuple[OptionLegDefinition, ...] | list[OptionLegDefinition]


@dataclass(frozen=True)
class OptionStrategyDecisionRecord:
    option_strategy_decision_id: str
    trading_decision_id: str
    ticker: str
    trade_identity: str
    decision_action: str
    option_strategy_type: str
    status: str
    rejection_reason: str | None
    strategy_id: str
    strategy_version: str
    expression_bucket_id: str
    expression_bucket_version: str
    underlying_price: float
    expiry: date
    net_debit_or_credit: float
    max_loss: float
    max_profit: float | None
    breakevens: tuple[float, ...]
    margin_requirement: float
    buying_power_effect: float
    assignment_notional: float
    portfolio_delta: float
    portfolio_gamma: float
    portfolio_theta: float
    portfolio_vega: float
    earnings_date: date | None
    event_through_expiry: bool
    strategy_pairing_method: str
    assignment_plan: str | None
    margin_model_profile: str
    margin_model_version: str
    margin_requirement_source: str
    profit_target_pct: float
    max_loss_rule: str
    roll_conditions: tuple[str, ...]
    close_conditions: tuple[str, ...]
    metadata_json: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class OptionStrategyLegRecord:
    option_strategy_leg_id: str
    option_strategy_decision_id: str
    ticker: str
    option_type: str
    side: str
    quantity: int
    strike: float
    expiry: date
    dte: int
    delta: float
    gamma: float
    theta: float
    vega: float
    iv_rank: float | None
    bid: float
    ask: float
    mid: float
    chosen_price: float
    created_at: datetime


class OptionsStrategyLayer:
    """Validate PR7 whitelist and derive strategy-level option risk primitives."""

    def build_strategy(self, input_data: OptionStrategyDecisionInput) -> OptionStrategyDecisionRecord:
        legs = tuple(input_data.legs)
        if input_data.option_strategy_type not in _WHITELIST:
            return self._rejected(input_data, "unsupported_option_strategy_type")
        if not legs:
            return self._rejected(input_data, "missing_option_legs")
        if any(leg.bid <= 0 or leg.ask <= 0 or leg.chosen_price <= 0 for leg in legs):
            return self._rejected(input_data, "missing_leg_pricing")
        if any(leg.expiry != input_data.expiry for leg in legs):
            return self._rejected(input_data, "mixed_expiry_not_supported")
        if any(leg.option_type not in {"call", "put"} or leg.side not in {"buy", "sell"} for leg in legs):
            return self._rejected(input_data, "invalid_leg_definition")

        net_debit_or_credit = sum(
            leg.chosen_price * leg.quantity * (1 if leg.side == "buy" else -1)
            for leg in legs
        )
        assignment_notional = sum(
            leg.strike * leg.quantity * 100.0
            for leg in legs
            if leg.side == "sell"
        )
        max_loss, max_profit = _max_loss_profit(input_data.option_strategy_type, legs, net_debit_or_credit)
        margin_requirement = _margin_requirement(input_data.option_strategy_type, max_loss, net_debit_or_credit)
        portfolio_delta = sum(leg.delta * leg.quantity * (1 if leg.side == "buy" else -1) for leg in legs)
        portfolio_gamma = sum(leg.gamma * leg.quantity * (1 if leg.side == "buy" else -1) for leg in legs)
        portfolio_theta = sum(leg.theta * leg.quantity * (1 if leg.side == "buy" else -1) for leg in legs)
        portfolio_vega = sum(leg.vega * leg.quantity * (1 if leg.side == "buy" else -1) for leg in legs)

        return OptionStrategyDecisionRecord(
            option_strategy_decision_id=str(uuid.uuid4()),
            trading_decision_id=input_data.trading_decision_id,
            ticker=input_data.ticker,
            trade_identity=input_data.trade_identity,
            decision_action=input_data.decision_action,
            option_strategy_type=input_data.option_strategy_type,
            status="ready",
            rejection_reason=None,
            strategy_id=input_data.strategy_id,
            strategy_version=input_data.strategy_version,
            expression_bucket_id=input_data.expression_bucket_id,
            expression_bucket_version=input_data.expression_bucket_version,
            underlying_price=input_data.underlying_price,
            expiry=input_data.expiry,
            net_debit_or_credit=net_debit_or_credit,
            max_loss=max_loss,
            max_profit=max_profit,
            breakevens=_breakevens(input_data.option_strategy_type, input_data.underlying_price, legs, net_debit_or_credit),
            margin_requirement=margin_requirement,
            buying_power_effect=margin_requirement,
            assignment_notional=assignment_notional,
            portfolio_delta=portfolio_delta,
            portfolio_gamma=portfolio_gamma,
            portfolio_theta=portfolio_theta,
            portfolio_vega=portfolio_vega,
            earnings_date=input_data.earnings_date,
            event_through_expiry=input_data.event_through_expiry,
            strategy_pairing_method=input_data.strategy_pairing_method,
            assignment_plan=input_data.assignment_plan,
            margin_model_profile=input_data.margin_model_profile,
            margin_model_version=input_data.margin_model_version,
            margin_requirement_source=input_data.margin_requirement_source,
            profit_target_pct=input_data.profit_target_pct,
            max_loss_rule=input_data.max_loss_rule,
            roll_conditions=tuple(input_data.roll_conditions),
            close_conditions=tuple(input_data.close_conditions),
            metadata_json={"legs": [_serialize_leg(leg) for leg in legs]},
            created_at=input_data.decision_time,
        )

    def build_legs(self, decision: OptionStrategyDecisionRecord) -> tuple[OptionStrategyLegRecord, ...]:
        records: list[OptionStrategyLegRecord] = []
        for payload in decision.metadata_json.get("legs", []):
            records.append(
                OptionStrategyLegRecord(
                    option_strategy_leg_id=str(uuid.uuid4()),
                    option_strategy_decision_id=decision.option_strategy_decision_id,
                    ticker=decision.ticker,
                    option_type=str(payload["option_type"]),
                    side=str(payload["side"]),
                    quantity=int(payload["quantity"]),
                    strike=float(payload["strike"]),
                    expiry=date.fromisoformat(str(payload["expiry"])),
                    dte=int(payload["dte"]),
                    delta=float(payload["delta"]),
                    gamma=float(payload["gamma"]),
                    theta=float(payload["theta"]),
                    vega=float(payload["vega"]),
                    iv_rank=float(payload["iv_rank"]) if payload.get("iv_rank") is not None else None,
                    bid=float(payload["bid"]),
                    ask=float(payload["ask"]),
                    mid=float(payload["mid"]),
                    chosen_price=float(payload["chosen_price"]),
                    created_at=decision.created_at,
                )
            )
        return tuple(records)

    def _rejected(self, input_data: OptionStrategyDecisionInput, reason: str) -> OptionStrategyDecisionRecord:
        return OptionStrategyDecisionRecord(
            option_strategy_decision_id=str(uuid.uuid4()),
            trading_decision_id=input_data.trading_decision_id,
            ticker=input_data.ticker,
            trade_identity=input_data.trade_identity,
            decision_action=input_data.decision_action,
            option_strategy_type=input_data.option_strategy_type,
            status="rejected",
            rejection_reason=reason,
            strategy_id=input_data.strategy_id,
            strategy_version=input_data.strategy_version,
            expression_bucket_id=input_data.expression_bucket_id,
            expression_bucket_version=input_data.expression_bucket_version,
            underlying_price=input_data.underlying_price,
            expiry=input_data.expiry,
            net_debit_or_credit=0.0,
            max_loss=0.0,
            max_profit=None,
            breakevens=(),
            margin_requirement=0.0,
            buying_power_effect=0.0,
            assignment_notional=0.0,
            portfolio_delta=0.0,
            portfolio_gamma=0.0,
            portfolio_theta=0.0,
            portfolio_vega=0.0,
            earnings_date=input_data.earnings_date,
            event_through_expiry=input_data.event_through_expiry,
            strategy_pairing_method=input_data.strategy_pairing_method,
            assignment_plan=input_data.assignment_plan,
            margin_model_profile=input_data.margin_model_profile,
            margin_model_version=input_data.margin_model_version,
            margin_requirement_source=input_data.margin_requirement_source,
            profit_target_pct=input_data.profit_target_pct,
            max_loss_rule=input_data.max_loss_rule,
            roll_conditions=tuple(input_data.roll_conditions),
            close_conditions=tuple(input_data.close_conditions),
            metadata_json={},
            created_at=input_data.decision_time,
        )


def _serialize_leg(leg: OptionLegDefinition) -> dict[str, Any]:
    return {
        "option_type": leg.option_type,
        "side": leg.side,
        "quantity": leg.quantity,
        "strike": leg.strike,
        "expiry": leg.expiry.isoformat(),
        "dte": leg.dte,
        "delta": leg.delta,
        "gamma": leg.gamma,
        "theta": leg.theta,
        "vega": leg.vega,
        "iv_rank": leg.iv_rank,
        "bid": leg.bid,
        "ask": leg.ask,
        "mid": leg.mid,
        "chosen_price": leg.chosen_price,
    }


def _premium_abs(net_debit_or_credit: float) -> float:
    return abs(net_debit_or_credit) * 100.0


def _max_loss_profit(strategy_type: str, legs: tuple[OptionLegDefinition, ...], net_debit_or_credit: float) -> tuple[float, float | None]:
    if strategy_type in {"long_call", "long_put", "long_straddle", "long_strangle"}:
        premium = _premium_abs(net_debit_or_credit)
        return premium, None
    width = abs(max(leg.strike for leg in legs) - min(leg.strike for leg in legs)) * 100.0
    credit = abs(min(net_debit_or_credit, 0.0)) * 100.0
    return max(width - credit, 0.0), credit


def _margin_requirement(strategy_type: str, max_loss: float, net_debit_or_credit: float) -> float:
    if strategy_type in {"long_call", "long_put", "long_straddle", "long_strangle"}:
        return _premium_abs(net_debit_or_credit)
    return max_loss


def _breakevens(
    strategy_type: str,
    underlying_price: float,
    legs: tuple[OptionLegDefinition, ...],
    net_debit_or_credit: float,
) -> tuple[float, ...]:
    if strategy_type == "long_call":
        strike = legs[0].strike
        return (strike + abs(net_debit_or_credit),)
    if strategy_type == "long_put":
        strike = legs[0].strike
        return (strike - abs(net_debit_or_credit),)
    if strategy_type in {"put_credit_spread", "call_credit_spread"}:
        short_strike = next(leg.strike for leg in legs if leg.side == "sell")
        credit = abs(min(net_debit_or_credit, 0.0))
        if strategy_type == "put_credit_spread":
            return (short_strike - credit,)
        return (short_strike + credit,)
    if strategy_type == "long_straddle":
        strike = legs[0].strike
        premium = abs(net_debit_or_credit)
        return (strike - premium, strike + premium)
    if strategy_type == "long_strangle":
        put_strike = min(leg.strike for leg in legs if leg.option_type == "put")
        call_strike = max(leg.strike for leg in legs if leg.option_type == "call")
        premium = abs(net_debit_or_credit)
        return (put_strike - premium, call_strike + premium)
    return (underlying_price,)
