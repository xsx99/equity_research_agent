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


@dataclass(frozen=True)
class AssetSnapshot:
    """Frozen loader-facing asset attributes used during ranking."""

    ticker: str
    average_dollar_volume: float | None
    freshness_session_lag: int | None = None
    freshness_classification: str | None = None
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "source_refs", tuple(sorted(set(self.source_refs))))


@dataclass(frozen=True)
class PeerBasketMembership:
    """Point-in-time membership of one ticker in a configured peer basket."""

    ticker: str
    basket_id: str
    valid_from: datetime
    valid_to: datetime | None
    available_for_decision_at: datetime
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "basket_id", self.basket_id.strip())
        object.__setattr__(self, "source_refs", tuple(sorted(set(self.source_refs))))


@dataclass(frozen=True)
class TickerRelationship:
    """Point-in-time sector or industry relationship supplied by a loader."""

    ticker: str
    relationship_type: str
    relationship_id: str
    valid_from: datetime
    valid_to: datetime | None
    available_for_decision_at: datetime
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "relationship_type", self.relationship_type.strip().lower())
        object.__setattr__(self, "relationship_id", self.relationship_id.strip())
        object.__setattr__(self, "source_refs", tuple(sorted(set(self.source_refs))))


@dataclass(frozen=True)
class CohortSelection:
    """Exact cohort membership and provenance chosen for one component."""

    cohort_type: str
    cohort_id: str | None
    members: tuple[str, ...]
    source_refs: tuple[str, ...]
    fallback: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "members", tuple(sorted(set(self.members))))
        object.__setattr__(self, "source_refs", tuple(sorted(set(self.source_refs))))

    @classmethod
    def unavailable(cls, cohort_type: str = "unavailable") -> CohortSelection:
        return cls("unavailable", None, (), (), fallback=cohort_type)

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass(frozen=True)
class CohortResolution:
    """All candidate and selected cohorts used for one ticker's replay."""

    ticker: str
    configured_peer: CohortSelection
    industry: CohortSelection
    peer: CohortSelection
    sector: CohortSelection
    relative_volume: CohortSelection
    raw_configured_peer_relative_20d: float | None
    raw_industry_relative_20d: float | None
    raw_sector_relative_20d: float | None
    market: CohortSelection | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())


@dataclass(frozen=True)
class NormalizedRankingComponents:
    """Normalized positive components and penalty inputs for v1 scoring."""

    peer_or_fallback_20d_percentile: float | None
    sector_or_fallback_20d_percentile: float | None
    market_20d_alpha_percentile: float | None
    relative_strength_60d_persistence: float | None
    multi_horizon_direction_agreement: float | None
    relative_volume_percentile: float | None
    realized_volatility_percentile: float | None
    drawdown_severity_percentile: float | None
    one_day_concentration_20d: float | None


@dataclass(frozen=True)
class Contributor:
    """One deterministic explanation item."""

    name: str
    value: float
    impact: float


@dataclass(frozen=True)
class ScoreBreakdown:
    """Pure v1 score result before confidence and cross-row ordering."""

    status: str
    score: float | None
    positive_score: float | None
    concentration_penalty: float
    volatility_penalty: float
    drawdown_penalty: float
    risk_penalty: float
    coverage: float
    missing_inputs: tuple[str, ...]
    positive_contributors: tuple[Contributor, ...]
    negative_contributors: tuple[Contributor, ...]


@dataclass(frozen=True)
class RankedTicker:
    """A full-cohort output row with replayable scoring metadata."""

    ticker: str
    status: str
    score: float | None
    confidence: float
    coverage: float
    freshness: float
    cohort_quality: float
    benchmark_coverage: float
    average_dollar_volume: float | None
    overall_rank: int | None
    overall_percentile: float | None
    forced_reasons: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    normalized_metrics: tuple[tuple[str, float | None], ...]
    positive_contributors: tuple[Contributor, ...]
    negative_contributors: tuple[Contributor, ...]
    cohort_resolution: CohortResolution


@dataclass(frozen=True)
class RankingResult:
    """Complete cohort plus independent automatic and research selections."""

    full_cohort: tuple[RankedTicker, ...]
    automatic_tickers: tuple[str, ...]
    research_tickers: tuple[str, ...]
