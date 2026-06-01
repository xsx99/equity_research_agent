"""Confidence-calibration inputs derived from PR03 classifications and outcomes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.trading.outcome_evaluator import CandidateOutcomeEvaluationRecord
from src.trading.trade_classifier import TradeClassificationRecord


@dataclass(frozen=True)
class ConfidenceCalibrationResult:
    """Calibration summary consumed by later decision agents."""

    confidence_bucket: str
    sample_count: int
    win_rate: float | None
    average_alpha: float | None
    calibrated_confidence: float


class ConfidenceCalibrator:
    """Compute deterministic confidence inputs from historical outcomes."""

    def __init__(self, historical_outcomes: Iterable[CandidateOutcomeEvaluationRecord] = ()) -> None:
        self.historical_outcomes = tuple(historical_outcomes)

    def calibrate(self, classification: TradeClassificationRecord) -> ConfidenceCalibrationResult:
        catalyst_type = _catalyst_type(classification)
        bucket = "|".join(
            (
                classification.selected_strategy_id,
                classification.expression_bucket_id,
                classification.trade_identity,
                classification.direction,
                catalyst_type or "none",
            )
        )
        matches = [
            outcome
            for outcome in self.historical_outcomes
            if outcome.confidence_bucket == bucket and outcome.evaluation_status == "final"
        ]
        if not matches:
            return ConfidenceCalibrationResult(
                confidence_bucket=bucket,
                sample_count=0,
                win_rate=None,
                average_alpha=None,
                calibrated_confidence=0.5,
            )
        wins = sum(1 for outcome in matches if outcome.alpha is not None and outcome.alpha > 0)
        average_alpha = round(sum(outcome.alpha or 0.0 for outcome in matches) / len(matches), 10)
        win_rate = wins / len(matches)
        calibrated = _clamp(0.5 + (win_rate - 0.5) * 0.25 + average_alpha * 2.0)
        return ConfidenceCalibrationResult(
            confidence_bucket=bucket,
            sample_count=len(matches),
            win_rate=win_rate,
            average_alpha=average_alpha,
            calibrated_confidence=calibrated,
        )


def _catalyst_type(classification: TradeClassificationRecord) -> str | None:
    explicit = classification.selected_strategy_context_json.get("catalyst_type")
    if explicit:
        return str(explicit)
    evidence = classification.selected_strategy_context_json.get("core_signal_evidence") or {}
    if isinstance(evidence, dict):
        for key in (
            "events_news.catalyst_type",
            "events_news.own_earnings_event_type",
            "events_news.direct_negative_catalyst_type",
        ):
            if evidence.get(key):
                return str(evidence[key])
    return None


def _clamp(value: float) -> float:
    return max(0.0, min(value, 1.0))
