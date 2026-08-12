"""Final outcome boundary rules for selected versus observational candidates."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OutcomeFinalization:
    horizon_end_at: datetime
    reason: str


def resolve_finalization(
    *,
    trade_identity: str,
    has_complete_close: bool,
    complete_close_at: datetime | None,
    horizon_end_at: datetime,
) -> OutcomeFinalization:
    """Use actual close only for a selected, fully closed trade path."""
    selected_identity = trade_identity in {
        "core_holding",
        "tactical_stock_trade",
        "tactical_option_trade",
        "risk_hedge_overlay",
    }
    if (
        selected_identity
        and has_complete_close
        and complete_close_at is not None
        and complete_close_at < horizon_end_at
    ):
        return OutcomeFinalization(horizon_end_at=complete_close_at, reason="trade_closed")
    return OutcomeFinalization(horizon_end_at=horizon_end_at, reason="horizon_expired")
