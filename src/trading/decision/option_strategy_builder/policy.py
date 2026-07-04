"""Expression-policy helpers for option strategy payload construction."""
from __future__ import annotations

from typing import Any

from src.trading.signals import SignalSnapshotResult
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord


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
