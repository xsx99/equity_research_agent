"""Compatibility shim for the strategy scoring pipeline."""
from __future__ import annotations

from src.trading.strategies.scoring import (
    StrategyPipeline,
    StrategyPipelineResult,
)

__all__ = [
    "StrategyPipeline",
    "StrategyPipelineResult",
]
