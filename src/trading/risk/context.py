"""Pure risk-context contracts for deterministic PR04 sizing and approval."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord


@dataclass(frozen=True)
class PortfolioPosition:
    """One open portfolio exposure used for deterministic PR04 risk checks."""

    ticker: str
    quantity: float
    market_value: float
    notional_exposure: float
    trade_identity: str
    direction: str
    sector: str | None
    strategy_id: str | None
    intended_horizon: str | None
    beta_bucket: str | None
    volatility_bucket: str | None
    liquidity_bucket: str | None
    event_type: str | None
    macro_sensitivity: str | None
    margin_requirement: float
    option_margin_requirement: float = 0.0
    assignment_notional: float = 0.0


@dataclass(frozen=True)
class RiskFactorExposureRecord:
    """Aggregate exposure for one factor bucket."""

    factor_type: str
    factor_value: str
    gross_exposure: float
    net_exposure: float
    long_exposure: float
    short_exposure: float
    position_count: int
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioContext:
    """Explicit portfolio/account context for PR04 risk logic."""

    as_of: datetime
    account_equity: float
    cash_balance: float
    buying_power: float
    excess_liquidity: float
    positions: tuple[PortfolioPosition, ...]
    open_strategy_exposure: dict[str, float]
    current_factor_exposure: tuple[RiskFactorExposureRecord, ...]
    stock_margin_requirement: float
    option_margin_requirement: float
    total_margin_requirement: float
    initial_margin_requirement: float | None = None
    maintenance_margin_requirement: float | None = None
    approved_core_tickers: tuple[str, ...] = ()
    margin_model_profile: str = "estimated_fidelity_like_conservative_v1"
    margin_model_version: str = "v1"
    margin_requirement_source: str = "estimated"
    broker_reported_margin_requirement: float | None = None


@dataclass(frozen=True)
class TradeRiskRequest:
    """Deterministic trade request entering PR04 sizing and risk approval."""

    candidate: CandidateScoreRecord
    classification: TradeClassificationRecord
    instrument_type: str
    target_weight: float
    confidence: float
    sector: str | None
    beta_bucket: str | None
    volatility_bucket: str | None
    liquidity_bucket: str | None
    event_type: str | None
    macro_sensitivity: str | None
    price: float
    atr_pct: float
    average_daily_dollar_volume: float
    signal_freshness: dict[str, str]
    estimated_margin_requirement: float | None
    estimated_buying_power_effect: float | None
    estimated_initial_margin_requirement: float | None
    estimated_maintenance_margin_requirement: float | None
    broker_reported_margin_requirement: float | None = None
    assignment_notional: float = 0.0
    direct_company_negative_evidence: bool = False
    bearish_signal_sources: tuple[str, ...] = ()
    option_risk_metadata_complete: bool = True
    event_date_distance: int | None = None
    event_through_horizon: bool | None = None
    core_vs_tactical: str | None = None
    lookahead_macro_state: str | None = None
    lookahead_event_state: str | None = None
    lookahead_cluster_state: str | None = None


@dataclass(frozen=True)
class PositionSizingDecisionRecord:
    """Persistable deterministic sizing output."""

    position_sizing_decision_id: str
    candidate_score_id: str | None
    trade_classification_id: str | None
    ticker: str
    risk_appetite: str
    base_weight: float
    volatility_adjusted_weight: float
    liquidity_capped_weight: float
    final_weight: float
    final_notional: float
    applied_caps: list[str]
    binding_constraint: str | None
    decision_time: datetime
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        candidate_score_id: str | None,
        trade_classification_id: str | None,
        ticker: str,
        risk_appetite: str,
        base_weight: float,
        volatility_adjusted_weight: float,
        liquidity_capped_weight: float,
        final_weight: float,
        final_notional: float,
        applied_caps: list[str],
        binding_constraint: str | None,
        decision_time: datetime,
        metadata_json: dict[str, Any] | None = None,
    ) -> "PositionSizingDecisionRecord":
        return cls(
            position_sizing_decision_id=str(uuid.uuid4()),
            candidate_score_id=candidate_score_id,
            trade_classification_id=trade_classification_id,
            ticker=ticker,
            risk_appetite=risk_appetite,
            base_weight=base_weight,
            volatility_adjusted_weight=volatility_adjusted_weight,
            liquidity_capped_weight=liquidity_capped_weight,
            final_weight=final_weight,
            final_notional=final_notional,
            applied_caps=applied_caps,
            binding_constraint=binding_constraint,
            decision_time=decision_time,
            metadata_json=metadata_json or {},
        )


@dataclass(frozen=True)
class PortfolioRiskSnapshotRecord:
    """Persistable account-level risk snapshot."""

    portfolio_risk_snapshot_id: str
    decision_time: datetime
    risk_appetite: str
    resolver_version: str
    margin_model_profile: str
    margin_model_version: str
    account_equity: float
    cash_balance: float
    buying_power: float
    excess_liquidity: float
    stock_margin_requirement: float
    option_margin_requirement: float
    total_margin_requirement: float
    initial_margin_requirement: float | None
    maintenance_margin_requirement: float | None
    margin_requirement_source: str
    net_exposure: float
    gross_exposure: float
    beta_adjusted_net_exposure: float
    concentration_flags: list[str]
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        decision_time: datetime,
        risk_appetite: str,
        resolver_version: str,
        margin_model_profile: str,
        margin_model_version: str,
        account_equity: float,
        cash_balance: float,
        buying_power: float,
        excess_liquidity: float,
        stock_margin_requirement: float,
        option_margin_requirement: float,
        total_margin_requirement: float,
        initial_margin_requirement: float | None,
        maintenance_margin_requirement: float | None,
        margin_requirement_source: str,
        net_exposure: float,
        gross_exposure: float,
        beta_adjusted_net_exposure: float,
        concentration_flags: list[str],
        metadata_json: dict[str, Any] | None = None,
    ) -> "PortfolioRiskSnapshotRecord":
        return cls(
            portfolio_risk_snapshot_id=str(uuid.uuid4()),
            decision_time=decision_time,
            risk_appetite=risk_appetite,
            resolver_version=resolver_version,
            margin_model_profile=margin_model_profile,
            margin_model_version=margin_model_version,
            account_equity=account_equity,
            cash_balance=cash_balance,
            buying_power=buying_power,
            excess_liquidity=excess_liquidity,
            stock_margin_requirement=stock_margin_requirement,
            option_margin_requirement=option_margin_requirement,
            total_margin_requirement=total_margin_requirement,
            initial_margin_requirement=initial_margin_requirement,
            maintenance_margin_requirement=maintenance_margin_requirement,
            margin_requirement_source=margin_requirement_source,
            net_exposure=net_exposure,
            gross_exposure=gross_exposure,
            beta_adjusted_net_exposure=beta_adjusted_net_exposure,
            concentration_flags=concentration_flags,
            metadata_json=metadata_json or {},
        )


@dataclass(frozen=True)
class RiskDecisionRecord:
    """Persistable final risk decision."""

    risk_decision_id: str
    candidate_score_id: str | None
    trade_classification_id: str | None
    position_sizing_decision_id: str | None
    ticker: str
    status: str
    reason_code: str
    approved_weight: float
    approved_notional: float
    approved_quantity: float
    portfolio_risk_snapshot_id: str | None
    applied_rules: list[str]
    generated_hedge_action: dict[str, Any] | None
    decision_time: datetime
    binding_constraint: str | None = None
    lookahead_risk_source: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        candidate_score_id: str | None,
        trade_classification_id: str | None,
        position_sizing_decision_id: str | None,
        ticker: str,
        status: str,
        reason_code: str,
        approved_weight: float,
        approved_notional: float,
        approved_quantity: float,
        portfolio_risk_snapshot_id: str | None,
        applied_rules: list[str],
        decision_time: datetime,
        binding_constraint: str | None = None,
        lookahead_risk_source: str | None = None,
        generated_hedge_action: dict[str, Any] | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> "RiskDecisionRecord":
        return cls(
            risk_decision_id=str(uuid.uuid4()),
            candidate_score_id=candidate_score_id,
            trade_classification_id=trade_classification_id,
            position_sizing_decision_id=position_sizing_decision_id,
            ticker=ticker,
            status=status,
            reason_code=reason_code,
            approved_weight=approved_weight,
            approved_notional=approved_notional,
            approved_quantity=approved_quantity,
            portfolio_risk_snapshot_id=portfolio_risk_snapshot_id,
            applied_rules=applied_rules,
            binding_constraint=binding_constraint,
            lookahead_risk_source=lookahead_risk_source,
            generated_hedge_action=generated_hedge_action,
            decision_time=decision_time,
            metadata_json=metadata_json or {},
        )
