"""Risk hedge overlay records for PR7."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RiskHedgeDecisionRecord:
    risk_hedge_decision_id: str
    risk_decision_id: str | None
    ticker: str
    trade_identity: str
    action: str
    option_strategy_type: str
    rationale: str
    hedge_cost: float
    protected_notional: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        risk_decision_id: str | None,
        ticker: str,
        action: str,
        option_strategy_type: str,
        rationale: str,
        hedge_cost: float,
        protected_notional: float,
        metadata_json: dict[str, Any] | None = None,
    ) -> "RiskHedgeDecisionRecord":
        return cls(
            risk_hedge_decision_id=str(uuid.uuid4()),
            risk_decision_id=risk_decision_id,
            ticker=ticker,
            trade_identity="risk_hedge_overlay",
            action=action,
            option_strategy_type=option_strategy_type,
            rationale=rationale,
            hedge_cost=hedge_cost,
            protected_notional=protected_notional,
            metadata_json=metadata_json or {},
        )
