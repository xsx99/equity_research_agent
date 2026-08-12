from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import uuid

from src.db.models.trading import CandidateOutcomeEvaluation, HistoricalReplayRun
from src.trading.phases.replay.historical import HistoricalReplayRunRecord
from src.trading.phases.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter_by(self, **values):
        rows = [row for row in self.rows if all(getattr(row, key) == value for key, value in values.items())]
        return _Query(rows)

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self):
        self.rows = {}
        self.flush_count = 0

    def query(self, model):
        return _Query(self.rows.get(model, []))

    def add(self, row):
        self.rows.setdefault(type(row), []).append(row)

    def flush(self):
        self.flush_count += 1


def _run() -> HistoricalReplayRunRecord:
    now = datetime(2026, 7, 7, 20, tzinfo=timezone.utc)
    return HistoricalReplayRunRecord(
        historical_replay_run_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "outcome-run")),
        decision_time=datetime(2026, 7, 2, 13, 30, tzinfo=timezone.utc),
        snapshot_type="manual",
        status="succeeded",
        started_at=now,
        completed_at=now,
        decision_filter_json={"source": "persisted"},
        outcome_horizon_policy_json={"typical_horizon": "intraday-2d"},
        evaluation_as_of_session=now,
        metadata_json={"mode": "persisted_candidate_maturation"},
    )


def _outcome(run_id: str) -> CandidateOutcomeEvaluationRecord:
    moment = datetime(2026, 7, 7, 20, tzinfo=timezone.utc)
    return CandidateOutcomeEvaluationRecord(
        candidate_outcome_evaluation_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "outcome-row")),
        historical_replay_run_id=run_id,
        candidate_score_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "candidate-row")),
        trade_classification_id=None,
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        trade_identity="tactical_stock_trade",
        direction="bullish",
        catalyst_type=None,
        confidence_bucket="test",
        decision_time=datetime(2026, 7, 2, 13, 30, tzinfo=timezone.utc),
        horizon_start_at=datetime(2026, 7, 2, 13, 30, tzinfo=timezone.utc),
        horizon_end_at=moment,
        evaluation_status="final",
        candidate_return=0.1,
        benchmark_returns={"QQQ": 0.02},
        peer_basket_id=None,
        peer_basket_return=None,
        alpha=0.08,
        max_favorable_excursion=0.12,
        max_adverse_excursion=-0.02,
        regime=None,
        sector_theme=None,
        metadata_json={"finalization_reason": "horizon_expired"},
    )


def test_sqlalchemy_repository_upserts_maturation_run_and_checkpoint_outcome():
    session = _Session()
    repository = SqlAlchemyTradingRepository(session)
    run = _run()
    outcome = _outcome(run.historical_replay_run_id)

    repository.save_historical_replay_run(run)
    repository.save_historical_replay_run(run)
    repository.save_candidate_outcome_evaluations((outcome,))
    repository.save_candidate_outcome_evaluations((outcome,))

    persisted_run = session.query(HistoricalReplayRun).one_or_none()
    persisted_outcome = session.query(CandidateOutcomeEvaluation).one_or_none()
    assert persisted_run.evaluation_as_of_session == run.evaluation_as_of_session
    assert persisted_run.metadata_json == {"mode": "persisted_candidate_maturation"}
    assert persisted_outcome.alpha == Decimal("0.08")
    assert persisted_outcome.benchmark_returns_json == {"QQQ": 0.02}
    assert session.flush_count == 4
