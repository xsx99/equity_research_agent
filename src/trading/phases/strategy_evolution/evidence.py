"""Deterministic evidence gates for PR52 strategy evolution."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.trading.phases.replay.outcomes import CandidateOutcomeEvaluationRecord


LONG_HORIZON_LOOKBACK_DAYS = 60


@dataclass(frozen=True)
class EvidenceGatePolicy:
    min_final_outcomes: int = 3
    min_distinct_trade_dates: int = 3
    min_distinct_tickers: int = 2
    min_win_rate: float = 0.60
    min_mean_alpha: float = 0.0


@dataclass(frozen=True)
class EvidenceGateResult:
    passed: bool
    reason_code: str
    metrics_json: dict[str, object]


def evaluate_proposal_evidence(
    *,
    supporting_outcome_ids: Iterable[str],
    outcomes: Iterable[CandidateOutcomeEvaluationRecord],
    policy: EvidenceGatePolicy = EvidenceGatePolicy(),
) -> EvidenceGateResult:
    """Evaluate cited outcome ids against deterministic multi-day evidence gates."""
    requested_ids = tuple(str(outcome_id) for outcome_id in supporting_outcome_ids if str(outcome_id))
    all_outcomes = tuple(outcomes)
    indexed = {str(row.candidate_outcome_evaluation_id): row for row in all_outcomes}
    missing_ids = tuple(outcome_id for outcome_id in requested_ids if outcome_id not in indexed)
    cited_rows = tuple(indexed[outcome_id] for outcome_id in requested_ids if outcome_id in indexed)
    final_rows = tuple(row for row in cited_rows if row.evaluation_status == "final")
    interim_rows = tuple(row for row in cited_rows if row.evaluation_status == "interim")
    alphas = tuple(float(row.alpha) for row in final_rows if row.alpha is not None)
    win_rate = (sum(1 for alpha in alphas if alpha > 0) / len(alphas)) if alphas else 0.0
    mean_alpha = (sum(alphas) / len(alphas)) if alphas else None
    trade_dates = {row.decision_time.date().isoformat() for row in final_rows}
    tickers = {row.ticker for row in final_rows}
    regimes = {row.regime for row in final_rows if row.regime}
    sector_themes = {row.sector_theme for row in final_rows if row.sector_theme}
    metrics_json: dict[str, object] = {
        "passed": False,
        "supporting_outcome_ids": list(requested_ids),
        "missing_outcome_ids": list(missing_ids),
        "final_outcome_count": len(final_rows),
        "interim_outcome_count": len(interim_rows),
        "distinct_trade_dates": len(trade_dates),
        "distinct_tickers": len(tickers),
        "win_rate": win_rate,
        "mean_alpha": mean_alpha,
        "distinct_regimes": len(regimes),
        "distinct_sector_themes": len(sector_themes),
        "sector_theme_counts": _counts(row.sector_theme for row in final_rows if row.sector_theme),
        "regime_counts": _counts(row.regime for row in final_rows if row.regime),
    }
    reason_code = _reason_code(
        requested_ids=requested_ids,
        missing_ids=missing_ids,
        final_rows=final_rows,
        alphas=alphas,
        distinct_trade_dates=len(trade_dates),
        distinct_tickers=len(tickers),
        win_rate=win_rate,
        mean_alpha=mean_alpha,
        policy=policy,
    )
    if reason_code == "passed":
        metrics_json["passed"] = True
        return EvidenceGateResult(passed=True, reason_code="passed", metrics_json=metrics_json)
    return EvidenceGateResult(passed=False, reason_code=reason_code, metrics_json=metrics_json)


def _reason_code(
    *,
    requested_ids: tuple[str, ...],
    missing_ids: tuple[str, ...],
    final_rows: tuple[CandidateOutcomeEvaluationRecord, ...],
    alphas: tuple[float, ...],
    distinct_trade_dates: int,
    distinct_tickers: int,
    win_rate: float,
    mean_alpha: float | None,
    policy: EvidenceGatePolicy,
) -> str:
    if not requested_ids:
        return "missing_supporting_outcome_ids"
    if missing_ids:
        return "missing_supporting_outcome_ids"
    if len(final_rows) < policy.min_final_outcomes:
        return "insufficient_final_outcomes"
    if distinct_trade_dates < policy.min_distinct_trade_dates:
        return "insufficient_distinct_trade_dates"
    if distinct_tickers < policy.min_distinct_tickers:
        return "insufficient_distinct_tickers"
    if len(alphas) < policy.min_final_outcomes:
        return "insufficient_alpha_observations"
    if win_rate < policy.min_win_rate:
        return "insufficient_win_rate"
    if mean_alpha is None or mean_alpha <= policy.min_mean_alpha:
        return "insufficient_mean_alpha"
    return "passed"


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts
