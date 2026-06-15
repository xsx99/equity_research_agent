"""Risk assembly helpers for the live preopen runtime."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from src.trading.runtime.lookahead_risk import LookaheadRiskWorkflowHelper


class _LiveRiskWorkflow:
    def __init__(
        self,
        *,
        repository: Any,
        source_repository: Any,
        config_resolver: Any,
        position_sizer: Any,
        risk_manager: Any,
        option_risk_manager: Any | None = None,
        lookahead_helper: Any | None = None,
    ) -> None:
        self.repository = repository
        self.source_repository = source_repository
        self.config_resolver = config_resolver
        self.position_sizer = position_sizer
        self.risk_manager = risk_manager
        self.option_risk_manager = option_risk_manager
        self.lookahead_helper = lookahead_helper or LookaheadRiskWorkflowHelper()

    def run(
        self,
        *,
        candidates: tuple[object, ...],
        classifications: tuple[object, ...],
        portfolio_context: object,
        decision_time: datetime,
    ) -> object:
        from types import SimpleNamespace

        signal_by_id = {
            snapshot.signal_snapshot_id: snapshot
            for snapshot in self.repository.load_signal_snapshots_for_decision(
                decision_time=decision_time,
                snapshot_type="pre_open",
            )
        }
        expression_definitions = {
            definition.strategy_id: definition
            for definition in getattr(self.repository, "load_active_strategy_definitions", lambda: [])()
            if getattr(definition, "strategy_layer", None) == "expression_bucket"
            and bool(getattr(definition, "is_active", False))
        }
        config = self.config_resolver.resolve(
            risk_appetite="balanced",
            portfolio_context=portfolio_context,
            macro_risk_budget_multiplier=1.0,
        )
        portfolio_snapshot = self.risk_manager.build_portfolio_risk_snapshot(portfolio_context, config)
        exposures = self.risk_manager.compute_factor_exposures(portfolio_context)
        self.repository.save_portfolio_risk_snapshot(portfolio_snapshot)
        self.repository.save_risk_factor_exposures(exposures)
        portfolio_risk_intent = self.lookahead_helper.build_preopen_portfolio_risk_intent(
            candidates=candidates,
            classifications=classifications,
            signal_by_id=signal_by_id,
            portfolio_context=portfolio_context,
            config=config,
            decision_time=decision_time,
            portfolio_risk_snapshot_id=portfolio_snapshot.portfolio_risk_snapshot_id,
        )
        if hasattr(self.repository, "save_portfolio_risk_intent"):
            self.repository.save_portfolio_risk_intent(
                replace(
                    portfolio_risk_intent,
                    portfolio_risk_snapshot_id=portfolio_snapshot.portfolio_risk_snapshot_id,
                )
            )
        candidate_by_id = {candidate.candidate_score_id: candidate for candidate in candidates}
        decisions: list[object] = []
        for classification in classifications:
            candidate = candidate_by_id.get(classification.candidate_score_id)
            if candidate is None:
                continue
            snapshot = signal_by_id.get(candidate.signal_snapshot_id)
            request = _build_trade_risk_request(
                candidate=candidate,
                classification=classification,
                snapshot=snapshot,
                source_repository=self.source_repository,
                decision_time=decision_time,
                expression_definitions=expression_definitions,
            )
            sizing = self.position_sizer.size_position(request, portfolio_context, config)
            decision = _evaluate_with_optional_lookahead(
                self.risk_manager,
                request=request,
                sizing=sizing,
                portfolio_context=portfolio_context,
                config=config,
                portfolio_risk_intent=portfolio_risk_intent,
            )
            decision = replace(
                decision,
                portfolio_risk_snapshot_id=portfolio_snapshot.portfolio_risk_snapshot_id,
            )
            decision = self._apply_option_assignment_risk(
                candidate=candidate,
                classification=classification,
                snapshot=snapshot,
                request=request,
                decision=decision,
                portfolio_context=portfolio_context,
                config=config,
                expression_definitions=expression_definitions,
            )
            self.repository.save_position_sizing_decision(sizing)
            decisions.append(decision)
        materialized = self.lookahead_helper.materialize_generated_hedges(
            risk_decisions=tuple(decisions),
            portfolio_risk_intent=portfolio_risk_intent,
        )
        for decision in materialized:
            self.repository.save_risk_decision(decision)
        return SimpleNamespace(
            risk_decisions=materialized,
            portfolio_risk_intent=portfolio_risk_intent,
        )

    def _apply_option_assignment_risk(
        self,
        *,
        candidate: Any,
        classification: Any,
        snapshot: Any,
        request: Any,
        decision: Any,
        portfolio_context: Any,
        config: Any,
        expression_definitions: dict[str, Any],
    ) -> Any:
        if self.option_risk_manager is None or getattr(request, "instrument_type", "") != "option":
            return decision
        if getattr(decision, "status", None) not in {"approved", "reduced"}:
            return decision
        option_payload = _preopen_option_strategy_payload(
            candidate=candidate,
            classification=classification,
            snapshot=snapshot,
            source_repository=self.source_repository,
            expression_definitions=expression_definitions,
        )
        option_risk = _build_preopen_option_risk_input(
            option_payload=option_payload,
            trade_identity=str(getattr(classification, "trade_identity", "") or ""),
            ticker=str(getattr(candidate, "ticker", "") or ""),
            sector=getattr(request, "sector", None),
        )
        if option_risk is None:
            return decision
        assessment = self.option_risk_manager.evaluate_assignment_risk(
            option_risk,
            portfolio_context=portfolio_context,
            config=config,
        )
        if assessment.status == "approved":
            return decision
        from src.trading.risk import OptionRiskSnapshotRecord, RiskDecisionRecord

        saved_snapshot = None
        if hasattr(self.repository, "save_option_risk_snapshot"):
            snapshot_metadata = {
                **dict(option_payload.get("metadata_json") or {}),
                "option_risk_reason_code": assessment.reason_code,
                "option_risk_status": assessment.status,
                "option_risk_checks": dict(getattr(assessment, "metadata_json", {}) or {}),
            }
            saved_snapshot = OptionRiskSnapshotRecord.create(
                ticker=option_risk.ticker,
                trade_identity=option_risk.trade_identity,
                option_strategy_type=option_risk.option_strategy_type,
                underlying_price=option_risk.underlying_price,
                portfolio_delta=assessment.portfolio_delta,
                portfolio_gamma=assessment.portfolio_gamma,
                portfolio_theta=assessment.portfolio_theta,
                portfolio_vega=assessment.portfolio_vega,
                net_debit_or_credit=option_risk.net_debit_or_credit,
                max_loss=option_risk.max_loss,
                max_profit=option_risk.max_profit,
                margin_requirement=option_risk.margin_requirement,
                buying_power_effect=option_risk.buying_power_effect,
                assignment_notional=float(option_payload.get("assignment_notional") or 0.0),
                worst_case_assignment_notional=assessment.worst_case_assignment_notional,
                margin_model_profile=str(
                    option_payload.get("margin_model_profile") or "estimated_fidelity_like_conservative_v1"
                ),
                margin_model_version=str(option_payload.get("margin_model_version") or "v1"),
                margin_requirement_source=str(
                    option_payload.get("margin_requirement_source") or "simulated_formula"
                ),
                risk_status=assessment.status,
                reason_code=assessment.reason_code,
                created_at=getattr(decision, "decision_time"),
                metadata_json=snapshot_metadata,
            )
            self.repository.save_option_risk_snapshot(saved_snapshot)
        return RiskDecisionRecord.create(
            candidate_score_id=getattr(decision, "candidate_score_id", None),
            trade_classification_id=getattr(decision, "trade_classification_id", None),
            position_sizing_decision_id=getattr(decision, "position_sizing_decision_id", None),
            ticker=getattr(decision, "ticker"),
            status="rejected",
            reason_code=assessment.reason_code,
            approved_weight=0.0,
            approved_notional=0.0,
            approved_quantity=0.0,
            portfolio_risk_snapshot_id=getattr(decision, "portfolio_risk_snapshot_id", None),
            applied_rules=[*list(getattr(decision, "applied_rules", ())), "option_assignment_risk_check"],
            decision_time=getattr(decision, "decision_time"),
            metadata_json={
                "superseded_risk_decision_id": getattr(decision, "risk_decision_id", None),
                "option_risk_reason_code": assessment.reason_code,
                "option_risk_status": assessment.status,
                "option_risk_snapshot_id": getattr(saved_snapshot, "option_risk_snapshot_id", None),
                "option_risk_checks": dict(getattr(assessment, "metadata_json", {}) or {}),
            },
        )


def _build_trade_risk_request(
    *,
    candidate: Any,
    classification: Any,
    snapshot: Any,
    source_repository: Any,
    decision_time: datetime,
    expression_definitions: dict[str, Any] | None = None,
) -> Any:
    from src.trading.risk.context import TradeRiskRequest

    instrument_type = _classification_instrument_type(classification)
    technical = dict(getattr(snapshot, "signal_json", {}).get("technical", {}))
    source_freshness = dict(getattr(snapshot, "source_freshness_json", {}))
    price = _latest_price_from_sources(
        source_repository=source_repository,
        ticker=candidate.ticker,
        decision_time=decision_time,
    )
    option_contracts = _latest_option_contracts(
        source_repository=source_repository,
        ticker=candidate.ticker,
        decision_time=decision_time,
    )
    option_payload = _preopen_option_strategy_payload(
        candidate=candidate,
        classification=classification,
        snapshot=snapshot,
        source_repository=source_repository,
        expression_definitions=expression_definitions or {},
    )
    option_price_proxy = _option_price_proxy(option_contracts)
    sector = _sector_from_snapshot(snapshot)
    atr_pct = float(technical.get("atr_pct") or 0.0)
    average_daily_dollar_volume = float(technical.get("dollar_volume") or 0.0)
    option_metadata_complete = bool(option_contracts) if instrument_type == "option" else True
    if instrument_type == "option" and option_price_proxy is not None:
        price = option_price_proxy
    margin_proxy = max(price, 1.0)
    buying_power_effect = margin_proxy
    assignment_notional = 0.0
    event_through_horizon = None
    if instrument_type == "option" and isinstance(option_payload, dict) and option_payload.get("status") == "ready":
        net_debit_or_credit = option_payload.get("net_debit_or_credit")
        if isinstance(net_debit_or_credit, (int, float)):
            price = round(max(abs(float(net_debit_or_credit)) * 100.0, 1.0), 2)
        margin_proxy = float(option_payload.get("margin_requirement") or margin_proxy)
        buying_power_effect = float(option_payload.get("buying_power_effect") or margin_proxy)
        assignment_notional = float(option_payload.get("assignment_notional") or 0.0)
        option_metadata_complete = bool((option_payload.get("metadata_json") or {}).get("legs"))
        event_through_horizon = bool(option_payload.get("event_through_expiry"))
    return TradeRiskRequest(
        candidate=candidate,
        classification=classification,
        instrument_type=instrument_type,
        target_weight=min(max(float(candidate.candidate_score) * 0.05, 0.0), 0.10),
        confidence=min(max(float(candidate.candidate_score), 0.0), 1.0),
        sector=sector,
        beta_bucket=None,
        volatility_bucket="high" if atr_pct >= 0.05 else "medium",
        liquidity_bucket="thin"
        if average_daily_dollar_volume and average_daily_dollar_volume < 25_000_000
        else "liquid",
        event_type=None,
        macro_sensitivity=None,
        price=price,
        atr_pct=atr_pct,
        average_daily_dollar_volume=average_daily_dollar_volume,
        signal_freshness=source_freshness,
        estimated_margin_requirement=margin_proxy,
        estimated_buying_power_effect=buying_power_effect,
        estimated_initial_margin_requirement=margin_proxy,
        estimated_maintenance_margin_requirement=max(buying_power_effect, 1.0),
        assignment_notional=assignment_notional,
        option_risk_metadata_complete=option_metadata_complete,
        event_through_horizon=event_through_horizon,
    )


def _classification_instrument_type(classification: Any) -> str:
    trade_identity = str(getattr(classification, "trade_identity", "") or "")
    if trade_identity == "watch_only":
        return "watch"
    if trade_identity == "tactical_option_trade":
        return "option"
    return "stock"


def _latest_price_from_sources(*, source_repository: Any, ticker: str, decision_time: datetime) -> float:
    technical_rows = source_repository.latest_available_by_family(ticker, "technical", decision_time)
    if not technical_rows:
        return 1.0
    bars = list((technical_rows[-1].payload or {}).get("bars") or [])
    if not bars:
        return 1.0
    last_bar = bars[-1]
    close = last_bar.get("close")
    if isinstance(close, (int, float)) and close > 0:
        return float(close)
    return 1.0


def _latest_option_contracts(
    *,
    source_repository: Any,
    ticker: str,
    decision_time: datetime,
) -> tuple[dict[str, Any], ...]:
    option_rows = source_repository.latest_available_by_family(ticker, "option_chain", decision_time)
    if not option_rows:
        return ()
    contracts = list((option_rows[-1].payload or {}).get("contracts") or [])
    return tuple(contract for contract in contracts if isinstance(contract, dict))


def _option_price_proxy(contracts: tuple[dict[str, Any], ...]) -> float | None:
    for contract in contracts:
        for key in ("chosen_price", "mid", "ask", "bid"):
            value = contract.get(key)
            if isinstance(value, (int, float)) and float(value) > 0:
                return float(value) * 100.0
    return None


def _preopen_option_strategy_payload(
    *,
    candidate: Any,
    classification: Any,
    snapshot: Any,
    source_repository: Any,
    expression_definitions: dict[str, Any],
) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    expression_bucket_id = str(getattr(classification, "expression_bucket_id", "") or "")
    expression_definition = expression_definitions.get(expression_bucket_id)
    if expression_definition is None:
        return None

    from src.trading.options.strategy import OptionsStrategyLayer
    from src.trading.workflows.trading_decision import (
        _build_option_strategy_payload,
        _decision_action_for_expression,
    )

    option_chain_rows = tuple(
        source_repository.latest_available_by_family(candidate.ticker, "option_chain", candidate.decision_time) or ()
    )
    decision_action = _decision_action_for_expression(
        getattr(candidate, "action", ""),
        "option",
        getattr(classification, "trade_identity", ""),
    )
    return _build_option_strategy_payload(
        candidate=candidate,
        classification=classification,
        signal_snapshot=snapshot,
        option_chain_rows=option_chain_rows,
        expression_bucket_id=expression_bucket_id,
        expression_bucket_version=str(
            getattr(classification, "expression_bucket_version", "")
            or getattr(expression_definition, "version", "v1")
        ),
        trade_identity=str(getattr(classification, "trade_identity", "") or ""),
        decision_action=decision_action,
        expression_definition=expression_definition,
        options_strategy_layer=OptionsStrategyLayer(),
    )


def _build_preopen_option_risk_input(
    *,
    option_payload: dict[str, Any] | None,
    trade_identity: str,
    ticker: str,
    sector: str | None,
) -> Any | None:
    if not isinstance(option_payload, dict) or option_payload.get("status") != "ready":
        return None
    legs_payload = list((option_payload.get("metadata_json") or {}).get("legs") or [])
    if not legs_payload:
        return None

    from datetime import date

    from src.trading.risk import OptionLegRiskInput, OptionRiskInput

    legs = []
    for payload in legs_payload:
        if not isinstance(payload, dict):
            continue
        legs.append(
            OptionLegRiskInput(
                option_type=str(payload["option_type"]),
                side=str(payload["side"]),
                quantity=int(payload["quantity"]),
                strike=float(payload["strike"]),
                expiry=date.fromisoformat(str(payload["expiry"])),
                delta=float(payload["delta"]),
                gamma=float(payload["gamma"]),
                theta=float(payload["theta"]),
                vega=float(payload["vega"]),
                premium=float(payload["chosen_price"]),
            )
        )
    if not legs:
        return None
    return OptionRiskInput(
        ticker=ticker,
        trade_identity=trade_identity,
        option_strategy_type=str(option_payload["option_strategy_type"]),
        underlying_price=float(option_payload["underlying_price"]),
        sector=sector,
        event_type="earnings" if bool(option_payload.get("event_through_expiry")) else None,
        event_through_expiry=bool(option_payload.get("event_through_expiry")),
        margin_requirement=float(option_payload["margin_requirement"]),
        buying_power_effect=float(option_payload["buying_power_effect"]),
        max_loss=float(option_payload["max_loss"]),
        max_profit=(
            float(option_payload["max_profit"])
            if option_payload.get("max_profit") is not None
            else None
        ),
        net_debit_or_credit=float(option_payload["net_debit_or_credit"]),
        legs=tuple(legs),
    )


def _evaluate_with_optional_lookahead(
    risk_manager: Any,
    *,
    request: Any,
    sizing: Any,
    portfolio_context: Any,
    config: Any,
    portfolio_risk_intent: Any,
) -> Any:
    try:
        return risk_manager.evaluate(
            request,
            sizing,
            portfolio_context,
            config,
            portfolio_risk_intent=portfolio_risk_intent,
        )
    except TypeError as exc:
        if "portfolio_risk_intent" not in str(exc):
            raise
        return risk_manager.evaluate(request, sizing, portfolio_context, config)


def _sector_from_snapshot(snapshot: Any) -> str | None:
    if snapshot is None:
        return None
    signal_json = dict(getattr(snapshot, "signal_json", {}) or {})
    for key in ("fundamental", "company"):
        payload = dict(signal_json.get(key) or {})
        sector = payload.get("sector")
        if isinstance(sector, str) and sector.strip():
            return sector.strip()
    return None
