"""Canonical portfolio event-risk contracts."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PortfolioEventRiskAssessmentRecord:
    """Portfolio-specific event-risk assessment with point-in-time metadata."""

    ticker: str
    risk_source: str
    severity: str
    event_type: str | None
    days_until_event: int | None
    affects_existing_position: bool
    affects_pending_trade: bool
    portfolio_event_risk_assessment_id: str | None = None
    calendar_event_id: str | None = None
    portfolio_risk_snapshot_id: str | None = None
    decision_time: datetime | None = None
    available_for_decision_at: datetime | None = None
    recommended_action: str = "monitor"
    rationale: str = ""
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())


class PortfolioEventRiskAssessmentPipeline:
    """Build portfolio-aware event-risk assessments from normalized calendar events."""

    def __init__(self, *, now: callable | None = None) -> None:
        self.now = now or datetime.utcnow

    def build_assessments(
        self,
        *,
        calendar_events: tuple[object, ...],
        portfolio_context: object,
        pending_candidates: tuple[dict[str, Any], ...],
        decision_time: datetime,
        portfolio_risk_snapshot_id: str | None = None,
    ) -> tuple[PortfolioEventRiskAssessmentRecord, ...]:
        positions_by_ticker = {
            str(getattr(position, "ticker", "")).upper(): position
            for position in tuple(getattr(portfolio_context, "positions", ()) or ())
        }
        candidates_by_ticker = {
            str(candidate.get("ticker", "")).upper(): candidate
            for candidate in pending_candidates
        }
        assessments: list[PortfolioEventRiskAssessmentRecord] = []
        for event in calendar_events:
            ticker = getattr(event, "ticker", None)
            symbol = str(ticker).upper() if isinstance(ticker, str) else None
            affects_existing_position = symbol in positions_by_ticker if symbol else False
            affects_pending_trade = symbol in candidates_by_ticker if symbol else False
            if not _is_relevant_event(
                event=event,
                affects_existing_position=affects_existing_position,
                affects_pending_trade=affects_pending_trade,
                portfolio_has_exposure=bool(positions_by_ticker or candidates_by_ticker),
                decision_time=decision_time,
            ):
                continue
            risk_source = _risk_source(event)
            days_until_event = max((getattr(event, "event_time").date() - decision_time.date()).days, 0)
            position = positions_by_ticker.get(symbol or "")
            candidate = candidates_by_ticker.get(symbol or "")
            assessment = PortfolioEventRiskAssessmentRecord(
                portfolio_event_risk_assessment_id=str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"{getattr(event, 'event_key')}|{symbol or 'macro'}|{risk_source}")
                ),
                calendar_event_id=str(getattr(event, "calendar_event_id")),
                portfolio_risk_snapshot_id=portfolio_risk_snapshot_id,
                decision_time=decision_time,
                available_for_decision_at=getattr(event, "available_for_decision_at"),
                ticker=symbol or "PORTFOLIO",
                risk_source=risk_source,
                severity=_severity(event),
                event_type=getattr(event, "event_type"),
                days_until_event=days_until_event,
                affects_existing_position=affects_existing_position,
                affects_pending_trade=affects_pending_trade,
                recommended_action=_recommended_action(
                    risk_source=risk_source,
                    days_until_event=days_until_event,
                    affects_existing_position=affects_existing_position,
                    affects_pending_trade=affects_pending_trade,
                ),
                rationale=_rationale(
                    risk_source=risk_source,
                    event_title=str(getattr(event, "title")),
                    days_until_event=days_until_event,
                ),
                metadata_json={
                    "position_notional": float(getattr(position, "notional_exposure", 0.0) or 0.0),
                    "candidate_score_id": candidate.get("candidate_score_id") if candidate else None,
                    "relationship_context": dict(getattr(event, "metadata_json", {}) or {}).get("relationship_context"),
                    "why_visible": _why_visible(
                        affects_existing_position=affects_existing_position,
                        affects_pending_trade=affects_pending_trade,
                    ),
                    "default_visibility": "show",
                    "summary_bucket": risk_source,
                },
            )
            assessments.append(assessment)
        return tuple(assessments)


def _is_relevant_event(
    *,
    event: object,
    affects_existing_position: bool,
    affects_pending_trade: bool,
    portfolio_has_exposure: bool,
    decision_time: datetime,
) -> bool:
    if affects_existing_position or affects_pending_trade:
        return True
    if getattr(event, "event_type", None) == "macro":
        severity = _severity(event)
        days_until_event = (getattr(event, "event_time").date() - decision_time.date()).days
        return portfolio_has_exposure and severity in {"high", "critical"} and days_until_event <= 3
    return False


def _risk_source(event: object) -> str:
    event_type = str(getattr(event, "event_type", ""))
    if event_type == "earnings":
        return "own_event"
    if event_type == "readthrough":
        return "readthrough"
    if event_type == "macro":
        return "macro"
    if event_type == "option_expiry":
        return "option_expiry"
    return "company_specific"


def _severity(event: object) -> str:
    severity = str(getattr(event, "severity_hint", "medium") or "medium").lower()
    if severity not in {"low", "medium", "high", "critical", "watch"}:
        return "medium"
    return severity


def _recommended_action(
    *,
    risk_source: str,
    days_until_event: int,
    affects_existing_position: bool,
    affects_pending_trade: bool,
) -> str:
    if risk_source == "own_event" and affects_pending_trade and days_until_event <= 5:
        return "block_open"
    if risk_source in {"macro", "option_expiry"}:
        return "tighten_risk"
    if affects_existing_position:
        return "review_position"
    return "monitor"


def _rationale(*, risk_source: str, event_title: str, days_until_event: int) -> str:
    return f"{event_title} maps to {risk_source} risk within {days_until_event} day(s)."


def _why_visible(*, affects_existing_position: bool, affects_pending_trade: bool) -> str:
    if affects_existing_position and affects_pending_trade:
        return "existing_position_and_pending_trade"
    if affects_existing_position:
        return "existing_position"
    if affects_pending_trade:
        return "pending_trade"
    return "portfolio_context"
