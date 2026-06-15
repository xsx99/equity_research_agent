"""Option risk and assignment-risk helpers for PR7."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from src.trading.risk.config import RiskLimitConfig
from src.trading.risk.context import PortfolioContext


@dataclass(frozen=True)
class OptionLegRiskInput:
    option_type: str
    side: str
    quantity: int
    strike: float
    expiry: date
    delta: float
    gamma: float
    theta: float
    vega: float
    premium: float


@dataclass(frozen=True)
class OptionRiskInput:
    ticker: str
    trade_identity: str
    option_strategy_type: str
    underlying_price: float
    sector: str | None
    event_type: str | None
    event_through_expiry: bool
    margin_requirement: float
    buying_power_effect: float
    max_loss: float
    max_profit: float | None
    net_debit_or_credit: float
    legs: tuple[OptionLegRiskInput, ...] | list[OptionLegRiskInput]


@dataclass(frozen=True)
class OptionRiskAssessment:
    status: str
    reason_code: str
    worst_case_assignment_notional: float
    portfolio_delta: float
    portfolio_gamma: float
    portfolio_theta: float
    portfolio_vega: float
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OptionRiskSnapshotRecord:
    option_risk_snapshot_id: str
    ticker: str
    trade_identity: str
    option_strategy_type: str
    underlying_price: float
    portfolio_delta: float
    portfolio_gamma: float
    portfolio_theta: float
    portfolio_vega: float
    net_debit_or_credit: float
    max_loss: float
    max_profit: float | None
    margin_requirement: float
    buying_power_effect: float
    assignment_notional: float
    worst_case_assignment_notional: float
    margin_model_profile: str
    margin_model_version: str
    margin_requirement_source: str
    risk_status: str
    reason_code: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        ticker: str,
        trade_identity: str,
        option_strategy_type: str,
        underlying_price: float,
        portfolio_delta: float,
        portfolio_gamma: float,
        portfolio_theta: float,
        portfolio_vega: float,
        net_debit_or_credit: float,
        max_loss: float,
        max_profit: float | None,
        margin_requirement: float,
        buying_power_effect: float,
        assignment_notional: float,
        worst_case_assignment_notional: float,
        margin_model_profile: str,
        margin_model_version: str,
        margin_requirement_source: str,
        risk_status: str,
        reason_code: str,
        created_at: datetime,
        metadata_json: dict[str, Any] | None = None,
    ) -> "OptionRiskSnapshotRecord":
        return cls(
            option_risk_snapshot_id=str(uuid.uuid4()),
            ticker=ticker,
            trade_identity=trade_identity,
            option_strategy_type=option_strategy_type,
            underlying_price=underlying_price,
            portfolio_delta=portfolio_delta,
            portfolio_gamma=portfolio_gamma,
            portfolio_theta=portfolio_theta,
            portfolio_vega=portfolio_vega,
            net_debit_or_credit=net_debit_or_credit,
            max_loss=max_loss,
            max_profit=max_profit,
            margin_requirement=margin_requirement,
            buying_power_effect=buying_power_effect,
            assignment_notional=assignment_notional,
            worst_case_assignment_notional=worst_case_assignment_notional,
            margin_model_profile=margin_model_profile,
            margin_model_version=margin_model_version,
            margin_requirement_source=margin_requirement_source,
            risk_status=risk_status,
            reason_code=reason_code,
            created_at=created_at,
            metadata_json=metadata_json or {},
        )


class OptionRiskManager:
    """Evaluate strategy-level option risk plus assignment exposure."""

    def evaluate_assignment_risk(
        self,
        option_risk: OptionRiskInput,
        *,
        portfolio_context: PortfolioContext,
        config: RiskLimitConfig,
    ) -> OptionRiskAssessment:
        legs = tuple(option_risk.legs)
        assignment_notional = sum(
            leg.strike * leg.quantity * 100.0
            for leg in legs
            if leg.side == "sell"
        )
        total_assignment = assignment_notional + sum(position.assignment_notional for position in portfolio_context.positions)
        delta = sum(leg.delta * leg.quantity * (1 if leg.side == "buy" else -1) for leg in legs)
        gamma = sum(leg.gamma * leg.quantity * (1 if leg.side == "buy" else -1) for leg in legs)
        theta = sum(leg.theta * leg.quantity * (1 if leg.side == "buy" else -1) for leg in legs)
        vega = sum(leg.vega * leg.quantity * (1 if leg.side == "buy" else -1) for leg in legs)

        if portfolio_context.account_equity > 0:
            assignment_ratio = total_assignment / portfolio_context.account_equity
        else:
            assignment_ratio = 1.0
        if _blocks_short_premium_through_event(option_risk):
            return OptionRiskAssessment(
                status="rejected",
                reason_code="event_through_expiry_short_premium_blocked",
                worst_case_assignment_notional=assignment_notional,
                portfolio_delta=delta,
                portfolio_gamma=gamma,
                portfolio_theta=theta,
                portfolio_vega=vega,
                metadata_json={
                    "assignment_ratio": assignment_ratio,
                    "event_type": option_risk.event_type,
                    "event_through_expiry": option_risk.event_through_expiry,
                    "blocked_exposure_basis": "event_through_expiry",
                },
            )
        sector_exposure_after_assignment = _sector_exposure_after_assignment(
            portfolio_context=portfolio_context,
            sector=option_risk.sector,
            assignment_notional=assignment_notional,
        )
        if portfolio_context.account_equity > 0:
            sector_exposure_after_assignment_ratio = (
                sector_exposure_after_assignment / portfolio_context.account_equity
            )
        else:
            sector_exposure_after_assignment_ratio = 1.0
        if (
            option_risk.sector
            and assignment_notional > 0
            and sector_exposure_after_assignment_ratio > config.max_sector_weight
        ):
            return OptionRiskAssessment(
                status="rejected",
                reason_code="assignment_sector_concentration_cap",
                worst_case_assignment_notional=assignment_notional,
                portfolio_delta=delta,
                portfolio_gamma=gamma,
                portfolio_theta=theta,
                portfolio_vega=vega,
                metadata_json={
                    "assignment_ratio": assignment_ratio,
                    "sector": option_risk.sector,
                    "sector_exposure_after_assignment": sector_exposure_after_assignment,
                    "sector_exposure_after_assignment_ratio": sector_exposure_after_assignment_ratio,
                    "blocked_exposure_basis": "sector_after_assignment",
                },
            )
        if assignment_ratio > config.assignment_concentration_limit:
            return OptionRiskAssessment(
                status="rejected",
                reason_code="assignment_concentration_cap",
                worst_case_assignment_notional=assignment_notional,
                portfolio_delta=delta,
                portfolio_gamma=gamma,
                portfolio_theta=theta,
                portfolio_vega=vega,
                metadata_json={
                    "assignment_ratio": assignment_ratio,
                    "assignment_concentration_limit": config.assignment_concentration_limit,
                    "blocked_exposure_basis": "assignment_notional",
                },
            )
        return OptionRiskAssessment(
            status="approved",
            reason_code="within_limits",
            worst_case_assignment_notional=assignment_notional,
            portfolio_delta=delta,
            portfolio_gamma=gamma,
            portfolio_theta=theta,
            portfolio_vega=vega,
            metadata_json={
                "assignment_ratio": assignment_ratio,
                "sector": option_risk.sector,
                "sector_exposure_after_assignment": sector_exposure_after_assignment,
                "sector_exposure_after_assignment_ratio": sector_exposure_after_assignment_ratio,
            },
        )


def _blocks_short_premium_through_event(option_risk: OptionRiskInput) -> bool:
    if not option_risk.event_through_expiry:
        return False
    if option_risk.option_strategy_type not in {"put_credit_spread", "call_credit_spread"}:
        return False
    return any(leg.side == "sell" for leg in option_risk.legs)


def _sector_exposure_after_assignment(
    *,
    portfolio_context: PortfolioContext,
    sector: str | None,
    assignment_notional: float,
) -> float:
    if not sector:
        return 0.0
    current_sector_exposure = sum(
        abs(position.notional_exposure) + float(position.assignment_notional)
        for position in portfolio_context.positions
        if position.sector == sector
    )
    return current_sector_exposure + max(assignment_notional, 0.0)
