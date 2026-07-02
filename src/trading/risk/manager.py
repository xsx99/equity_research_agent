"""Deterministic PR04 risk approval and exposure aggregation."""
from __future__ import annotations

from collections import defaultdict

from src.trading.risk.config import RiskLimitConfig
from src.trading.risk.context import (
    PortfolioContext,
    PortfolioPosition,
    PortfolioRiskSnapshotRecord,
    PositionSizingDecisionRecord,
    RiskDecisionRecord,
    RiskFactorExposureRecord,
    TradeRiskRequest,
)
from src.trading.risk.lookahead import HedgeActionRecord, PortfolioRiskIntentRecord, PositionRiskActionRecord

_BLOCKING_SIGNAL_STATUSES = frozenset({"missing", "stale", "failed"})
_INSIDER_REQUIRED_STRATEGIES = frozenset({"insider_accumulation_momentum_v1"})


class RiskManager:
    """Final deterministic risk gate before later broker wiring."""

    def compute_factor_exposures(
        self,
        portfolio_context: PortfolioContext,
    ) -> tuple[RiskFactorExposureRecord, ...]:
        buckets: dict[tuple[str, str], dict[str, float]] = defaultdict(
            lambda: {
                "gross_exposure": 0.0,
                "net_exposure": 0.0,
                "long_exposure": 0.0,
                "short_exposure": 0.0,
                "position_count": 0.0,
            }
        )
        for position in portfolio_context.positions:
            self._accumulate_factor(buckets, "sector", position.sector, position)
            self._accumulate_factor(buckets, "strategy", position.strategy_id, position)
            self._accumulate_factor(buckets, "horizon", position.intended_horizon, position)
            self._accumulate_factor(buckets, "direction", position.direction, position)
            self._accumulate_factor(buckets, "beta_bucket", position.beta_bucket, position)
            self._accumulate_factor(buckets, "volatility_bucket", position.volatility_bucket, position)
            self._accumulate_factor(buckets, "liquidity_bucket", position.liquidity_bucket, position)
            self._accumulate_factor(buckets, "event_type", position.event_type, position)
            self._accumulate_factor(buckets, "macro_sensitivity", position.macro_sensitivity, position)

        return tuple(
            RiskFactorExposureRecord(
                factor_type=factor_type,
                factor_value=factor_value,
                gross_exposure=values["gross_exposure"],
                net_exposure=values["net_exposure"],
                long_exposure=values["long_exposure"],
                short_exposure=values["short_exposure"],
                position_count=int(values["position_count"]),
                metadata_json={},
            )
            for (factor_type, factor_value), values in sorted(buckets.items())
        )

    def build_portfolio_risk_snapshot(
        self,
        portfolio_context: PortfolioContext,
        config: RiskLimitConfig,
    ) -> PortfolioRiskSnapshotRecord:
        gross_exposure = sum(abs(position.notional_exposure) for position in portfolio_context.positions)
        net_exposure = sum(
            position.notional_exposure if position.direction != "short" else -position.notional_exposure
            for position in portfolio_context.positions
        )
        beta_adjusted_net_exposure = sum(
            position.notional_exposure * _beta_multiplier(position.beta_bucket) * (-1 if position.direction == "short" else 1)
            for position in portfolio_context.positions
        )
        concentration_flags = [
            f"sector:{exposure.factor_value}"
            for exposure in self.compute_factor_exposures(portfolio_context)
            if exposure.factor_type == "sector"
            and portfolio_context.account_equity > 0
            and exposure.gross_exposure / portfolio_context.account_equity > config.max_sector_weight
        ]
        return PortfolioRiskSnapshotRecord.create(
            decision_time=portfolio_context.as_of,
            risk_appetite=config.risk_appetite,
            resolver_version=config.resolver_version,
            margin_model_profile=config.margin_model_profile,
            margin_model_version=config.margin_model_version,
            account_equity=portfolio_context.account_equity,
            cash_balance=portfolio_context.cash_balance,
            buying_power=portfolio_context.buying_power,
            excess_liquidity=portfolio_context.excess_liquidity,
            stock_margin_requirement=portfolio_context.stock_margin_requirement,
            option_margin_requirement=portfolio_context.option_margin_requirement,
            total_margin_requirement=portfolio_context.total_margin_requirement,
            initial_margin_requirement=portfolio_context.initial_margin_requirement,
            maintenance_margin_requirement=portfolio_context.maintenance_margin_requirement,
            margin_requirement_source=portfolio_context.margin_requirement_source,
            net_exposure=net_exposure,
            gross_exposure=gross_exposure,
            beta_adjusted_net_exposure=beta_adjusted_net_exposure,
            concentration_flags=concentration_flags,
            metadata_json={},
        )

    def evaluate(
        self,
        request: TradeRiskRequest,
        sizing: PositionSizingDecisionRecord,
        portfolio_context: PortfolioContext,
        config: RiskLimitConfig,
        portfolio_risk_intent: PortfolioRiskIntentRecord | None = None,
    ) -> RiskDecisionRecord:
        snapshot = self.build_portfolio_risk_snapshot(portfolio_context, config)
        planner_position_action = _matching_planner_position_action(
            portfolio_risk_intent,
            ticker=request.candidate.ticker,
            trade_identity=request.classification.trade_identity,
        )
        planner_weight = sizing.final_weight
        planner_reason_code: str | None = None
        planner_risk_source: str | None = None
        if planner_position_action is not None:
            planner_reason_code = planner_position_action.reason_code
            planner_risk_source = planner_position_action.risk_source
            if planner_position_action.action == "block_open":
                return self._decision(
                    request,
                    sizing,
                    portfolio_context=portfolio_context,
                    config=config,
                    portfolio_risk_intent=portfolio_risk_intent,
                    snapshot_id=snapshot.portfolio_risk_snapshot_id,
                    status="rejected",
                    reason_code=planner_position_action.reason_code,
                    approved_weight=0.0,
                    applied_rules=["portfolio_risk_intent"],
                    binding_constraint=planner_position_action.reason_code,
                    lookahead_risk_source=planner_position_action.risk_source,
                )
            if (
                planner_position_action.action in {"reduce", "force_reduce"}
                and planner_position_action.max_allowed_weight_override is not None
            ):
                planner_weight = min(sizing.final_weight, planner_position_action.max_allowed_weight_override)

        if request.classification.trade_identity == "core_holding" and request.candidate.ticker not in portfolio_context.approved_core_tickers:
            return self._decision(
                request,
                sizing,
                portfolio_context=portfolio_context,
                config=config,
                portfolio_risk_intent=portfolio_risk_intent,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="rejected",
                reason_code="core_holding_requires_portfolio_intent",
                approved_weight=0.0,
                applied_rules=["core_holding_intent_check"],
                lookahead_risk_source=planner_risk_source,
            )

        if _has_missing_or_stale_signals(request):
            return self._decision(
                request,
                sizing,
                portfolio_context=portfolio_context,
                config=config,
                portfolio_risk_intent=portfolio_risk_intent,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="rejected",
                reason_code="missing_or_stale_signals",
                approved_weight=0.0,
                applied_rules=["signal_freshness_check"],
                lookahead_risk_source=planner_risk_source,
            )

        if request.instrument_type == "stock" and _is_macro_only_bearish(request):
            return self._decision(
                request,
                sizing,
                portfolio_context=portfolio_context,
                config=config,
                portfolio_risk_intent=portfolio_risk_intent,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="rejected",
                reason_code="macro_only_bearish_single_name_blocked",
                approved_weight=0.0,
                applied_rules=["bearish_evidence_gate"],
                lookahead_risk_source=planner_risk_source,
            )

        if request.estimated_margin_requirement is None or request.estimated_buying_power_effect is None:
            return self._decision(
                request,
                sizing,
                portfolio_context=portfolio_context,
                config=config,
                portfolio_risk_intent=portfolio_risk_intent,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="rejected",
                reason_code="unestimable_margin_requirement",
                approved_weight=0.0,
                applied_rules=["margin_estimation_check"],
                lookahead_risk_source=planner_risk_source,
            )

        if request.instrument_type == "option" and not request.option_risk_metadata_complete:
            return self._decision(
                request,
                sizing,
                portfolio_context=portfolio_context,
                config=config,
                portfolio_risk_intent=portfolio_risk_intent,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="rejected",
                reason_code="missing_option_risk_metadata",
                approved_weight=0.0,
                applied_rules=["option_metadata_check"],
                lookahead_risk_source=planner_risk_source,
            )

        sector_weight = self._current_sector_weight(request.sector, portfolio_context)
        effective_sector_cap = _effective_sector_cap(request, config)
        proposed_weight = sector_weight + planner_weight
        if request.sector and proposed_weight > effective_sector_cap:
            approved_weight = max(0.0, effective_sector_cap - sector_weight)
            return self._decision(
                request,
                sizing,
                portfolio_context=portfolio_context,
                config=config,
                portfolio_risk_intent=portfolio_risk_intent,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="reduced" if approved_weight > 0 else "rejected",
                reason_code="sector_concentration_cap",
                approved_weight=approved_weight,
                applied_rules=["sector_concentration_check"],
                binding_constraint="sector_concentration_cap",
                lookahead_risk_source=planner_risk_source,
                generated_hedge_action=_generated_hedge_action(portfolio_risk_intent),
            )

        status = "approved"
        reason_code = "within_limits"
        applied_rules = ["single_name_limit_ok", "sector_concentration_ok"]
        binding_constraint = None
        if planner_weight < sizing.final_weight:
            status = "reduced"
            reason_code = planner_reason_code or "portfolio_risk_intent_reduce"
            applied_rules = ["portfolio_risk_intent", "single_name_limit_ok", "sector_concentration_ok"]
            binding_constraint = reason_code
        return self._decision(
            request,
            sizing,
            portfolio_context=portfolio_context,
            config=config,
            portfolio_risk_intent=portfolio_risk_intent,
            snapshot_id=snapshot.portfolio_risk_snapshot_id,
            status=status,
            reason_code=reason_code,
            approved_weight=planner_weight,
            applied_rules=applied_rules,
            binding_constraint=binding_constraint,
            lookahead_risk_source=planner_risk_source or _hedge_risk_source(portfolio_risk_intent),
            generated_hedge_action=_generated_hedge_action(portfolio_risk_intent),
        )

    def _current_sector_weight(self, sector: str | None, portfolio_context: PortfolioContext) -> float:
        if not sector or portfolio_context.account_equity <= 0:
            return 0.0
        sector_notional = sum(
            abs(position.notional_exposure)
            for position in portfolio_context.positions
            if position.sector == sector
        )
        return sector_notional / portfolio_context.account_equity

    def _accumulate_factor(
        self,
        buckets: dict[tuple[str, str], dict[str, float]],
        factor_type: str,
        factor_value: str | None,
        position: PortfolioPosition,
    ) -> None:
        if not factor_value:
            return
        key = (factor_type, factor_value)
        signed = position.notional_exposure if position.direction != "short" else -position.notional_exposure
        buckets[key]["gross_exposure"] += abs(position.notional_exposure)
        buckets[key]["net_exposure"] += signed
        if position.direction == "short":
            buckets[key]["short_exposure"] += abs(position.notional_exposure)
        else:
            buckets[key]["long_exposure"] += abs(position.notional_exposure)
        buckets[key]["position_count"] += 1

    def _decision(
        self,
        request: TradeRiskRequest,
        sizing: PositionSizingDecisionRecord,
        *,
        portfolio_context: PortfolioContext,
        config: RiskLimitConfig,
        portfolio_risk_intent: PortfolioRiskIntentRecord | None,
        snapshot_id: str | None,
        status: str,
        reason_code: str,
        approved_weight: float,
        applied_rules: list[str],
        binding_constraint: str | None = None,
        lookahead_risk_source: str | None = None,
        generated_hedge_action: dict[str, object] | None = None,
    ) -> RiskDecisionRecord:
        approved_notional = approved_weight * (sizing.final_notional / sizing.final_weight) if sizing.final_weight > 0 else 0.0
        quantity_basis, quantity_denominator = _approved_quantity_basis(request)
        approved_quantity = approved_notional / quantity_denominator if quantity_denominator > 0 else 0.0
        return RiskDecisionRecord.create(
            candidate_score_id=request.candidate.candidate_score_id,
            trade_classification_id=request.classification.trade_classification_id,
            position_sizing_decision_id=sizing.position_sizing_decision_id,
            ticker=request.candidate.ticker,
            status=status,
            reason_code=reason_code,
            approved_weight=approved_weight,
            approved_notional=approved_notional,
            approved_quantity=approved_quantity,
            portfolio_risk_snapshot_id=snapshot_id,
            applied_rules=applied_rules,
            binding_constraint=binding_constraint,
            lookahead_risk_source=lookahead_risk_source,
            generated_hedge_action=generated_hedge_action,
            decision_time=request.candidate.decision_time,
            metadata_json=_risk_decision_metadata(
                request=request,
                approved_notional=approved_notional,
                approved_quantity=approved_quantity,
                quantity_basis=quantity_basis,
                quantity_unit_cost=quantity_denominator,
                requested_weight=sizing.final_weight,
                approved_weight=approved_weight,
                portfolio_context=portfolio_context,
                config=config,
                portfolio_risk_intent=portfolio_risk_intent,
                binding_constraint=binding_constraint,
                lookahead_risk_source=lookahead_risk_source,
            ),
        )


