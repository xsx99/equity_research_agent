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
    ) -> RiskDecisionRecord:
        snapshot = self.build_portfolio_risk_snapshot(portfolio_context, config)
        if request.classification.trade_identity == "core_holding" and request.candidate.ticker not in portfolio_context.approved_core_tickers:
            return self._decision(
                request,
                sizing,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="rejected",
                reason_code="core_holding_requires_portfolio_intent",
                approved_weight=0.0,
                applied_rules=["core_holding_intent_check"],
            )

        if _has_missing_or_stale_signals(request):
            return self._decision(
                request,
                sizing,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="rejected",
                reason_code="missing_or_stale_signals",
                approved_weight=0.0,
                applied_rules=["signal_freshness_check"],
            )

        if request.instrument_type == "stock" and _is_macro_only_bearish(request):
            return self._decision(
                request,
                sizing,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="rejected",
                reason_code="macro_only_bearish_single_name_blocked",
                approved_weight=0.0,
                applied_rules=["bearish_evidence_gate"],
            )

        if request.estimated_margin_requirement is None or request.estimated_buying_power_effect is None:
            return self._decision(
                request,
                sizing,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="rejected",
                reason_code="unestimable_margin_requirement",
                approved_weight=0.0,
                applied_rules=["margin_estimation_check"],
            )

        if request.instrument_type == "option" and not request.option_risk_metadata_complete:
            return self._decision(
                request,
                sizing,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="rejected",
                reason_code="missing_option_risk_metadata",
                approved_weight=0.0,
                applied_rules=["option_metadata_check"],
            )

        sector_weight = self._current_sector_weight(request.sector, portfolio_context)
        effective_sector_cap = _effective_sector_cap(request, config)
        proposed_weight = sector_weight + sizing.final_weight
        if request.sector and proposed_weight > effective_sector_cap:
            approved_weight = max(0.0, effective_sector_cap - sector_weight)
            return self._decision(
                request,
                sizing,
                snapshot_id=snapshot.portfolio_risk_snapshot_id,
                status="reduced" if approved_weight > 0 else "rejected",
                reason_code="sector_concentration_cap",
                approved_weight=approved_weight,
                applied_rules=["sector_concentration_check"],
            )

        return self._decision(
            request,
            sizing,
            snapshot_id=snapshot.portfolio_risk_snapshot_id,
            status="approved",
            reason_code="within_limits",
            approved_weight=sizing.final_weight,
            applied_rules=["single_name_limit_ok", "sector_concentration_ok"],
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
        snapshot_id: str | None,
        status: str,
        reason_code: str,
        approved_weight: float,
        applied_rules: list[str],
    ) -> RiskDecisionRecord:
        approved_notional = approved_weight * (sizing.final_notional / sizing.final_weight) if sizing.final_weight > 0 else 0.0
        approved_quantity = approved_notional / request.price if request.price > 0 else 0.0
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
            decision_time=request.candidate.decision_time,
        )


def _beta_multiplier(beta_bucket: str | None) -> float:
    return {
        "low": 0.75,
        "medium": 1.0,
        "high": 1.2,
    }.get(str(beta_bucket or "").lower(), 1.0)


def _is_macro_only_bearish(request: TradeRiskRequest) -> bool:
    if request.candidate.direction != "bearish":
        return False
    blocked_sources = {"macro", "valuation", "rsi", "generic_extended_stock"}
    signal_sources = set(request.bearish_signal_sources)
    return bool(signal_sources) and signal_sources.issubset(blocked_sources) and not request.direct_company_negative_evidence


def _has_missing_or_stale_signals(request: TradeRiskRequest) -> bool:
    return any(status in {"missing", "stale", "failed"} for status in request.signal_freshness.values())


def _effective_sector_cap(request: TradeRiskRequest, config: RiskLimitConfig) -> float:
    cap = config.max_sector_weight
    if request.beta_bucket == "high":
        cap -= 0.01
    if request.volatility_bucket == "high":
        cap -= 0.01
    if request.liquidity_bucket == "thin":
        cap -= 0.01
    return max(0.05, cap)
