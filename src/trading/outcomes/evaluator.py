"""Pure directional candidate-outcome math with explicit audit semantics."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DirectionalOutcome:
    """Directional metrics independent of persistence and market-data providers."""

    candidate_return: float | None
    alpha: float | None
    max_favorable_excursion: float | None
    max_adverse_excursion: float | None
    comparator_information_ratio: float | None
    directional_edge_eligible: bool
    evaluation_disposition: str
    metadata_json: dict[str, object]


_DIRECTION_SIGN = {
    "bullish": 1.0,
    "long": 1.0,
    "bearish": -1.0,
    "short": -1.0,
    "risk_off": -1.0,
}


def evaluate_directional_outcome(
    *,
    direction: str,
    candidate_start_price: float,
    candidate_end_price: float,
    path_high_prices: Iterable[float],
    path_low_prices: Iterable[float],
    primary_comparator_return: float | None,
    aligned_active_returns: Iterable[float],
) -> DirectionalOutcome:
    """Evaluate one persisted thesis without guessing direction from free text."""
    if candidate_start_price == 0:
        raise ValueError("candidate_start_price_must_be_nonzero")

    raw_return = (candidate_end_price - candidate_start_price) / candidate_start_price
    raw_high_returns = tuple((price - candidate_start_price) / candidate_start_price for price in path_high_prices)
    raw_low_returns = tuple((price - candidate_start_price) / candidate_start_price for price in path_low_prices)
    normalized_direction = direction.strip().lower()
    sign = _DIRECTION_SIGN.get(normalized_direction)
    raw_mfe = max(raw_high_returns, default=raw_return)
    raw_mae = min(raw_low_returns, default=raw_return)
    metadata: dict[str, object] = {
        "underlying_return": raw_return,
        "raw_max_favorable_excursion": raw_mfe,
        "raw_max_adverse_excursion": raw_mae,
        "direction": normalized_direction,
    }

    if normalized_direction == "neutral":
        return DirectionalOutcome(
            candidate_return=raw_return,
            alpha=None,
            max_favorable_excursion=raw_mfe,
            max_adverse_excursion=raw_mae,
            comparator_information_ratio=None,
            directional_edge_eligible=False,
            evaluation_disposition="observational",
            metadata_json=metadata,
        )
    if sign is None:
        metadata["evaluation_disposition"] = "unsupported_direction"
        return DirectionalOutcome(
            candidate_return=raw_return,
            alpha=None,
            max_favorable_excursion=raw_mfe,
            max_adverse_excursion=raw_mae,
            comparator_information_ratio=None,
            directional_edge_eligible=False,
            evaluation_disposition="unsupported_direction",
            metadata_json=metadata,
        )

    directional_return = sign * raw_return
    directional_alpha = (
        sign * (raw_return - primary_comparator_return)
        if primary_comparator_return is not None
        else None
    )
    directional_path = tuple(sign * value for value in (*raw_high_returns, *raw_low_returns, raw_return))
    information_ratio = _annualized_information_ratio(
        tuple(sign * value for value in aligned_active_returns)
    )
    metadata["directional_edge_eligible"] = True
    return DirectionalOutcome(
        candidate_return=directional_return,
        alpha=directional_alpha,
        max_favorable_excursion=max(directional_path),
        max_adverse_excursion=min(directional_path),
        comparator_information_ratio=information_ratio,
        directional_edge_eligible=True,
        evaluation_disposition="directional",
        metadata_json=metadata,
    )


def _annualized_information_ratio(active_returns: tuple[float, ...]) -> float | None:
    if len(active_returns) < 2:
        return None
    deviation = statistics.stdev(active_returns)
    if deviation == 0:
        return None
    return statistics.mean(active_returns) / deviation * math.sqrt(252)
