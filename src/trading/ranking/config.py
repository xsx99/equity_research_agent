"""Frozen configuration for the cross-sectional relative-strength v1 model."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RankingConfig:
    """Serializable constants that define the frozen v1 ranking model."""

    alpha_windows: tuple[int, ...] = (5, 20, 60)
    return_windows: tuple[int, ...] = (1, 5, 20, 60)
    relative_volume_window: int = 20
    realized_volatility_window: int = 20
    drawdown_window: int = 60
    concentration_window: int = 20
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
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
