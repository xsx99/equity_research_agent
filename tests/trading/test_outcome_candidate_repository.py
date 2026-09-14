from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import uuid

from src.db.models.trading import (
    CandidateOutcomeEvaluation,
    CandidateScore,
    HistoricalReplayRun,
    PaperExecution,
    PaperOrder,
    PeerBasket,
    StrategyRun,
    TradeClassification,
    TradingDecision,
    WatchCandidate,
)
from src.trading.phases.replay.historical import HistoricalReplayRunRecord
from src.trading.phases.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.outcomes.context import complete_close_from_lineage
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord, StrategyRunRecord
from src.trading.strategies.selector import WatchCandidateRecord


class _Query:
    def __init__(self, rows, criteria=None):
        self.rows = rows
        self.criteria = criteria

    def filter_by(self, **values):
        rows = [row for row in self.rows if all(getattr(row, key) == value for key, value in values.items())]
        return _Query(rows, self.criteria)

    def filter(self, *_criteria):
        if self.criteria is not None:
            self.criteria.extend(str(item) for item in _criteria)
        return self

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self):
        self.rows = {}
        self.flush_count = 0
        self.criteria = []

    def query(self, model):
        return _Query(self.rows.get(model, []), self.criteria)

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
    repository.save_candidate_outcome_evaluations((replace(outcome, alpha=0.99),))

    persisted_run = session.query(HistoricalReplayRun).one_or_none()
    persisted_outcome = session.query(CandidateOutcomeEvaluation).one_or_none()
    assert persisted_run.evaluation_as_of_session == run.evaluation_as_of_session
    assert persisted_run.metadata_json == {"mode": "persisted_candidate_maturation"}
    assert persisted_outcome.alpha == Decimal("0.08")
    assert persisted_outcome.benchmark_returns_json == {"QQQ": 0.02}
    assert session.flush_count == 4


