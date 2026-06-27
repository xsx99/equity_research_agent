"""Option chain and leg-selection helpers for option strategy payload construction."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from src.trading.options.strategy import OptionLegDefinition
from src.trading.signals import SignalSnapshotResult
from src.trading.signals.sources import SourceRecord
from src.trading.strategies.matching import StrategyDefinitionRecord
from src.trading.workflows.option_strategy_builder_policy import _expression_option_policy


def _infer_option_underlying_price(signal_snapshot: SignalSnapshotResult) -> float:
    technical = dict(signal_snapshot.signal_json.get("technical") or {})
    for field in ("last_price", "latest_close"):
        value = technical.get(field)
        if isinstance(value, (int, float)) and float(value) > 0:
            return float(value)
    return 100.0


def _build_option_leg_definitions(
    *,
    option_strategy_type: str,
    underlying_price: float,
    expiry: datetime.date,
    dte: int,
    direction: str,
    option_policy: dict[str, Any],
) -> tuple[OptionLegDefinition, ...]:
    def _leg(
        *,
        option_type: str,
        side: str,
        strike: float,
        delta: float,
        bid: float,
        ask: float,
    ) -> OptionLegDefinition:
        chosen = round((bid + ask) / 2.0, 2)
        return OptionLegDefinition(
            option_type=option_type,
            side=side,
            quantity=1,
            strike=round(strike, 2),
            expiry=expiry,
            dte=dte,
            delta=delta,
            gamma=0.03,
            theta=-0.02 if side == "buy" else 0.02,
            vega=0.1 if side == "buy" else -0.08,
            iv_rank=0.62,
            bid=bid,
            ask=ask,
            mid=chosen,
            chosen_price=chosen,
            implied_volatility=0.35,
        )

    direction = str(direction or "").lower()
    if option_strategy_type == "long_call":
        return (
            _leg(
                option_type="call",
                side="buy",
                strike=underlying_price * _policy_float(option_policy, "long_call_strike_pct_above_spot", 1.05, multiplier_default=True),
                delta=_policy_float(option_policy, "long_call_target_delta", 0.35),
                bid=2.2,
                ask=2.4,
            ),
        )
    if option_strategy_type == "long_put":
        return (
            _leg(
                option_type="put",
                side="buy",
                strike=underlying_price * _policy_float(option_policy, "long_put_strike_pct_below_spot", 0.95, multiplier_default=False),
                delta=_policy_float(option_policy, "long_put_target_delta", -0.35),
                bid=2.2,
                ask=2.4,
            ),
        )
    if option_strategy_type == "put_credit_spread":
        return (
            _leg(
                option_type="put",
                side="sell",
                strike=underlying_price * _policy_float(option_policy, "short_put_strike_pct_below_spot", 0.97, multiplier_default=False),
                delta=-abs(_policy_float(option_policy, "short_leg_target_delta_abs", 0.28)),
                bid=2.4,
                ask=2.6,
            ),
            _leg(
                option_type="put",
                side="buy",
                strike=underlying_price * _policy_float(option_policy, "long_put_strike_pct_below_spot", 0.92, multiplier_default=False),
                delta=-abs(_policy_float(option_policy, "long_leg_target_delta_abs", 0.12)),
                bid=1.0,
                ask=1.2,
            ),
        )
    if option_strategy_type == "call_credit_spread":
        return (
            _leg(
                option_type="call",
                side="sell",
                strike=underlying_price * _policy_float(option_policy, "short_call_strike_pct_above_spot", 1.03, multiplier_default=True),
                delta=abs(_policy_float(option_policy, "short_leg_target_delta_abs", 0.28)),
                bid=2.4,
                ask=2.6,
            ),
            _leg(
                option_type="call",
                side="buy",
                strike=underlying_price * _policy_float(option_policy, "long_call_strike_pct_above_spot", 1.08, multiplier_default=True),
                delta=abs(_policy_float(option_policy, "long_leg_target_delta_abs", 0.12)),
                bid=1.0,
                ask=1.2,
            ),
        )
    if option_strategy_type == "long_straddle":
        straddle_delta = abs(_policy_float(option_policy, "straddle_target_delta_abs", 0.24))
        return (
            _leg(option_type="call", side="buy", strike=underlying_price, delta=straddle_delta, bid=1.4, ask=1.6),
            _leg(option_type="put", side="buy", strike=underlying_price, delta=-straddle_delta, bid=1.4, ask=1.6),
        )
    if option_strategy_type == "long_strangle":
        call_key = (
            "strangle_call_strike_pct_above_spot_bullish"
            if direction == "bullish"
            else "strangle_call_strike_pct_above_spot_default"
        )
        put_key = (
            "strangle_put_strike_pct_below_spot_bearish"
            if direction == "bearish"
            else "strangle_put_strike_pct_below_spot_default"
        )
        call_default = 1.04 if direction == "bullish" else 1.03
        put_default = 0.96 if direction == "bearish" else 0.97
        call_strike = underlying_price * _policy_float(option_policy, call_key, call_default, multiplier_default=True)
        put_strike = underlying_price * _policy_float(option_policy, put_key, put_default, multiplier_default=False)
        return (
            _leg(
                option_type="call",
                side="buy",
                strike=call_strike,
                delta=_policy_float(option_policy, "strangle_call_target_delta", 0.26),
                bid=1.4,
                ask=1.6,
            ),
            _leg(
                option_type="put",
                side="buy",
                strike=put_strike,
                delta=_policy_float(option_policy, "strangle_put_target_delta", -0.14),
                bid=1.4,
                ask=1.6,
            ),
        )
    return ()


def _policy_float(
    option_policy: dict[str, Any],
    key: str,
    default: float,
    *,
    multiplier_default: bool | None = None,
) -> float:
    value = option_policy.get(key)
    if isinstance(value, (int, float)):
        number = float(value)
        if multiplier_default is True and 0 < number < 1:
            return 1.0 + number
        if multiplier_default is False and 0 < number < 1:
            return 1.0 - number
        return number
    return default


def _select_option_chain_legs(
    *,
    desired_legs: tuple[OptionLegDefinition, ...],
    option_chain_rows: tuple[SourceRecord, ...],
    expected_expiry: datetime.date,
    expression_bucket_id: str,
    expression_definition: StrategyDefinitionRecord,
) -> tuple[OptionLegDefinition, ...] | None:
    contracts = _flatten_option_chain_contracts(option_chain_rows)
    if not contracts:
        return None
    option_policy = _expression_option_policy(
        expression_bucket_id=expression_bucket_id,
        expression_definition=expression_definition,
    )
    remaining = list(contracts)
    selected: list[OptionLegDefinition] = []
    for desired_leg in desired_legs:
        candidates = [
            contract
            for contract in remaining
            if str(contract.get("option_type")) == desired_leg.option_type
        ]
        if not candidates:
            return None
        best = min(
            candidates,
            key=lambda contract: _option_chain_contract_score(
                contract=contract,
                desired_leg=desired_leg,
                expected_expiry=expected_expiry,
                option_policy=option_policy,
            ),
        )
        selected.append(_option_leg_from_chain_contract(best, desired_leg))
        remaining.remove(best)
    return tuple(selected)


def _option_iv_context(
    *,
    legs: tuple[OptionLegDefinition, ...],
    iv_required: bool,
    used_option_chain: bool,
) -> dict[str, Any]:
    missing_leg_count = sum(1 for leg in legs if leg.implied_volatility is None)
    if missing_leg_count == 0:
        return {
            "iv_required": iv_required,
            "mode": "present",
            "used_option_chain": used_option_chain,
            "missing_leg_count": 0,
        }
    return {
        "iv_required": iv_required,
        "mode": (
            "rejected_missing_implied_volatility"
            if iv_required and used_option_chain
            else "degraded_missing_implied_volatility"
        ),
        "used_option_chain": used_option_chain,
        "missing_leg_count": missing_leg_count,
    }


def _flatten_option_chain_contracts(
    option_chain_rows: tuple[SourceRecord, ...],
) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for row in option_chain_rows:
        payload = dict(row.payload or {})
        items = payload.get("contracts")
        if isinstance(items, list):
            for contract in items:
                if isinstance(contract, dict):
                    contracts.append(dict(contract))
            continue
        if payload.get("option_type") in {"call", "put"}:
            contracts.append(payload)
    return [contract for contract in contracts if _is_viable_option_chain_contract(contract)]


def _is_viable_option_chain_contract(contract: dict[str, Any]) -> bool:
    bid = contract.get("bid")
    ask = contract.get("ask")
    if not isinstance(bid, (int, float)) or not isinstance(ask, (int, float)):
        return False
    if float(bid) <= 0 or float(ask) <= 0 or float(ask) < float(bid):
        return False
    open_interest = contract.get("open_interest")
    volume = contract.get("volume")
    oi_ok = isinstance(open_interest, (int, float)) and float(open_interest) > 0
    volume_ok = isinstance(volume, (int, float)) and float(volume) > 0
    return oi_ok or volume_ok


def _option_chain_contract_score(
    *,
    contract: dict[str, Any],
    desired_leg: OptionLegDefinition,
    expected_expiry: datetime.date,
    option_policy: dict[str, Any],
) -> float:
    expiry = _contract_expiry(contract)
    expiry_penalty = abs((expiry - expected_expiry).days) * 100.0
    strike = float(contract.get("strike") or 0.0)
    delta = float(contract.get("delta") or 0.0)
    strike_penalty = abs(strike - desired_leg.strike)
    delta_penalty = abs(delta - desired_leg.delta) * 100.0
    score = expiry_penalty + strike_penalty + delta_penalty
    if option_policy.get("prefer_higher_vega"):
        vega = contract.get("vega")
        if isinstance(vega, (int, float)):
            score -= float(vega) * 100.0
    if option_policy.get("prefer_higher_implied_volatility"):
        implied_volatility = contract.get("implied_volatility")
        if isinstance(implied_volatility, (int, float)):
            score -= float(implied_volatility) * 10.0
    return score


def _option_leg_from_chain_contract(
    contract: dict[str, Any],
    desired_leg: OptionLegDefinition,
) -> OptionLegDefinition:
    bid = float(contract.get("bid") or 0.0)
    ask = float(contract.get("ask") or 0.0)
    mid = float(contract.get("mid") or round((bid + ask) / 2.0, 2))
    chosen_price = float(contract.get("chosen_price") or mid)
    expiry = _contract_expiry(contract)
    return OptionLegDefinition(
        option_type=str(contract["option_type"]),
        side=desired_leg.side,
        quantity=desired_leg.quantity,
        strike=float(contract["strike"]),
        expiry=expiry,
        dte=int(contract.get("dte") or desired_leg.dte),
        delta=float(contract.get("delta") or desired_leg.delta),
        gamma=float(contract.get("gamma") or desired_leg.gamma),
        theta=float(contract.get("theta") or desired_leg.theta),
        vega=float(contract.get("vega") or desired_leg.vega),
        iv_rank=float(contract["iv_rank"]) if contract.get("iv_rank") is not None else None,
        bid=bid,
        ask=ask,
        mid=mid,
        chosen_price=chosen_price,
        implied_volatility=(
            float(contract["implied_volatility"])
            if contract.get("implied_volatility") is not None
            else None
        ),
    )


def _contract_expiry(contract: dict[str, Any]) -> datetime.date:
    raw = contract.get("expiry")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, str):
        return datetime.fromisoformat(raw).date()
    return datetime.utcnow().date()
