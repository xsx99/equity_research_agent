"""Frozen configuration for the cross-sectional relative-strength v1 model."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from math import isclose, isfinite
from typing import Any


V1_RETURN_WINDOWS = (1, 5, 20, 60)
V1_ALPHA_WINDOWS = (5, 20, 60)
V1_RELATIVE_VOLUME_WINDOW = 20
V1_REALIZED_VOLATILITY_WINDOW = 20
V1_DRAWDOWN_WINDOW = 60
V1_CONCENTRATION_WINDOW = 20
V1_MINIMUM_BATCH_REQUEST_SESSIONS = max(V1_RETURN_WINDOWS) + 1


@dataclass(frozen=True)
class RankingConfig:
    """Serializable constants that define the frozen v1 ranking model."""

    alpha_windows: tuple[int, ...] = V1_ALPHA_WINDOWS
    return_windows: tuple[int, ...] = V1_RETURN_WINDOWS
    relative_volume_window: int = V1_RELATIVE_VOLUME_WINDOW
    realized_volatility_window: int = V1_REALIZED_VOLATILITY_WINDOW
    drawdown_window: int = V1_DRAWDOWN_WINDOW
    concentration_window: int = V1_CONCENTRATION_WINDOW
    batch_request_sessions: int = 65
    top_n: int = 100
    min_cohort_size: int = 10
    confidence_floor: float = 0.60
    model_version: str = "cross_sectional_rs_v1"

    peer_weight: float = 0.30
    sector_weight: float = 0.20
    market_alpha_weight: float = 0.15
    persistence_weight: float = 0.15
    direction_agreement_weight: float = 0.10
    relative_volume_weight: float = 0.10

    concentration_penalty_start: float = 0.35
    concentration_penalty_full: float = 0.65
    concentration_penalty_max: float = 0.10
    risk_percentile_penalty_start: float = 0.50
    volatility_penalty_max: float = 0.05
    drawdown_penalty_max: float = 0.05

    confidence_component_coverage_weight: float = 0.50
    confidence_freshness_weight: float = 0.20
    confidence_cohort_quality_weight: float = 0.20
    confidence_benchmark_coverage_weight: float = 0.10
    full_cohort_size: int = 30
    singleton_percentile: float = 0.50

    def __post_init__(self) -> None:
        object.__setattr__(self, "alpha_windows", tuple(self.alpha_windows))
        object.__setattr__(self, "return_windows", tuple(self.return_windows))
        _validate_windows("alpha_windows", self.alpha_windows)
        _validate_windows("return_windows", self.return_windows)
        _validate_exact_v1("alpha_windows", self.alpha_windows, V1_ALPHA_WINDOWS)
        _validate_exact_v1("return_windows", self.return_windows, V1_RETURN_WINDOWS)
        for field_name in (
            "relative_volume_window",
            "realized_volatility_window",
            "drawdown_window",
            "concentration_window",
            "batch_request_sessions",
            "top_n",
            "min_cohort_size",
            "full_cohort_size",
        ):
            _validate_positive_integer(field_name, getattr(self, field_name))
        for field_name, expected in (
            ("relative_volume_window", V1_RELATIVE_VOLUME_WINDOW),
            ("realized_volatility_window", V1_REALIZED_VOLATILITY_WINDOW),
            ("drawdown_window", V1_DRAWDOWN_WINDOW),
            ("concentration_window", V1_CONCENTRATION_WINDOW),
        ):
            _validate_exact_v1(field_name, getattr(self, field_name), expected)
        if self.batch_request_sessions < V1_MINIMUM_BATCH_REQUEST_SESSIONS:
            raise ValueError(
                "batch_request_sessions must cover at least 61 sessions for v1"
            )
        for field_name in (
            "confidence_floor",
            "peer_weight",
            "sector_weight",
            "market_alpha_weight",
            "persistence_weight",
            "direction_agreement_weight",
            "relative_volume_weight",
            "concentration_penalty_start",
            "concentration_penalty_full",
            "concentration_penalty_max",
            "risk_percentile_penalty_start",
            "volatility_penalty_max",
            "drawdown_penalty_max",
            "confidence_component_coverage_weight",
            "confidence_freshness_weight",
            "confidence_cohort_quality_weight",
            "confidence_benchmark_coverage_weight",
            "singleton_percentile",
        ):
            _validate_unit_interval(field_name, getattr(self, field_name))
        if self.concentration_penalty_full <= self.concentration_penalty_start:
            raise ValueError(
                "concentration_penalty_full must exceed concentration_penalty_start"
            )
        if not isclose(sum(self.positive_weights.values()), 1.0):
            raise ValueError("positive component weights must sum to 1")
        confidence_weight_total = sum(
            (
                self.confidence_component_coverage_weight,
                self.confidence_freshness_weight,
                self.confidence_cohort_quality_weight,
                self.confidence_benchmark_coverage_weight,
            )
        )
        if not isclose(confidence_weight_total, 1.0):
            raise ValueError("confidence weights must sum to 1")

    @property
    def positive_weights(self) -> dict[str, float]:
        return {
            "peer_or_fallback_20d_percentile": self.peer_weight,
            "sector_or_fallback_20d_percentile": self.sector_weight,
            "market_20d_alpha_percentile": self.market_alpha_weight,
            "relative_strength_60d_persistence": self.persistence_weight,
            "multi_horizon_direction_agreement": self.direction_agreement_weight,
            "relative_volume_percentile": self.relative_volume_weight,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-compatible representation."""
        payload = asdict(self)
        payload["alpha_windows"] = list(self.alpha_windows)
        payload["return_windows"] = list(self.return_windows)
        payload["positive_weights"] = self.positive_weights
        return payload

    def to_json(self) -> str:
        """Serialize using stable key ordering and separators for replay hashes."""
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def _validate_windows(field_name: str, windows: tuple[int, ...]) -> None:
    if not windows:
        raise ValueError(f"{field_name} must not be empty")
    if any(
        not isinstance(window, int) or isinstance(window, bool) or window <= 0
        for window in windows
    ):
        raise ValueError(f"{field_name} must contain only positive integers")
    if tuple(sorted(set(windows))) != windows:
        raise ValueError(f"{field_name} must be strictly increasing and unique")


def _validate_positive_integer(field_name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _validate_exact_v1(field_name: str, value: object, expected: object) -> None:
    if value != expected:
        raise ValueError(f"{field_name} is frozen at {expected!r} for cross_sectional_rs_v1")


def _validate_unit_interval(field_name: str, value: float) -> None:
    if not isfinite(value) or value < 0 or value > 1:
        raise ValueError(f"{field_name} must be finite and between 0 and 1")
