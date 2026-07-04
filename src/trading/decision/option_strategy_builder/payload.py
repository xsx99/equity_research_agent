"""Payload assembly helpers for option strategy decisions."""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from src.trading.options.strategy import (
    OptionStrategyDecisionInput,
    OptionStrategyDecisionRecord,
    OptionsStrategyLayer,
)
from src.trading.signals import SignalSnapshotResult
from src.trading.signals.sources import SourceRecord
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord
from src.trading.decision.option_strategy_builder.chain import (
    _build_option_leg_definitions,
    _infer_option_underlying_price,
    _option_iv_context,
    _select_option_chain_legs,
)
from src.trading.decision.option_strategy_builder.policy import (
    _apply_expression_policy_to_option_payload,
    _choose_option_strategy_type,
    _event_through_expiry,
    _expression_option_policy,
    _expression_requires_implied_volatility,
    _option_assignment_plan,
    _option_close_conditions,
    _option_days_to_expiry,
    _option_max_loss_rule,
    _option_profit_target_pct,
    _option_roll_conditions,
    _option_strategy_pairing_method,
)


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
