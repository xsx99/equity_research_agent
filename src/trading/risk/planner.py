"""Deterministic portfolio hedge planning for near-term lookahead risk."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from src.trading.risk.config import RiskLimitConfig
from src.trading.risk.context import PortfolioContext
from src.trading.risk.lookahead import (
    HedgeActionRecord,
    PortfolioEventRiskAssessmentRecord,
    PortfolioRiskIntentRecord,
    PositionRiskActionRecord,
)


@dataclass(frozen=True)
class PendingTradeRiskRecord:
    """Minimal pending-trade exposure used by the planner."""

    ticker: str
    trade_identity: str
    sector: str | None
    event_type: str | None
    macro_sensitivity: str | None
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioHedgePlannerRequest:
    """Pure planner input for `1-5` trading day lookahead risk."""

    decision_time: datetime
    risk_window: str
    portfolio_context: PortfolioContext
    risk_limit_config: RiskLimitConfig
    event_assessments: tuple[PortfolioEventRiskAssessmentRecord, ...]
    pending_trades: tuple[PendingTradeRiskRecord, ...]
    macro_risk_state: str | None = None


class PortfolioHedgePlanner:
    """Deterministic rules for near-term macro and event-driven risk intent."""

    def plan(self, request: PortfolioHedgePlannerRequest) -> PortfolioRiskIntentRecord:
        position_actions: list[PositionRiskActionRecord] = []
        hedge_actions: list[HedgeActionRecord] = []
        binding_constraints: list[str] = []

        for assessment in request.event_assessments:
            self._apply_own_event_rules(assessment, request, position_actions, binding_constraints)

        for assessment in request.event_assessments:
            self._apply_cluster_rules(assessment, request, position_actions, hedge_actions, binding_constraints)

        if request.macro_risk_state in {"watch", "high", "critical"}:
            severity = request.macro_risk_state
            underlier = _broad_underlier(request)
            hedge_actions.append(
                HedgeActionRecord(
                    action=_hedge_overlay_action(request, target_underlier=underlier),
                    risk_source="macro",
                    severity=severity,
                    target_underlier=underlier,
                    target_exposure_type="broad_market",
                    coverage_ratio=_coverage_ratio(severity),
                    reason_code=f"macro_{severity}_overlay",
                    metadata_json={"risk_window": request.risk_window},
                )
            )
            binding_constraints.append(f"macro_{severity}_overlay")
        elif not hedge_actions:
            existing_overlay = _first_existing_overlay(request)
            if existing_overlay is not None:
                hedge_actions.append(
                    HedgeActionRecord(
                        action="close_hedge",
                        risk_source="risk_normalized",
                        severity="watch",
                        target_underlier=existing_overlay.ticker,
                        target_exposure_type="broad_market",
                        coverage_ratio=1.0,
                        reason_code="risk_overlay_normalized",
                        metadata_json={"risk_window": request.risk_window},
                    )
                )
                binding_constraints.append("risk_overlay_normalized")

        aggregate_risk_state = _aggregate_risk_state(
            position_actions=position_actions,
            hedge_actions=hedge_actions,
            macro_risk_state=request.macro_risk_state,
        )
        return PortfolioRiskIntentRecord.create(
            portfolio_risk_snapshot_id=None,
            decision_time=request.decision_time,
            risk_window=request.risk_window,
            aggregate_risk_state=aggregate_risk_state,
            position_actions=tuple(position_actions),
            hedge_actions=tuple(hedge_actions),
            binding_constraints=tuple(binding_constraints),
            metadata_json={},
        )

    def _apply_own_event_rules(
        self,
        assessment: PortfolioEventRiskAssessmentRecord,
        request: PortfolioHedgePlannerRequest,
        position_actions: list[PositionRiskActionRecord],
        binding_constraints: list[str],
    ) -> None:
        if assessment.risk_source != "own_event":
            return
        if assessment.days_until_event is not None and assessment.days_until_event > 5:
            return

        for pending_trade in request.pending_trades:
            if pending_trade.ticker != assessment.ticker or not assessment.affects_pending_trade:
                continue
            if pending_trade.trade_identity.startswith("tactical_"):
                position_actions.append(
                    PositionRiskActionRecord(
                        ticker=pending_trade.ticker,
                        trade_identity=pending_trade.trade_identity,
                        action="block_open",
                        risk_source="own_event",
                        severity=assessment.severity,
                        max_allowed_weight_override=None,
                        reason_code="own_event_block",
                        metadata_json={"days_until_event": assessment.days_until_event},
                    )
                )
                binding_constraints.append("own_event_block")

        for position in request.portfolio_context.positions:
            if position.ticker != assessment.ticker or not assessment.affects_existing_position:
                continue
            action = "allow" if position.trade_identity == "core_holding" else "force_reduce"
            reason_code = "core_holding_event_review" if action == "allow" else "own_event_force_reduce"
            position_actions.append(
                PositionRiskActionRecord(
                    ticker=position.ticker,
                    trade_identity=position.trade_identity,
                    action=action,
                    risk_source="own_event",
                    severity=assessment.severity,
                    max_allowed_weight_override=None,
                    reason_code=reason_code,
                    metadata_json={"days_until_event": assessment.days_until_event},
                )
            )
            binding_constraints.append(reason_code)

    def _apply_cluster_rules(
        self,
        assessment: PortfolioEventRiskAssessmentRecord,
        request: PortfolioHedgePlannerRequest,
        position_actions: list[PositionRiskActionRecord],
        hedge_actions: list[HedgeActionRecord],
        binding_constraints: list[str],
    ) -> None:
        if assessment.risk_source not in {"sector_event_cluster", "event_cluster"}:
            return
        sector = _sector_for_ticker(assessment.ticker, request)
        if sector is None:
            return

        for position in request.portfolio_context.positions:
            if position.ticker != assessment.ticker or not assessment.affects_existing_position:
                continue
            action = "allow" if position.trade_identity == "core_holding" else "reduce"
            reason_code = "cluster_core_holding_allow" if action == "allow" else "cluster_reduce"
            position_actions.append(
                PositionRiskActionRecord(
                    ticker=position.ticker,
                    trade_identity=position.trade_identity,
                    action=action,
                    risk_source="sector_event_cluster",
                    severity=assessment.severity,
                    max_allowed_weight_override=None,
                    reason_code=reason_code,
                    metadata_json={"sector": sector},
                )
            )
            binding_constraints.append(reason_code)

        underlier = _sector_underlier(sector)
        if underlier is None:
            return
        hedge_actions.append(
            HedgeActionRecord(
                action=_hedge_overlay_action(request, target_underlier=underlier),
                risk_source="sector_event_cluster",
                severity=assessment.severity,
                target_underlier=underlier,
                target_exposure_type="sector",
                coverage_ratio=_coverage_ratio(assessment.severity),
                reason_code="sector_cluster_hedge",
                metadata_json={"sector": sector},
            )
        )
        binding_constraints.append("sector_cluster_hedge")


def _aggregate_risk_state(
    *,
    position_actions: list[PositionRiskActionRecord],
    hedge_actions: list[HedgeActionRecord],
    macro_risk_state: str | None,
) -> str:
    if any(action.risk_source == "own_event" for action in position_actions):
        return "mixed_risk"
    if any(action.risk_source == "sector_event_cluster" for action in hedge_actions):
        return "event_cluster_risk"
    if macro_risk_state == "watch":
        return "macro_watch"
    if macro_risk_state in {"high", "critical"}:
        return "macro_high_risk"
    return "risk_normalized"


def _coverage_ratio(severity: str) -> float:
    return {
        "watch": 0.25,
        "high": 0.50,
        "critical": 0.75,
    }.get(severity, 0.25)


def _sector_for_ticker(ticker: str, request: PortfolioHedgePlannerRequest) -> str | None:
    for position in request.portfolio_context.positions:
        if position.ticker == ticker and position.sector:
            return position.sector
    for pending_trade in request.pending_trades:
        if pending_trade.ticker == ticker and pending_trade.sector:
            return pending_trade.sector
    return None


def _sector_underlier(sector: str | None) -> str | None:
    return {
        "Technology": "XLK",
        "Financials": "XLF",
        "Energy": "XLE",
        "Semiconductors": "SMH",
    }.get(str(sector or ""))


def _broad_underlier(request: PortfolioHedgePlannerRequest) -> str:
    sectors = list(_sector_values(request))
    if any(sector in {"Technology", "Semiconductors"} for sector in sectors):
        return "QQQ"
    return "SPY"


def _sector_values(request: PortfolioHedgePlannerRequest) -> Iterable[str]:
    for position in request.portfolio_context.positions:
        if position.sector:
            yield position.sector
    for pending_trade in request.pending_trades:
        if pending_trade.sector:
            yield pending_trade.sector


def _hedge_overlay_action(
    request: PortfolioHedgePlannerRequest,
    *,
    target_underlier: str,
) -> str:
    return "adjust_hedge" if _has_existing_overlay(request, target_underlier=target_underlier) else "open_hedge"


def _has_existing_overlay(
    request: PortfolioHedgePlannerRequest,
    *,
    target_underlier: str,
) -> bool:
    return any(
        position.trade_identity == "risk_hedge_overlay" and position.ticker == target_underlier
        for position in request.portfolio_context.positions
    )


def _first_existing_overlay(request: PortfolioHedgePlannerRequest):
    for position in request.portfolio_context.positions:
        if position.trade_identity == "risk_hedge_overlay":
            return position
    return None
