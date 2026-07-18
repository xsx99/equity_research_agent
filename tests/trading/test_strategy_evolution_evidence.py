from __future__ import annotations

from datetime import datetime, timezone

from src.trading.phases.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.phases.strategy_evolution.evidence import EvidenceGatePolicy, evaluate_proposal_evidence


def _outcome(
    outcome_id: str,
    *,
    ticker: str,
    decision_time: datetime,
    alpha: float | None,
    evaluation_status: str = "final",
    sector_theme: str = "software",
) -> CandidateOutcomeEvaluationRecord:
    return CandidateOutcomeEvaluationRecord(
        candidate_outcome_evaluation_id=outcome_id,
        historical_replay_run_id=None,
        candidate_score_id=None,
        trade_classification_id=None,
        ticker=ticker,
        strategy_id="post_gap_vwap_reclaim_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        trade_identity="watch_only",
        direction="bullish",
        catalyst_type="earnings",
        confidence_bucket="bucket",
        decision_time=decision_time,
        horizon_start_at=decision_time,
        horizon_end_at=decision_time,
        evaluation_status=evaluation_status,
        candidate_return=0.03,
        benchmark_returns={"QQQ": 0.01},
        peer_basket_id=None,
        peer_basket_return=None,
        alpha=alpha,
        max_favorable_excursion=0.04,
        max_adverse_excursion=-0.01,
        regime="neutral",
        sector_theme=sector_theme,
        metadata_json={},
    )


def test_proposal_evidence_gate_rejects_single_day_outcomes():
    same_day = datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc)
    metrics = evaluate_proposal_evidence(
        supporting_outcome_ids=("outcome-1", "outcome-2", "outcome-3"),
        outcomes=(
            _outcome("outcome-1", ticker="AAPL", decision_time=same_day, alpha=0.03),
            _outcome("outcome-2", ticker="MSFT", decision_time=same_day, alpha=0.02),
            _outcome("outcome-3", ticker="NVDA", decision_time=same_day, alpha=-0.01),
        ),
        policy=EvidenceGatePolicy(),
    )

    assert metrics.passed is False
    assert metrics.reason_code == "insufficient_distinct_trade_dates"


def test_proposal_evidence_gate_accepts_multi_day_positive_alpha():
    metrics = evaluate_proposal_evidence(
        supporting_outcome_ids=("outcome-1", "outcome-2", "outcome-3"),
        outcomes=(
            _outcome("outcome-1", ticker="AAPL", decision_time=datetime(2026, 6, 1, tzinfo=timezone.utc), alpha=0.03),
            _outcome("outcome-2", ticker="MSFT", decision_time=datetime(2026, 6, 2, tzinfo=timezone.utc), alpha=0.02),
            _outcome("outcome-3", ticker="NVDA", decision_time=datetime(2026, 6, 3, tzinfo=timezone.utc), alpha=-0.01),
        ),
        policy=EvidenceGatePolicy(),
    )

    assert metrics.passed is True
    assert metrics.metrics_json["final_outcome_count"] == 3
    assert metrics.metrics_json["distinct_trade_dates"] == 3
    assert metrics.metrics_json["win_rate"] >= 0.6
