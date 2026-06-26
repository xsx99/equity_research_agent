"""Option strategy helper functions for the trading decision workflow."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any

from src.trading.options.strategy import (
    OptionLegDefinition,
    OptionStrategyDecisionInput,
    OptionStrategyDecisionRecord,
    OptionsStrategyLayer,
)
from src.trading.signals import SignalSnapshotResult
from src.trading.signals.sources import EventNewsItemRecord, SourceRecord
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord


def _render_news_source_text(item: EventNewsItemRecord) -> str:
    parts = [part.strip() for part in (item.headline, item.summary) if isinstance(part, str) and part.strip()]
    return "\n\n".join(parts)


def _classification_instrument_type(classification: TradeClassificationRecord) -> str:
    if classification.trade_identity == "watch_only":
        return "watch"
    if classification.trade_identity == "tactical_option_trade":
        return "option"
    return "stock"


def _resolve_expression_fallback_plan(
    candidate: CandidateScoreRecord,
    classification: TradeClassificationRecord,
    expression_definitions: dict[str, StrategyDefinitionRecord],
) -> list[dict[str, Any]]:
    context = dict(classification.selected_strategy_context_json or {})
    selected_id = str(context.get("selected_expression_bucket_id") or classification.expression_bucket_id)
    fallback_ids = [
        str(item)
        for item in (context.get("fallback_expression_bucket_ids") or [])
        if str(item) != selected_id
    ]
    ordered_ids = [selected_id, *fallback_ids]
    plan: list[dict[str, Any]] = []
    for rank, expression_id in enumerate(ordered_ids):
        definition = expression_definitions.get(expression_id)
        if definition is not None:
            trade_identity = str(
                definition.config_json.get("default_trade_identity")
                or (classification.trade_identity if rank == 0 else "")
            )
            version = definition.version
            instrument_type = _instrument_type_for_expression_definition(definition, trade_identity)
        else:
            trade_identity = classification.trade_identity if rank == 0 else ""
            version = classification.expression_bucket_version if rank == 0 else "unknown"
            instrument_type = _instrument_type_from_trade_identity(trade_identity)
        plan.append(
            {
                "expression_bucket_id": expression_id,
                "expression_bucket_version": version,
                "trade_identity": trade_identity,
                "instrument_type": instrument_type,
                "decision_action": _decision_action_for_expression(
                    candidate.action,
                    instrument_type,
                    trade_identity,
                ),
                "rank": rank,
                "is_selected": rank == 0,
            }
        )
    return plan


def _instrument_type_for_expression_definition(
    definition: StrategyDefinitionRecord,
    trade_identity: str,
) -> str:
    allowed_instruments = {
        str(item)
        for item in (definition.config_json.get("allowed_instruments") or [])
    }
    if "paper_option_strategy" in allowed_instruments:
        return "option"
    if "common_stock" in allowed_instruments:
        return "stock"
    return _instrument_type_from_trade_identity(trade_identity)


def _instrument_type_from_trade_identity(trade_identity: str) -> str:
    if trade_identity == "watch_only":
        return "watch"
    if trade_identity == "tactical_option_trade":
        return "option"
    return "stock"


def _decision_action_for_expression(
    candidate_action: str,
    instrument_type: str,
    trade_identity: str,
) -> str:
    if instrument_type == "option" or trade_identity == "tactical_option_trade":
        return "open_option_strategy"
    action = str(candidate_action or "").strip().lower()
    if action == "trim":
        return "reduce"
    if action == "add":
        return "enter_long"
    if action in {"enter_long", "enter_short", "reduce", "exit", "no_trade", "hold"}:
        return action
    return "enter_long"


def _build_option_strategy_payloads(
    *,
    candidate: CandidateScoreRecord,
    classification: TradeClassificationRecord,
    signal_snapshot: SignalSnapshotResult,
    option_chain_rows: tuple[SourceRecord, ...],
    expression_fallback_plan: list[dict[str, Any]],
    expression_definitions: dict[str, StrategyDefinitionRecord],
    decision_action: str,
    instrument_type: str,
    options_strategy_layer: OptionsStrategyLayer,
) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    if instrument_type != "option" or decision_action not in {
        "open_option_strategy",
        "close_option_strategy",
        "roll_option_strategy",
        "adjust_option_strategy",
    }:
        return None, {}
    selected_payload: dict[str, Any] | None = None
    fallback_payloads: dict[str, dict[str, Any]] = {}
    for plan in expression_fallback_plan:
        if str(plan.get("instrument_type")) != "option":
            continue
        expression_bucket_id = str(plan.get("expression_bucket_id") or "")
        definition = expression_definitions.get(expression_bucket_id)
        if definition is None:
            continue
        payload = _build_option_strategy_payload(
            candidate=candidate,
            classification=classification,
            signal_snapshot=signal_snapshot,
            option_chain_rows=option_chain_rows,
            expression_bucket_id=expression_bucket_id,
            expression_bucket_version=str(plan.get("expression_bucket_version") or classification.expression_bucket_version),
            trade_identity=str(plan.get("trade_identity") or classification.trade_identity),
            decision_action=str(plan.get("decision_action") or decision_action),
            expression_definition=definition,
            options_strategy_layer=options_strategy_layer,
        )
        if payload is None:
            continue
        if bool(plan.get("is_selected")):
            selected_payload = payload
        else:
            fallback_payloads[expression_bucket_id] = payload
    return selected_payload, fallback_payloads


def _build_option_strategy_payload(
    *,
    candidate: CandidateScoreRecord,
    classification: TradeClassificationRecord,
    signal_snapshot: SignalSnapshotResult,
    option_chain_rows: tuple[SourceRecord, ...],
    expression_bucket_id: str,
    expression_bucket_version: str,
    trade_identity: str,
    decision_action: str,
    expression_definition: StrategyDefinitionRecord,
    options_strategy_layer: OptionsStrategyLayer,
) -> dict[str, Any] | None:
    event_through_expiry = _event_through_expiry(signal_snapshot)
    option_policy = _expression_option_policy(
        expression_bucket_id=expression_bucket_id,
        expression_definition=expression_definition,
    )
    option_strategy_type = _choose_option_strategy_type(
        expression_bucket_id=expression_bucket_id,
        expression_definition=expression_definition,
        direction=candidate.direction,
        event_through_expiry=event_through_expiry,
    )
    if option_strategy_type is None:
        return None
    underlying_price = _infer_option_underlying_price(signal_snapshot)
    dte = _option_days_to_expiry(
        option_strategy_type=option_strategy_type,
        option_policy=option_policy,
        event_through_expiry=event_through_expiry,
    )
    expiry = candidate.decision_time.date() + timedelta(days=dte)
    desired_legs = _build_option_leg_definitions(
        option_strategy_type=option_strategy_type,
        underlying_price=underlying_price,
        expiry=expiry,
        dte=dte,
        direction=candidate.direction,
        option_policy=option_policy,
    )
    chain_legs = _select_option_chain_legs(
        desired_legs=desired_legs,
        option_chain_rows=option_chain_rows,
        expected_expiry=expiry,
        expression_bucket_id=expression_bucket_id,
        expression_definition=expression_definition,
    )
    if option_chain_rows and chain_legs is None:
        return _reject_option_payload(
            reason="missing_option_chain",
            option_strategy_type=option_strategy_type,
            underlying_price=underlying_price,
            event_through_expiry=event_through_expiry,
            metadata={"payload_generation_mode": "option_chain_snapshot"},
        )
    selected_legs = chain_legs or desired_legs
    selected_expiry = chain_legs[0].expiry if chain_legs else expiry
    iv_context = _option_iv_context(
        legs=selected_legs,
        iv_required=_expression_requires_implied_volatility(
            expression_bucket_id=expression_bucket_id,
            expression_definition=expression_definition,
        ),
        used_option_chain=chain_legs is not None,
    )
    if iv_context["mode"] == "rejected_missing_implied_volatility":
        return _reject_option_payload(
            reason="iv_data_required",
            option_strategy_type=option_strategy_type,
            underlying_price=underlying_price,
            event_through_expiry=event_through_expiry,
            metadata={
                "payload_generation_mode": "option_chain_snapshot",
                "iv_context": iv_context,
            },
        )
    decision = options_strategy_layer.build_strategy(
        OptionStrategyDecisionInput(
            trading_decision_id=str(uuid.uuid4()),
            ticker=candidate.ticker,
            trade_identity=trade_identity,
            option_strategy_type=option_strategy_type,
            decision_action=decision_action,
            strategy_id=candidate.strategy_id,
            strategy_version=candidate.strategy_version,
            expression_bucket_id=expression_bucket_id,
            expression_bucket_version=expression_bucket_version,
            decision_time=candidate.decision_time,
            expiry=selected_expiry,
            underlying_price=underlying_price,
            earnings_date=selected_expiry if event_through_expiry else None,
            event_through_expiry=event_through_expiry,
            profit_target_pct=_option_profit_target_pct(
                option_strategy_type=option_strategy_type,
                option_policy=option_policy,
            ),
            max_loss_rule=_option_max_loss_rule(
                option_strategy_type=option_strategy_type,
                option_policy=option_policy,
            ),
            roll_conditions=_option_roll_conditions(
                option_strategy_type=option_strategy_type,
                option_policy=option_policy,
            ),
            close_conditions=_option_close_conditions(
                option_strategy_type=option_strategy_type,
                option_policy=option_policy,
            ),
            margin_model_profile="estimated_fidelity_like_conservative_v1",
            margin_model_version="v1",
            margin_requirement_source="simulated_formula",
            strategy_pairing_method=_option_strategy_pairing_method(
                option_strategy_type=option_strategy_type,
                option_policy=option_policy,
            ),
            assignment_plan=_option_assignment_plan(
                option_strategy_type=option_strategy_type,
                option_policy=option_policy,
            ),
            legs=selected_legs,
        )
    )
    payload = _apply_expression_policy_to_option_payload(
        payload=_serialize_option_strategy_payload(decision),
        expression_bucket_id=expression_bucket_id,
        expression_definition=expression_definition,
        event_through_expiry=event_through_expiry,
    )
    metadata = dict(payload.get("metadata_json") or {})
    metadata["payload_generation_mode"] = (
        "option_chain_snapshot" if chain_legs is not None else "deterministic_signal_snapshot"
    )
    metadata["iv_context"] = iv_context
    payload["metadata_json"] = metadata
    return payload


def _choose_option_strategy_type(
    *,
    expression_bucket_id: str,
    expression_definition: StrategyDefinitionRecord,
    direction: str,
    event_through_expiry: bool,
) -> str | None:
    allowed = [str(item) for item in expression_definition.config_json.get("allowed_option_strategy_types") or []]
    if not allowed:
        allowed = {
            "defined_risk_directional_option": ["long_call", "long_put"],
            "defined_risk_income_spread": ["put_credit_spread", "call_credit_spread"],
            "volatility_event_option": ["long_straddle", "long_strangle"],
        }.get(expression_bucket_id, [])
    direction = str(direction or "").lower()
    preferred_by_direction = {
        "bullish": {
            "defined_risk_directional_option": "long_call",
            "defined_risk_income_spread": "put_credit_spread",
            "volatility_event_option": "long_strangle",
        },
        "bearish": {
            "defined_risk_directional_option": "long_put",
            "defined_risk_income_spread": "call_credit_spread",
            "volatility_event_option": "long_strangle",
        },
    }
    preferred = preferred_by_direction.get(direction, {}).get(expression_bucket_id)
    if preferred in allowed:
        if expression_bucket_id == "volatility_event_option" and event_through_expiry and "long_straddle" in allowed:
            return "long_straddle"
        return preferred
    if expression_bucket_id == "volatility_event_option" and "long_straddle" in allowed and direction not in {"bullish", "bearish"}:
        return "long_straddle"
    return allowed[0] if allowed else None


def _apply_expression_policy_to_option_payload(
    *,
    payload: dict[str, Any],
    expression_bucket_id: str,
    expression_definition: StrategyDefinitionRecord,
    event_through_expiry: bool,
) -> dict[str, Any]:
    earnings_policy = _expression_earnings_policy(
        expression_bucket_id=expression_bucket_id,
        expression_definition=expression_definition,
    )
    blocked = (
        earnings_policy in {
            "avoid_unpriced_high_risk_events",
            "avoid_holding_through_unapproved_binary_events",
        }
        and event_through_expiry
    ) or (
        earnings_policy == "event_through_expiry_must_be_explicit"
        and not event_through_expiry
    )
    if not blocked:
        return payload
    metadata = dict(payload.get("metadata_json") or {})
    metadata["policy_rejection"] = {
        "earnings_policy": earnings_policy,
        "event_through_expiry": event_through_expiry,
    }
    adjusted = dict(payload)
    adjusted["status"] = "rejected"
    adjusted["rejection_reason"] = "earnings_policy_blocked"
    adjusted["metadata_json"] = metadata
    return adjusted


def _reject_option_payload(
    *,
    reason: str,
    option_strategy_type: str,
    underlying_price: float,
    event_through_expiry: bool,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "option_strategy_decision_id": str(uuid.uuid4()),
        "option_strategy_type": option_strategy_type,
        "status": "rejected",
        "rejection_reason": reason,
        "underlying_price": underlying_price,
        "net_debit_or_credit": 0.0,
        "max_loss": 0.0,
        "max_profit": None,
        "breakevens": [],
        "margin_requirement": 0.0,
        "buying_power_effect": 0.0,
        "assignment_notional": 0.0,
        "portfolio_delta": 0.0,
        "portfolio_gamma": 0.0,
        "portfolio_theta": 0.0,
        "portfolio_vega": 0.0,
        "event_through_expiry": event_through_expiry,
        "strategy_pairing_method": "single_leg",
        "assignment_plan": None,
        "margin_model_profile": "estimated_fidelity_like_conservative_v1",
        "margin_model_version": "v1",
        "margin_requirement_source": "simulated_formula",
        "profit_target_pct": 0.0,
        "max_loss_rule": "",
        "roll_conditions": [],
        "close_conditions": [],
        "metadata_json": dict(metadata or {}),
    }


def _expression_earnings_policy(
    *,
    expression_bucket_id: str,
    expression_definition: StrategyDefinitionRecord,
) -> str | None:
    value = expression_definition.config_json.get("earnings_policy")
    if isinstance(value, str) and value:
        return value
    return {
        "defined_risk_directional_option": "avoid_unpriced_high_risk_events",
        "defined_risk_income_spread": "avoid_holding_through_unapproved_binary_events",
        "volatility_event_option": "event_through_expiry_must_be_explicit",
    }.get(expression_bucket_id)


def _expression_option_policy(
    *,
    expression_bucket_id: str,
    expression_definition: StrategyDefinitionRecord,
) -> dict[str, Any]:
    policy = dict(expression_definition.config_json.get("option_policy") or {})
    if policy:
        return policy
    return {
        "defined_risk_directional_option": {
            "max_loss_source": "premium_paid",
            "requires_implied_volatility": False,
            "profit_target_pct": 0.65,
            "non_event_dte_days": 28,
            "long_call_strike_pct_above_spot": 0.02,
            "long_put_strike_pct_below_spot": 0.02,
            "long_call_target_delta": 0.42,
            "long_put_target_delta": -0.42,
            "close_conditions": ["take_profit_65pct", "time_stop_10d"],
        },
        "defined_risk_income_spread": {
            "profit_target_pct": 0.5,
            "non_event_dte_days": 28,
            "short_put_strike_pct_below_spot": 0.03,
            "long_put_strike_pct_below_spot": 0.08,
            "short_call_strike_pct_above_spot": 0.03,
            "long_call_strike_pct_above_spot": 0.08,
            "short_leg_target_delta_abs": 0.28,
            "long_leg_target_delta_abs": 0.12,
            "close_conditions": ["take_profit_50pct"],
            "roll_conditions": ["7_dte_if_otm"],
            "assignment_plan": "close_or_roll_before_expiry_if_itm",
            "strategy_pairing_method": "vertical_by_expiry_and_width",
        },
        "volatility_event_option": {
            "max_loss_source": "net_debit",
            "requires_implied_volatility": True,
            "prefer_higher_vega": True,
            "prefer_higher_implied_volatility": True,
            "profit_target_pct": 0.35,
            "event_dte_days": 7,
            "straddle_target_delta_abs": 0.24,
            "strangle_call_strike_pct_above_spot_bullish": 0.04,
            "strangle_call_strike_pct_above_spot_default": 0.03,
            "strangle_put_strike_pct_below_spot_bearish": 0.04,
            "strangle_put_strike_pct_below_spot_default": 0.03,
            "strangle_call_target_delta": 0.26,
            "strangle_put_target_delta": -0.14,
            "close_conditions": ["event_exit_after_reaction", "premium_stop"],
            "roll_conditions": ["event_window_only"],
            "strategy_pairing_method": "same_expiry_long_vol",
        },
    }.get(expression_bucket_id, {})


def _expression_requires_implied_volatility(
    *,
    expression_bucket_id: str,
    expression_definition: StrategyDefinitionRecord,
) -> bool:
    option_policy = _expression_option_policy(
        expression_bucket_id=expression_bucket_id,
        expression_definition=expression_definition,
    )
    configured = option_policy.get("requires_implied_volatility")
    if isinstance(configured, bool):
        return configured
    return expression_bucket_id == "volatility_event_option"


def _option_days_to_expiry(
    *,
    option_strategy_type: str,
    option_policy: dict[str, Any],
    event_through_expiry: bool,
) -> int:
    _ = option_strategy_type
    key = "event_dte_days" if event_through_expiry else "non_event_dte_days"
    value = option_policy.get(key)
    if isinstance(value, int) and value > 0:
        return value
    return 10 if event_through_expiry else 21


def _option_profit_target_pct(
    *,
    option_strategy_type: str,
    option_policy: dict[str, Any],
) -> float:
    _ = option_strategy_type
    value = option_policy.get("profit_target_pct")
    if isinstance(value, (int, float)) and float(value) > 0:
        return float(value)
    return 0.5


def _infer_option_underlying_price(signal_snapshot: SignalSnapshotResult) -> float:
    technical = dict(signal_snapshot.signal_json.get("technical") or {})
    for field in ("last_price", "latest_close"):
        value = technical.get(field)
        if isinstance(value, (int, float)) and float(value) > 0:
            return float(value)
    return 100.0


def _event_through_expiry(signal_snapshot: SignalSnapshotResult) -> bool:
    events_news = dict(signal_snapshot.signal_json.get("events_news") or {})
    return bool(
        events_news.get("own_earnings_event_type")
        or events_news.get("regulatory_news_flag")
        or events_news.get("guidance_news_flag")
    )


def _option_max_loss_rule(option_strategy_type: str, option_policy: dict[str, Any]) -> str:
    max_loss_source = option_policy.get("max_loss_source")
    if isinstance(max_loss_source, str) and max_loss_source:
        return max_loss_source
    if option_strategy_type in {"long_call", "long_put"}:
        return "premium_paid"
    if option_strategy_type in {"long_straddle", "long_strangle"}:
        return "net_debit"
    return "close_at_2x_credit"


def _option_roll_conditions(option_strategy_type: str, option_policy: dict[str, Any]) -> tuple[str, ...]:
    configured = option_policy.get("roll_conditions")
    if isinstance(configured, list) and configured:
        return tuple(str(item) for item in configured)
    if option_strategy_type in {"put_credit_spread", "call_credit_spread"}:
        return ("7_dte_if_otm",)
    return ("delta_drops",)


def _option_close_conditions(option_strategy_type: str, option_policy: dict[str, Any]) -> tuple[str, ...]:
    configured = option_policy.get("close_conditions")
    if isinstance(configured, list) and configured:
        return tuple(str(item) for item in configured)
    if option_strategy_type in {"put_credit_spread", "call_credit_spread"}:
        return ("take_profit_50pct",)
    return ("take_profit",)


def _option_strategy_pairing_method(option_strategy_type: str, option_policy: dict[str, Any]) -> str:
    configured = option_policy.get("strategy_pairing_method")
    if isinstance(configured, str) and configured:
        return configured
    if option_strategy_type in {"put_credit_spread", "call_credit_spread"}:
        return "vertical_by_expiry_and_width"
    return "single_leg"


def _option_assignment_plan(option_strategy_type: str, option_policy: dict[str, Any]) -> str | None:
    configured = option_policy.get("assignment_plan")
    if isinstance(configured, str) and configured:
        return configured
    if option_strategy_type in {"put_credit_spread", "call_credit_spread"}:
        return "close_or_roll_before_expiry_if_itm"
    return None


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


def _serialize_option_strategy_payload(decision: OptionStrategyDecisionRecord) -> dict[str, Any]:
    return {
        "option_strategy_decision_id": decision.option_strategy_decision_id,
        "option_strategy_type": decision.option_strategy_type,
        "status": decision.status,
        "rejection_reason": decision.rejection_reason,
        "underlying_price": decision.underlying_price,
        "net_debit_or_credit": decision.net_debit_or_credit,
        "max_loss": decision.max_loss,
        "max_profit": decision.max_profit,
        "breakevens": list(decision.breakevens),
        "margin_requirement": decision.margin_requirement,
        "buying_power_effect": decision.buying_power_effect,
        "assignment_notional": decision.assignment_notional,
        "portfolio_delta": decision.portfolio_delta,
        "portfolio_gamma": decision.portfolio_gamma,
        "portfolio_theta": decision.portfolio_theta,
        "portfolio_vega": decision.portfolio_vega,
        "event_through_expiry": decision.event_through_expiry,
        "strategy_pairing_method": decision.strategy_pairing_method,
        "assignment_plan": decision.assignment_plan,
        "margin_model_profile": decision.margin_model_profile,
        "margin_model_version": decision.margin_model_version,
        "margin_requirement_source": decision.margin_requirement_source,
        "profit_target_pct": decision.profit_target_pct,
        "max_loss_rule": decision.max_loss_rule,
        "roll_conditions": list(decision.roll_conditions),
        "close_conditions": list(decision.close_conditions),
        "metadata_json": dict(decision.metadata_json),
    }


_WINDOWED_EVENT_NEWS_FIELDS = (
    "own_earnings_event_type",
    "analyst_upgrade_count",
    "analyst_downgrade_count",
    "price_target_revision_score",
    "guidance_news_flag",
    "customer_order_news_flag",
    "regulatory_news_flag",
    "high_signal_news_count_24h",
    "high_signal_news_count_7d",
    "sentiment_direction",
    "catalyst_quality_score",
    "direct_negative_catalyst_type",
)

_EVIDENCE_IMPORTANCE_PRIORITY = {"critical": 0, "high": 1, "medium": 2, "normal": 3, "low": 4}


def _news_evidence_limit() -> int:
    raw = os.getenv("TRADING_NEWS_EVIDENCE_LIMIT", "4").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 4


def _evidence_priority(item: EventNewsItemRecord) -> tuple[int, int, datetime, str]:
    importance_rank = _EVIDENCE_IMPORTANCE_PRIORITY.get(str(item.importance or "").casefold(), 5)
    specificity = int(item.metadata_json.get("specificity_score", 0))
    return (
        importance_rank,
        -specificity,
        item.available_for_decision_at,
        item.event_news_item_id,
    )


def _round_nested_floats(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, list):
        return [_round_nested_floats(item) for item in value]
    if isinstance(value, tuple):
        return [_round_nested_floats(item) for item in value]
    if isinstance(value, dict):
        return {key: _round_nested_floats(item) for key, item in value.items()}
    return value
