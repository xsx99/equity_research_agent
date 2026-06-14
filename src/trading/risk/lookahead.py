"""Pure lookahead risk-planning contracts."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PositionRiskActionRecord:
    """Deterministic planner action applied to one position or pending trade."""

    ticker: str
    trade_identity: str
    action: str
    risk_source: str
    severity: str
    max_allowed_weight_override: float | None
    reason_code: str
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HedgeActionRecord:
    """Deterministic planner hedge intent before execution materialization."""

    action: str
    risk_source: str
    severity: str
    target_underlier: str
    target_exposure_type: str
    coverage_ratio: float
    reason_code: str
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioEventRiskAssessmentRecord:
    """Lookahead event assessment attached to portfolio names or pending trades."""

    ticker: str
    risk_source: str
    severity: str
    event_type: str | None
    days_until_event: int | None
    affects_existing_position: bool
    affects_pending_trade: bool
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioRiskIntentRecord:
    """Persisted lookahead risk intent emitted before final trade approval."""

    portfolio_risk_intent_id: str
    portfolio_risk_snapshot_id: str | None
    decision_time: datetime
    risk_window: str
    aggregate_risk_state: str
    position_actions: tuple[PositionRiskActionRecord, ...]
    hedge_actions: tuple[HedgeActionRecord, ...]
    binding_constraints: tuple[str, ...]
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        decision_time: datetime,
        risk_window: str,
        aggregate_risk_state: str,
        position_actions: tuple[PositionRiskActionRecord, ...] = (),
        hedge_actions: tuple[HedgeActionRecord, ...] = (),
        binding_constraints: tuple[str, ...] = (),
        portfolio_risk_snapshot_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> "PortfolioRiskIntentRecord":
        return cls(
            portfolio_risk_intent_id=str(uuid.uuid4()),
            portfolio_risk_snapshot_id=portfolio_risk_snapshot_id,
            decision_time=decision_time,
            risk_window=risk_window,
            aggregate_risk_state=aggregate_risk_state,
            position_actions=position_actions,
            hedge_actions=hedge_actions,
            binding_constraints=binding_constraints,
            metadata_json=metadata_json or {},
        )