def test_sqlalchemy_repository_loads_due_persisted_context_and_omits_existing_checkpoint():
    session = _Session()
    candidate_id = uuid.uuid5(uuid.NAMESPACE_URL, "candidate-context")
    run_id = uuid.uuid5(uuid.NAMESPACE_URL, "strategy-run-context")
    classification_id = uuid.uuid5(uuid.NAMESPACE_URL, "classification-context")
    decision_id = uuid.uuid5(uuid.NAMESPACE_URL, "decision-context")
    order_id = uuid.uuid5(uuid.NAMESPACE_URL, "order-context")
    basket_id = uuid.uuid5(uuid.NAMESPACE_URL, "peer-basket-context")
    decision_time = datetime(2026, 7, 2, 13, 30, tzinfo=timezone.utc)
    close_at = datetime(2026, 7, 7, 19, 45, tzinfo=timezone.utc)
    session.rows = {
        StrategyRun: [SimpleNamespace(strategy_run_id=run_id, snapshot_type="manual")],
        CandidateScore: [
            _candidate_row(
                candidate_id=candidate_id,
                run_id=run_id,
                decision_time=decision_time,
                benchmark_context={
                    "primary_benchmark": "SPY",
                    "sector_theme_symbols": ["XLK"],
                    "peer_basket_id": str(basket_id),
                    "opportunity_set_key": "ranked:top2",
                    "opportunity_set_members": [
                        {"symbol": "NVDA", "weight": 0.7},
                        {"symbol": "MSFT", "weight": 0.3},
                    ],
                },
            )
        ],
        TradeClassification: [
            SimpleNamespace(
                trade_classification_id=classification_id,
                candidate_score_id=candidate_id,
                strategy_run_id=run_id,
                ticker="AAPL",
                selected_strategy_id="relative_strength_rotation_v1",
                selected_strategy_version="v1",
                expression_bucket_id="long_stock",
                expression_bucket_version="v1",
                trade_identity="tactical_stock_trade",
                watch_type=None,
                direction="bullish",
                intended_horizon="intraday-2d",
                exit_policy="horizon",
                result_status="actionable_trade",
                classification_reason="selected",
                selected_strategy_context_json={},
                decision_time=decision_time,
            )
        ],
        WatchCandidate: [],
        PeerBasket: [
            SimpleNamespace(
                peer_basket_id=basket_id,
                members_json=[
                    {"symbol": "MSFT", "weight": 0.6},
                    {"symbol": "GOOG", "weight": 0.4},
                ],
            )
        ],
        TradingDecision: [
            SimpleNamespace(
                trading_decision_id=decision_id,
                candidate_score_id=candidate_id,
                trade_classification_id=classification_id,
            )
        ],
        PaperOrder: [
            SimpleNamespace(
                paper_order_id=order_id,
                trading_decision_id=decision_id,
                action="enter_long",
            ),
            SimpleNamespace(
                paper_order_id=uuid.uuid5(uuid.NAMESPACE_URL, "close-order-context"),
                trading_decision_id=decision_id,
                action="exit",
            ),
        ],
        PaperExecution: [],
        CandidateOutcomeEvaluation: [
            SimpleNamespace(
                candidate_score_id=candidate_id,
                evaluation_status="interim",
                horizon_end_at=datetime(2026, 7, 6, 20, tzinfo=timezone.utc),
            )
        ],
    }
    close_order = session.rows[PaperOrder][1]
    session.rows[PaperExecution] = [
        SimpleNamespace(
            paper_order_id=order_id,
            paper_execution_id=uuid.uuid5(uuid.NAMESPACE_URL, "entry-fill-context"),
            quantity=Decimal("10"),
            executed_at=datetime(2026, 7, 2, 14, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            paper_order_id=close_order.paper_order_id,
            paper_execution_id=uuid.uuid5(uuid.NAMESPACE_URL, "close-fill-context"),
            quantity=Decimal("10"),
            executed_at=close_at,
        ),
    ]

    contexts = SqlAlchemyTradingRepository(session).load_due_candidate_outcome_contexts(
        evaluation_as_of_session=date(2026, 7, 7)
    )

    assert len(contexts) == 1
    context = contexts[0]
    assert context.candidate.candidate_score_id == str(candidate_id)
    assert context.snapshot_type == "manual"
    assert context.trade_classification.trade_classification_id == str(classification_id)
    assert context.watch_candidate is None
    assert context.primary_comparator_key == "SPY"
    assert context.peer_basket_id == str(basket_id)
    assert context.comparator_members == {
        f"peer:{basket_id}": ("GOOG", "MSFT"),
        "ranked:top2": ("MSFT", "NVDA"),
    }
    assert context.comparator_weights[f"peer:{basket_id}"] == {"GOOG": 0.4, "MSFT": 0.6}
    assert context.comparator_weights["ranked:top2"] == {"MSFT": 0.3, "NVDA": 0.7}
    assert context.sector_theme_symbols == ("XLK",)
    assert len(context.selected_orders) == 2
    assert len(context.selected_fills) == 2
    assert context.has_complete_close is True
    assert context.complete_close_at == close_at
    assert context.due_evaluation_statuses == ("final",)


def test_sqlalchemy_due_loader_pushes_date_bounds_and_missing_status_checks_into_sql():
    session = _Session()

    SqlAlchemyTradingRepository(session).load_due_candidate_outcome_contexts(
        evaluation_as_of_session=date(2026, 7, 7),
        source_decision_date=date(2026, 7, 2),
    )

    sql = " ".join(session.criteria)
    assert "candidate_scores.decision_time >=" in sql
    assert "candidate_scores.decision_time <" in sql
    assert sql.count("NOT (EXISTS") >= 2


def test_in_memory_due_context_preserves_phase_watch_and_production_checkpoint_identity():
    repository = InMemoryTradingRepository()
    decision_time = datetime(2026, 7, 2, 13, 30, tzinfo=timezone.utc)
    run = StrategyRunRecord(
        strategy_run_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "manual-run")),
        decision_time=decision_time,
        snapshot_type="manual",
        status="succeeded",
    )
    candidate = _candidate_record(run_id=run.strategy_run_id, decision_time=decision_time)
    watch = WatchCandidateRecord(
        watch_candidate_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "watch-context")),
        candidate=candidate,
        watch_strategy_id=candidate.strategy_id,
        watch_strategy_version=candidate.strategy_version,
        watch_type="ordinary_watch",
        result_status="watch",
        watch_reason="fixture",
        selection_context={},
    )
    repository.save_strategy_run(run)
    repository.save_candidate_scores((candidate,))
    repository.save_watch_candidates((watch,))
    interim = replace(
        _outcome(str(uuid.uuid5(uuid.NAMESPACE_URL, "in-memory-run"))),
        candidate_score_id=candidate.candidate_score_id,
        candidate_outcome_evaluation_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "in-memory-interim")),
        evaluation_status="interim",
        horizon_end_at=datetime(2026, 7, 6, 20, tzinfo=timezone.utc),
    )
    repository.save_candidate_outcome_evaluations((interim,))

    contexts = repository.load_due_candidate_outcome_contexts(
        evaluation_as_of_session=date(2026, 7, 7)
    )

    assert len(contexts) == 1
    assert contexts[0].snapshot_type == "manual"
    assert contexts[0].watch_candidate == watch
    assert contexts[0].trade_classification is None
    assert contexts[0].due_evaluation_statuses == ("final",)


