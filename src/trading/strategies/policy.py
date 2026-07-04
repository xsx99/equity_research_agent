"""Focused post-close policy helpers reused outside pipeline modules."""
from __future__ import annotations


def experimental_strategy_weight_cap(base_cap: float) -> float:
    """Apply the stricter sizing cap used for experimental strategies."""
    return min(base_cap * 0.25, 0.02)