def _beta_multiplier(beta_bucket: str | None) -> float:
    return {
        "low": 0.75,
        "medium": 1.0,
        "high": 1.2,
    }.get(str(beta_bucket or "").lower(), 1.0)


def _approved_quantity_basis(request: TradeRiskRequest) -> tuple[str, float]:
    if request.instrument_type == "option":
        if request.estimated_margin_requirement and request.estimated_margin_requirement > 0:
            return ("estimated_margin_requirement", request.estimated_margin_requirement)
        if request.estimated_buying_power_effect and request.estimated_buying_power_effect > 0:
            return ("estimated_buying_power_effect", request.estimated_buying_power_effect)
    return ("price", request.price if request.price > 0 else 0.0)


def _risk_decision_metadata(
    *,
    request: TradeRiskRequest,
    approved_notional: float,
    approved_quantity: float,
    quantity_basis: str,
    quantity_unit_cost: float,
    requested_weight: float,
    approved_weight: float,
    portfolio_context: PortfolioContext,
    config: RiskLimitConfig,
    portfolio_risk_intent: PortfolioRiskIntentRecord | None,
    binding_constraint: str | None,
    lookahead_risk_source: str | None,
) -> dict[str, object]:
    sector_weight_before = _sector_weight_for_request(request=request, portfolio_context=portfolio_context)
    sector_cap = _effective_sector_cap(request, config)
    metadata: dict[str, object] = {
        "approved_capital_notional": approved_notional,
        "approved_quantity_basis": quantity_basis,
        "approved_quantity_unit_cost": quantity_unit_cost,
        "macro_risk_budget_multiplier": config.macro_risk_budget_multiplier,
        "binding_constraints": list(getattr(portfolio_risk_intent, "binding_constraints", ()) or ()),
        "top_risk_sources": _top_risk_sources_for_decision(
            portfolio_risk_intent=portfolio_risk_intent,
            lookahead_risk_source=lookahead_risk_source,
        ),
        "hedge_posture": _hedge_posture_metadata(portfolio_risk_intent),
        "data_availability_issues": list(_data_availability_issues(portfolio_risk_intent)),
        "exposure_usage": {
            "sector_weight_before": sector_weight_before,
            "sector_weight_after": sector_weight_before + approved_notional / portfolio_context.account_equity
            if request.sector and portfolio_context.account_equity > 0
            else sector_weight_before,
            "sector_cap": sector_cap,
            "account_equity": portfolio_context.account_equity,
        },
        "rule_checks": _risk_rule_checks(
            request=request,
            requested_weight=requested_weight,
            approved_weight=approved_weight,
            sector_weight_before=sector_weight_before,
            sector_cap=sector_cap,
            config=config,
        ),
    }
    if binding_constraint is not None:
        metadata["binding_constraint"] = binding_constraint
    if request.instrument_type != "option":
        return metadata
    metadata["approved_strategy_units"] = approved_quantity
    metadata["approved_margin_exposure"] = approved_quantity * float(request.estimated_margin_requirement or 0.0)
    metadata["approved_buying_power_effect"] = approved_quantity * float(request.estimated_buying_power_effect or 0.0)
    metadata["approved_assignment_notional"] = approved_quantity * float(request.assignment_notional or 0.0)
    metadata["approved_premium_notional"] = approved_quantity * float(request.price or 0.0)
    return metadata