def test_due_context_does_not_treat_same_calendar_date_as_exact_checkpoint():
    repository = InMemoryTradingRepository()
    decision_time = datetime(2026, 7, 2, 13, 30, tzinfo=timezone.utc)
    run = StrategyRunRecord(
        strategy_run_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "exact-checkpoint-run")),
        decision_time=decision_time,
        snapshot_type="manual",
        status="succeeded",
    )
    candidate = _candidate_record(run_id=run.strategy_run_id, decision_time=decision_time)
    repository.save_strategy_run(run)
    repository.save_candidate_scores((candidate,))
    repository.save_candidate_outcome_evaluations(
        (
            replace(
                _outcome(str(uuid.uuid5(uuid.NAMESPACE_URL, "exact-checkpoint-outcome-run"))),
                candidate_score_id=candidate.candidate_score_id,
                evaluation_status="interim",
                horizon_end_at=datetime(2026, 7, 6, 19, 59, tzinfo=timezone.utc),
            ),
        )
    )

    contexts = repository.load_due_candidate_outcome_contexts(
        evaluation_as_of_session=date(2026, 7, 7)
    )

    assert contexts[0].due_evaluation_statuses == ("interim", "final")


def test_option_premium_fill_cannot_establish_underlying_close_lineage():
    order_id = uuid.uuid5(uuid.NAMESPACE_URL, "option-premium-order")
    orders = (SimpleNamespace(paper_order_id=order_id, action="exit"),)
    fills = (
        SimpleNamespace(
            paper_order_id=order_id,
            paper_execution_id=uuid.uuid5(uuid.NAMESPACE_URL, "option-premium-fill"),
            quantity=Decimal("1"),
            executed_at=datetime(2026, 7, 6, 19, 45, tzinfo=timezone.utc),
        ),
    )

    assert complete_close_from_lineage(
        orders, fills, trade_identity="tactical_option_trade"
    ) == (False, None)


def test_maturation_insert_preserves_first_production_checkpoint_but_keeps_offline_null_ids():
    repository = InMemoryTradingRepository()
    first = _outcome(str(uuid.uuid5(uuid.NAMESPACE_URL, "production-run")))
    replacement = replace(
        first,
        candidate_outcome_evaluation_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "different-row-id")),
        alpha=0.25,
    )
    offline_one = replace(
        first,
        candidate_outcome_evaluation_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "offline-one")),
        candidate_score_id=None,
    )
    offline_two = replace(
        offline_one,
        candidate_outcome_evaluation_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "offline-two")),
    )

    repository.save_candidate_outcome_evaluations((first, replacement, offline_one, offline_two))

    production = [row for row in repository.candidate_outcome_evaluations if row.candidate_score_id is not None]
    offline = [row for row in repository.candidate_outcome_evaluations if row.candidate_score_id is None]
    assert len(production) == 1
    assert production[0].alpha == first.alpha
    assert len(offline) == 2


def _candidate_row(*, candidate_id, run_id, decision_time, benchmark_context):
    return SimpleNamespace(
        candidate_score_id=candidate_id,
        strategy_run_id=run_id,
        signal_snapshot_id=None,
        universe_ranking_run_id=None,
        universe_ranking_id=None,
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id=None,
        candidate_score=Decimal("0.8"),
        candidate_status="actionable",
        direction="bullish",
        action="enter_long",
        typical_horizon="intraday-2d",
        core_signal_evidence_json={},
        missing_required_signals_json=[],
        unsupported_missing_signal_families_json=[],
        invalidators_json=[],
        risk_tags_json=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="fixture",
        rejection_reason=None,
        benchmark_context_json=benchmark_context,
        decision_time=decision_time,
        available_for_decision_at=decision_time,
        source_record_refs_json=[],
    )


def _candidate_record(*, run_id: str, decision_time: datetime) -> CandidateScoreRecord:
    return CandidateScoreRecord(
        candidate_score_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "in-memory-candidate")),
        strategy_run_id=run_id,
        signal_snapshot_id="",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="",
        candidate_score=0.8,
        direction="bullish",
        action="enter_long",
        typical_horizon="intraday-2d",
        core_signal_evidence={},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=[],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="fixture",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=decision_time,
        available_for_decision_at=decision_time,
        source_record_refs_json=[],
    )
