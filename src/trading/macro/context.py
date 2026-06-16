"""Canonical macro point-in-time contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class MacroSnapshotRecord:
    """Canonical macro snapshot consumed across risk and web read models."""

    macro_snapshot_id: str
    snapshot_time: datetime
    trade_date: date
    regime: str
    risk_budget_multiplier: float
    volatility_state: str | None
    rates_state: str | None
    liquidity_state: str | None
    blocked_strategy_tags: tuple[str, ...]
    invalidators: tuple[str, ...]
    source_freshness: dict[str, Any]
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.snapshot_time.date() != self.trade_date:
            raise ValueError("trade_date must match snapshot_time.date()")

    @property
    def source_set_key(self) -> str:
        keys = sorted(str(key) for key in self.source_freshness.keys())
        return "|".join(keys)


@dataclass(frozen=True)
class MacroReadthroughEventRecord:
    """Structured peer/sector/theme read-through event for macro-aware decisions."""

    macro_readthrough_event_id: str
    event_key: str
    source_ticker: str
    affected_ticker: str | None
    scope: str
    mechanism: str
    direction: str | None
    title: str
    source: str
    event_time: datetime
    published_at: datetime
    available_for_decision_at: datetime
    valid_until: datetime | None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ticker", self.source_ticker.strip().upper())
        if self.affected_ticker is not None:
            object.__setattr__(self, "affected_ticker", self.affected_ticker.strip().upper())
        if self.available_for_decision_at < self.published_at:
            raise ValueError("available_for_decision_at cannot be earlier than published_at")