def _risk_rule_checks(
    *,
    request: TradeRiskRequest,
    requested_weight: float,
    approved_weight: float,
    sector_weight_before: float,
    sector_cap: float,
    config: RiskLimitConfig,
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = [
        {
            "label": "Single-name size",
            "observed": _format_rule_pct(requested_weight),
            "cap": f"{_format_rule_pct(config.max_single_name_weight)} cap",
            "passed": requested_weight <= config.max_single_name_weight + 1e-9,
        }
    ]
    if request.sector:
        observed_sector_weight = sector_weight_before + requested_weight
        checks.append(
            {
                "label": "Sector concentration",
                "observed": _format_rule_pct(observed_sector_weight),
                "cap": f"{_format_rule_pct(sector_cap)} cap",
                "passed": observed_sector_weight <= sector_cap + 1e-9,
            }
        )
    if approved_weight < requested_weight:
        checks.append(
            {
                "label": "Approved size",
                "observed": _format_rule_pct(approved_weight),
                "cap": f"{_format_rule_pct(requested_weight)} requested",
                "passed": False,
            }
        )
    return checks


def _format_rule_pct(value: float) -> str:
    return f"{float(value) * 100:.1f}%"


def _is_macro_only_bearish(request: TradeRiskRequest) -> bool:
    if request.candidate.direction != "bearish":
        return False
    blocked_sources = {"macro", "valuation", "rsi", "generic_extended_stock"}
    signal_sources = set(request.bearish_signal_sources)
    return bool(signal_sources) and signal_sources.issubset(blocked_sources) and not request.direct_company_negative_evidence


def _has_missing_or_stale_signals(request: TradeRiskRequest) -> bool:
    for signal_family, status in request.signal_freshness.items():
        if status not in _BLOCKING_SIGNAL_STATUSES:
            continue
        if (
            signal_family == "insider"
            and request.candidate.strategy_id not in _INSIDER_REQUIRED_STRATEGIES
        ):
            continue
        return True
    return False


def _effective_sector_cap(request: TradeRiskRequest, config: RiskLimitConfig) -> float:
    cap = config.max_sector_weight
    if request.beta_bucket == "high":
        cap -= 0.01
    if request.volatility_bucket == "high":
        cap -= 0.01
    if request.liquidity_bucket == "thin":
        cap -= 0.01
    return max(0.05, cap)


def _sector_weight_for_request(*, request: TradeRiskRequest, portfolio_context: PortfolioContext) -> float:
    if not request.sector or portfolio_context.account_equity <= 0:
        return 0.0
    sector_notional = sum(
        abs(position.notional_exposure)
        for position in portfolio_context.positions
        if position.sector == request.sector
    )
    return sector_notional / portfolio_context.account_equity


def _matching_planner_position_action(
    portfolio_risk_intent: PortfolioRiskIntentRecord | None,
    *,
    ticker: str,
    trade_identity: str,
) -> PositionRiskActionRecord | None:
    if portfolio_risk_intent is None:
        return None
    matches = [
        action
        for action in portfolio_risk_intent.position_actions
        if action.ticker == ticker and action.trade_identity == trade_identity
    ]
    if not matches:
        return None
    priority = {"block_open": 0, "force_reduce": 1, "reduce": 2, "allow": 3}
    return sorted(matches, key=lambda action: priority.get(action.action, 99))[0]


def _generated_hedge_action(portfolio_risk_intent: PortfolioRiskIntentRecord | None) -> dict[str, object] | None:
    if portfolio_risk_intent is None or not portfolio_risk_intent.hedge_actions:
        return None
    return _hedge_action_payload(portfolio_risk_intent.hedge_actions[0])


def _hedge_risk_source(portfolio_risk_intent: PortfolioRiskIntentRecord | None) -> str | None:
    if portfolio_risk_intent is None or not portfolio_risk_intent.hedge_actions:
        return None
    return portfolio_risk_intent.hedge_actions[0].risk_source


def _hedge_action_payload(action: HedgeActionRecord) -> dict[str, object]:
    return {
        "action": action.action,
        "risk_source": action.risk_source,
        "severity": action.severity,
        "target_underlier": action.target_underlier,
        "target_exposure_type": action.target_exposure_type,
        "coverage_ratio": action.coverage_ratio,
        "reason_code": action.reason_code,
        "metadata_json": dict(action.metadata_json),
    }


def _top_risk_sources_for_decision(
    *,
    portfolio_risk_intent: PortfolioRiskIntentRecord | None,
    lookahead_risk_source: str | None,
) -> list[str]:
    values = list(dict(getattr(portfolio_risk_intent, "metadata_json", {}) or {}).get("top_risk_sources", ()) or ())
    if lookahead_risk_source and lookahead_risk_source not in values:
        values.append(lookahead_risk_source)
    return [str(value) for value in values if str(value)]


def _hedge_posture_metadata(portfolio_risk_intent: PortfolioRiskIntentRecord | None) -> dict[str, object] | None:
    metadata_json = dict(getattr(portfolio_risk_intent, "metadata_json", {}) or {})
    posture = metadata_json.get("hedge_posture")
    if isinstance(posture, dict):
        return dict(posture)
    return None


def _data_availability_issues(portfolio_risk_intent: PortfolioRiskIntentRecord | None) -> tuple[str, ...]:
    metadata_json = dict(getattr(portfolio_risk_intent, "metadata_json", {}) or {})
    values = metadata_json.get("data_availability_issues", ())
    if not isinstance(values, (list, tuple)):
        return ()
    return tuple(str(value) for value in values if str(value))
