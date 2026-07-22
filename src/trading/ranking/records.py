"""Immutable records for point-in-time relative-strength metrics."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class AdjustedDailyBar:
    """One daily bar and the provenance required to use it at decision time."""

    session_date: date
    close: float | None
    volume: float | None
    available_for_decision_at: datetime
    is_adjusted: bool = True
    split_adjusted: bool = True
    adjustment_source: str | None = None
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_refs", tuple(self.source_refs))


@dataclass(frozen=True)
class NormalizedBarSet:
    """Decision-time-filtered bars and their aggregate provenance."""

    bars: tuple[AdjustedDailyBar, ...]
    invalid_reason: str | None
    source_refs: tuple[str, ...]
    adjustment_sources: tuple[str, ...]
    max_available_for_decision_at: datetime | None


@dataclass(frozen=True)
class RawRankingMetrics:
    """Raw v1 inputs calculated before cross-sectional normalization."""

    ticker: str
    return_1d: float | None
    return_5d: float | None
    return_20d: float | None
    return_60d: float | None
    alpha_vs_spy_5d: float | None
    alpha_vs_spy_20d: float | None
    alpha_vs_spy_60d: float | None
    relative_volume_20d: float | None
    realized_volatility_20d: float | None
    drawdown_60d: float | None
    one_day_concentration_20d: float | None
    is_fully_eligible: bool
    missing_inputs: tuple[str, ...]
    bar_count: int
    last_bar_date: date | None
    all_bars_adjusted: bool
    all_bars_split_adjusted: bool
    adjustment_sources: tuple[str, ...]
    source_refs: tuple[str, ...]
    max_available_for_decision_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "missing_inputs", tuple(self.missing_inputs))
        object.__setattr__(self, "adjustment_sources", tuple(self.adjustment_sources))
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
