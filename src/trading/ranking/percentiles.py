"""Deterministic percentile and liquidity-bucket helpers."""
from __future__ import annotations

from collections.abc import Mapping
from math import isfinite


def average_rank_percentiles(
    values_by_key: Mapping[str, float | None],
    *,
    singleton_percentile: float = 0.5,
) -> dict[str, float | None]:
    """Return ascending zero-based average-rank percentiles, excluding missing values."""
    present = sorted(_finite_items(values_by_key), key=lambda item: (item[1], item[0]))
    result: dict[str, float | None] = {key: None for key in values_by_key}
    if len(present) == 1:
        result[present[0][0]] = singleton_percentile
        return result
    if not present:
        return result

    index = 0
    denominator = len(present) - 1
    while index < len(present):
        end = index + 1
        while end < len(present) and present[end][1] == present[index][1]:
            end += 1
        average_rank = (index + end - 1) / 2
        percentile = average_rank / denominator
        for key, _ in present[index:end]:
            result[key] = percentile
        index = end
    return result


def liquidity_quartiles(
    dollar_volumes_by_key: Mapping[str, float | None],
    *,
    values_are_percentiles: bool = False,
) -> dict[str, str | None]:
    """Assign q1-q4 using average-rank dollar-volume percentiles."""
    percentiles = (
        dict(dollar_volumes_by_key)
        if values_are_percentiles
        else average_rank_percentiles(dollar_volumes_by_key)
    )
    return {key: _quartile(value) for key, value in percentiles.items()}


def _quartile(percentile: float | None) -> str | None:
    if percentile is None or not isfinite(percentile):
        return None
    if percentile < 0.25:
        return "q1"
    if percentile < 0.50:
        return "q2"
    if percentile < 0.75:
        return "q3"
    return "q4"


def _finite_items(
    values_by_key: Mapping[str, float | None],
) -> list[tuple[str, float]]:
    items: list[tuple[str, float]] = []
    for key, value in values_by_key.items():
        if value is None:
            continue
        numeric_value = float(value)
        if isfinite(numeric_value):
            items.append((key, numeric_value))
    return items
