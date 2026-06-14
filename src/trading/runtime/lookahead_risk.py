"""Helpers for pre-open and intraday lookahead risk orchestration."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from src.trading.risk import (
    PendingTradeRiskRecord,
    PortfolioEventRiskAssessmentRecord,
    PortfolioHedgePlanner,
    PortfolioHedgePlannerRequest,
    PortfolioRiskIntentRecord,
    RiskDecisionRecord,
)


class LookaheadRiskWorkflowHelper:
    """Build planner intent and materialize at most one residual hedge payload."""

    def __init__(self, *, hedge_planner: PortfolioHedgePlanner | None = None) -> None:
        self.hedge_planner = hedge_planner or PortfolioHedgePlanner()

    def build_preopen_portfolio_risk_intent(
        self,
        *,
        candidates: tuple[object, ...],
        classifications: tuple[object, ...],
        signal_by_id: dict[str, object],
        portfolio_context: object,
        config: object,
        decision_time: datetime,
        portfolio_risk_snapshot_id: str | None,
    ) -> PortfolioRiskIntentRecord:
        if not hasattr(portfolio_context, "positions"):
            return PortfolioRiskIntentRecord.create(
                portfolio_risk_snapshot_id=portfolio_risk_snapshot_id,
                decision_time=decision_time,
                risk_window="1-5d",
                aggregate_risk_state="risk_normalized",
            )

        candidate_by_id = {getattr(candidate, "candidate_score_id", None): candidate for candidate in candidates}
        pending_trades: list[PendingTradeRiskRecord] = []
        event_assessments: list[PortfolioEventRiskAssessmentRecord] = []
        for classification in classifications:
            candidate = candidate_by_id.get(getattr(classification, "candidate_score_id", None))
            if candidate is None:
                continue
            snapshot = signal_by_id.get(getattr(candidate, "signal_snapshot_id", ""))
            earnings_in_days = _earnings_in_days(snapshot)
            event_type = "earnings" if earnings_in_days is not None and earnings_in_days >= 0 else None
            pending_trades.append(
                PendingTradeRiskRecord(
                    ticker=str(candidate.ticker),
                    trade_identity=str(getattr(classification, "trade_identity", "")),
                    sector=_sector_from_snapshot(snapshot),
                    event_type=event_type,
                    macro_sensitivity=None,
                )
            )
            if earnings_in_days is not None and 0 <= earnings_in_days <= 5:
                event_assessments.append(
                    PortfolioEventRiskAssessmentRecord(
                        ticker=str(candidate.ticker),
                        risk_source="own_event",
                        severity="high",
                        event_type="earnings",
                        days_until_event=earnings_in_days,
                        affects_existing_position=False,
                        affects_pending_trade=True,
                        metadata_json={},
                    )
                )
        return self.hedge_planner.plan(
            PortfolioHedgePlannerRequest(
                decision_time=decision_time,
                risk_window="1-5d",
                portfolio_context=portfolio_context,
                risk_limit_config=config,
                event_assessments=tuple(event_assessments),
                pending_trades=tuple(pending_trades),
            )
        )

    def build_intraday_portfolio_risk_intent(
        self,
        *,
        rebalance_requests: tuple[object, ...],
        portfolio_context: object,
        config: object,
        decision_time: datetime,
        macro_risk_state: str | None,
    ) -> PortfolioRiskIntentRecord:
        if not hasattr(portfolio_context, "positions"):
            return PortfolioRiskIntentRecord.create(
                portfolio_risk_snapshot_id=None,
                decision_time=decision_time,
                risk_window="1-5d",
                aggregate_risk_state="risk_normalized",
            )

        pending_trades: list[PendingTradeRiskRecord] = []
        event_assessments: list[PortfolioEventRiskAssessmentRecord] = []
        for request in rebalance_requests:
            if not getattr(request, "existing_position", False) and bool(getattr(request, "allow_open_new", False)):
                pending_trades.append(
                    PendingTradeRiskRecord(
                        ticker=str(getattr(request, "ticker", "")),
                        trade_identity=str(getattr(request, "trade_identity", "")),
                        sector=None,
                        event_type=None,
                        macro_sensitivity=None,
                    )
                )
            for alert in tuple(getattr(request, "alerts", ())):
                assessment = _intraday_cluster_assessment(request=request, alert=alert)
                if assessment is None:
                    assessment = _intraday_event_assessment(request=request, alert=alert)
                if assessment is not None:
                    event_assessments.append(assessment)
        return self.hedge_planner.plan(
            PortfolioHedgePlannerRequest(
                decision_time=decision_time,
                risk_window="1-5d",
                portfolio_context=portfolio_context,
                risk_limit_config=config,
                event_assessments=tuple(event_assessments),
                pending_trades=tuple(pending_trades),
                macro_risk_state=macro_risk_state,
            )
        )

    def materialize_generated_hedges(
        self,
        *,
        risk_decisions: tuple[RiskDecisionRecord, ...],
        portfolio_risk_intent: PortfolioRiskIntentRecord,
    ) -> tuple[RiskDecisionRecord, ...]:
        if not portfolio_risk_intent.hedge_actions:
            return risk_decisions
        hedge_action = portfolio_risk_intent.hedge_actions[0]
        approved = [
            decision
            for decision in risk_decisions
            if decision.status in {"approved", "reduced"}
            and _hedge_protected_exposure(
                decision,
                target_exposure_type=hedge_action.target_exposure_type,
            )[1] > 0
        ]
        if not approved:
            return risk_decisions
        carrier = approved[0]
        protected_exposures = [
            _hedge_protected_exposure(
                decision,
                target_exposure_type=hedge_action.target_exposure_type,
            )
            for decision in approved
        ]
        protected_notional = sum(value for _, value in protected_exposures) * hedge_action.coverage_ratio
        payload = {
            "action": hedge_action.action,
            "risk_source": hedge_action.risk_source,
            "severity": hedge_action.severity,
            "target_underlier": hedge_action.target_underlier,
            "target_exposure_type": hedge_action.target_exposure_type,
            "coverage_ratio": hedge_action.coverage_ratio,
            "reason_code": hedge_action.reason_code,
            "option_strategy_type": "long_put",
            "underlying_price": 100.0,
            "protected_notional": protected_notional,
            "protected_exposure_basis": _dominant_protected_exposure_basis(protected_exposures),
            "metadata_json": dict(hedge_action.metadata_json),
        }
        materialized: list[RiskDecisionRecord] = []
        for decision in risk_decisions:
            materialized.append(
                replace(
                    decision,
                    generated_hedge_action=payload if decision.risk_decision_id == carrier.risk_decision_id else None,
                )
            )
        return tuple(materialized)


def _earnings_in_days(snapshot: object | None) -> int | None:
    if snapshot is None:
        return None
    signal_json = dict(getattr(snapshot, "signal_json", {}) or {})
    event_news = dict(signal_json.get("events_news", {}) or {})
    value = event_news.get("earnings_in_days")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _sector_from_snapshot(snapshot: object | None) -> str | None:
    if snapshot is None:
        return None
    signal_json = dict(getattr(snapshot, "signal_json", {}) or {})
    for key in ("fundamental", "company"):
        payload = dict(signal_json.get(key, {}) or {})
        sector = payload.get("sector")
        if isinstance(sector, str) and sector.strip():
            return sector.strip()
    return None


def _sector_from_baseline(baseline: object | None) -> str | None:
    return _sector_from_snapshot(baseline)


def _hedge_protected_exposure(
    decision: RiskDecisionRecord,
    *,
    target_exposure_type: str,
) -> tuple[str, float]:
    metadata_json = dict(decision.metadata_json or {})
    if target_exposure_type == "assignment":
        assignment_notional = float(metadata_json.get("approved_assignment_notional") or 0.0)
        if assignment_notional > 0:
            return ("approved_assignment_notional", assignment_notional)
    for key in (
        "approved_margin_exposure",
        "approved_buying_power_effect",
        "approved_capital_notional",
    ):
        value = float(metadata_json.get(key) or 0.0)
        if value > 0:
            return (key, value)
    return ("approved_notional", max(float(decision.approved_notional), 0.0))


def _dominant_protected_exposure_basis(protected_exposures: list[tuple[str, float]]) -> str:
    if not protected_exposures:
        return "approved_notional"
    basis_totals: dict[str, float] = {}
    for basis, value in protected_exposures:
        basis_totals[basis] = basis_totals.get(basis, 0.0) + value
    return max(basis_totals.items(), key=lambda item: item[1])[0]


def _intraday_event_assessment(
    *,
    request: object,
    alert: object,
) -> PortfolioEventRiskAssessmentRecord | None:
    if not isinstance(alert, dict):
        return None
    severity = str(alert.get("severity") or "low").lower()
    if severity not in {"high", "critical"}:
        return None
    event_type = str(alert.get("alert_type") or "").lower()
    if not any(keyword in event_type for keyword in ("earnings", "guidance", "fda", "litigation", "approval", "trial")):
        return None
    return PortfolioEventRiskAssessmentRecord(
        ticker=str(getattr(request, "ticker", "")),
        risk_source="own_event",
        severity=severity,
        event_type=event_type,
        days_until_event=0,
        affects_existing_position=bool(getattr(request, "existing_position", False)),
        affects_pending_trade=not bool(getattr(request, "existing_position", False)),
        metadata_json={"source": "intraday_alert"},
    )


def _intraday_cluster_assessment(
    *,
    request: object,
    alert: object,
) -> PortfolioEventRiskAssessmentRecord | None:
    if not isinstance(alert, dict):
        return None
    severity = str(alert.get("severity") or "low").lower()
    if severity not in {"high", "critical"}:
        return None
    themes = tuple(alert.get("affected_themes") or ())
    readthrough_source = alert.get("readthrough_source_ticker")
    ticker = str(getattr(request, "ticker", ""))
    sector = dict(getattr(request, "metadata_json", {}) or {}).get("sector")
    if not isinstance(readthrough_source, str) or not readthrough_source.strip():
        return None
    readthrough_source = readthrough_source.strip()
    if readthrough_source == ticker:
        return None
    if not sector:
        return None
    return PortfolioEventRiskAssessmentRecord(
        ticker=ticker,
        risk_source="sector_event_cluster",
        severity=severity,
        event_type=str(alert.get("alert_type") or "readthrough"),
        days_until_event=0,
        affects_existing_position=bool(getattr(request, "existing_position", False)),
        affects_pending_trade=not bool(getattr(request, "existing_position", False)),
        metadata_json={
            "sector": sector,
            "affected_themes": list(themes),
            "readthrough_source_ticker": readthrough_source,
        },
    )
