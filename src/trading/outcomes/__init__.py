"""Deterministic production candidate-outcome primitives."""

from src.trading.outcomes.evaluator import DirectionalOutcome, evaluate_directional_outcome
from src.trading.outcomes.horizons import OutcomeCheckpoints, OutcomeHorizonPolicy, UnsupportedOutcomeHorizon
from src.trading.outcomes.lineage import persisted_candidate_maturation_run_id
from src.trading.outcomes.finalization import OutcomeFinalization, resolve_finalization
from src.trading.outcomes.pipeline import OutcomeEvaluationPipeline, OutcomeEvaluationResult, PersistedCandidateOutcomeContext

__all__ = [
    "DirectionalOutcome",
    "OutcomeCheckpoints",
    "OutcomeHorizonPolicy",
    "OutcomeEvaluationPipeline",
    "OutcomeEvaluationResult",
    "OutcomeFinalization",
    "UnsupportedOutcomeHorizon",
    "evaluate_directional_outcome",
    "persisted_candidate_maturation_run_id",
    "PersistedCandidateOutcomeContext",
    "resolve_finalization",
]
