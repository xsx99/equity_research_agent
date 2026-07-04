"""Compatibility shim for post-close strategy-evolution records and pipeline."""
from __future__ import annotations

import sys

from src.trading.phases.strategy_evolution import pipeline as _canonical

COMPUTABLE_REQUIRED_SIGNALS = _canonical.COMPUTABLE_REQUIRED_SIGNALS
StrategyEvaluationResultRecord = _canonical.StrategyEvaluationResultRecord
StrategyEvolutionPipeline = _canonical.StrategyEvolutionPipeline
StrategyEvolutionRequest = _canonical.StrategyEvolutionRequest
StrategyEvolutionResult = _canonical.StrategyEvolutionResult
StrategyProposalRecord = _canonical.StrategyProposalRecord
find_duplicate_strategy = _canonical.find_duplicate_strategy
maybe_promote_strategy_from_outcomes = _canonical.maybe_promote_strategy_from_outcomes
required_signals_are_computable = _canonical.required_signals_are_computable

__all__ = [
    "COMPUTABLE_REQUIRED_SIGNALS",
    "StrategyEvaluationResultRecord",
    "StrategyEvolutionPipeline",
    "StrategyEvolutionRequest",
    "StrategyEvolutionResult",
    "StrategyProposalRecord",
    "find_duplicate_strategy",
    "maybe_promote_strategy_from_outcomes",
    "required_signals_are_computable",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
