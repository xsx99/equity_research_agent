from dataclasses import replace
from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.trading.outcomes.pipeline import OutcomeEvaluationPipeline, PersistedCandidateOutcomeContext
from src.trading.outcomes.prices import OutcomePriceBar, OutcomePriceLoadResult


class _Repository:
    def __init__(self, contexts):
        self.contexts = contexts
        self.runs = []
        self.outcomes = []

    def load_due_candidate_outcome_contexts(self, *, evaluation_as_of_session):
        assert evaluation_as_of_session == date(2026, 7, 7)
        return self.contexts

    def save_historical_replay_run(self, run):
        self.runs.append(run)

    def save_candidate_outcome_evaluations(self, outcomes):
        self.outcomes.extend(outcomes)


class _PriceLoader:
    def load(self, request):
        return OutcomePriceLoadResult(
            requested_symbols=("AAPL", "QQQ", "SPY"),
            bars_by_symbol={
                "AAPL": (
                    OutcomePriceBar(date(2026, 7, 2), 100, 104, 99, 102),
                    OutcomePriceBar(date(2026, 7, 6), 103, 106, 102, 105),
                    OutcomePriceBar(date(2026, 7, 7), 103, 110, 102, 108),
                ),
                "QQQ": (
                    OutcomePriceBar(date(2026, 7, 2), 500, 503, 498, 500),
                    OutcomePriceBar(date(2026, 7, 6), 505, 506, 504, 505),
                    OutcomePriceBar(date(2026, 7, 7), 510, 511, 509, 510),
                ),
                "SPY": (
                    OutcomePriceBar(date(2026, 7, 2), 600, 601, 599, 600),
                    OutcomePriceBar(date(2026, 7, 6), 603, 604, 602, 603),
                    OutcomePriceBar(date(2026, 7, 7), 606, 607, 605, 606),
                ),
            },
            missing_symbols=(),
            provider_errors={},
            start_boundary=datetime(2026, 7, 2, 13, 30, tzinfo=timezone.utc),
            end_boundary=datetime(2026, 7, 7, 20, tzinfo=timezone.utc),
            metadata_json={"provider": "fixture", "resolution": "1Day"},
            actual_close_prices_by_symbol={"AAPL": 104, "QQQ": 502, "SPY": 601},
        )


def test_pipeline_matures_persisted_candidate_without_reconstructing_strategy_cohort():
    decision_time = datetime(2026, 7, 2, 13, 0, tzinfo=timezone.utc)
    candidate = SimpleNamespace(
        candidate_score_id="candidate-1",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        direction="bullish",
        decision_time=decision_time,
        typical_horizon="intraday-2d",
        benchmark_context={"primary_benchmark": "QQQ"},
        selection_source="scanner",
        manual_request_id=None,
        rejection_reason=None,
        core_signal_evidence={},
    )
    context = PersistedCandidateOutcomeContext(
        candidate=candidate,
        snapshot_type="pre_open",
        trade_classification=None,
        peer_basket_id=None,
        sector_theme_symbols=(),
        peer_symbols=(),
        opportunity_symbols=(),
        has_complete_close=False,
        complete_close_at=None,
    )
    repository = _Repository((context,))
    pipeline = OutcomeEvaluationPipeline(repository=repository, price_loader=_PriceLoader())

    result = pipeline.run(evaluation_as_of_session=date(2026, 7, 7))

    assert result.created_final_count == 1
    assert result.created_interim_count == 1
    assert len(repository.runs) == 1
    assert repository.runs[0].metadata_json["mode"] == "persisted_candidate_maturation"
    assert len(repository.outcomes) == 2
    final = next(row for row in repository.outcomes if row.evaluation_status == "final")
    assert final.candidate_score_id == "candidate-1"
    assert final.alpha == 0.06
    assert final.metadata_json["finalization_reason"] == "horizon_expired"


def test_pipeline_uses_complete_close_session_as_final_price_boundary():
    decision_time = datetime(2026, 7, 2, 13, 0, tzinfo=timezone.utc)
    candidate = SimpleNamespace(
        candidate_score_id="candidate-closed",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        direction="bullish",
        decision_time=decision_time,
        typical_horizon="intraday-2d",
        benchmark_context={"primary_benchmark": "QQQ"},
        selection_source="scanner",
        manual_request_id=None,
        rejection_reason=None,
        core_signal_evidence={},
    )
    context = PersistedCandidateOutcomeContext(
        candidate=candidate,
        snapshot_type="pre_open",
        trade_classification=SimpleNamespace(
            trade_classification_id="classification-closed",
            expression_bucket_id="long_stock",
            trade_identity="tactical_stock_trade",
        ),
        peer_basket_id=None,
        sector_theme_symbols=(),
        peer_symbols=(),
        opportunity_symbols=(),
        has_complete_close=True,
        complete_close_at=datetime(2026, 7, 6, 19, 45, tzinfo=timezone.utc),
    )
    repository = _Repository((context,))

    OutcomeEvaluationPipeline(repository=repository, price_loader=_PriceLoader()).run(
        evaluation_as_of_session=date(2026, 7, 7)
    )

    final = next(row for row in repository.outcomes if row.evaluation_status == "final")
    assert final.horizon_end_at == datetime(2026, 7, 6, 19, 45, tzinfo=timezone.utc)
    assert final.candidate_return == 0.04
    assert final.metadata_json["price_end_boundary"] == "actual_close_minute"


def test_pipeline_persists_all_available_comparators_without_reweighting_missing_members():
    decision_time = datetime(2026, 7, 2, 13, 0, tzinfo=timezone.utc)
    candidate = SimpleNamespace(
        candidate_score_id="candidate-comparators",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        direction="bullish",
        decision_time=decision_time,
        typical_horizon="intraday-2d",
        benchmark_context={"primary_benchmark": "IWM"},
    )
    context = PersistedCandidateOutcomeContext(
        candidate=candidate,
        snapshot_type="pre_open",
        trade_classification=None,
        peer_basket_id="basket-1",
        sector_theme_symbols=("XLK",),
        peer_symbols=("MSFT", "GOOG"),
        opportunity_symbols=("NVDA", "MISSING"),
        has_complete_close=False,
        complete_close_at=None,
        primary_comparator_key="IWM",
        comparator_members={
            "peer:basket-1": ("MSFT", "GOOG"),
            "ranked:top2": ("NVDA", "MISSING"),
        },
        comparator_weights={
            "peer:basket-1": {"MSFT": 0.75, "GOOG": 0.25},
            "ranked:top2": {"NVDA": 0.5, "MISSING": 0.5},
        },
    )
    repository = _Repository((context,))
    price_loader = _PriceLoader()
    base = price_loader.load(None)
    base.bars_by_symbol.update(
        {
            "XLK": (
                OutcomePriceBar(date(2026, 7, 2), 200, 200, 200, 200),
                OutcomePriceBar(date(2026, 7, 7), 204, 204, 204, 204),
            ),
            "MSFT": (
                OutcomePriceBar(date(2026, 7, 2), 100, 100, 100, 100),
                OutcomePriceBar(date(2026, 7, 7), 110, 110, 110, 110),
            ),
            "GOOG": (
                OutcomePriceBar(date(2026, 7, 2), 100, 100, 100, 100),
                OutcomePriceBar(date(2026, 7, 7), 120, 120, 120, 120),
            ),
            "NVDA": (
                OutcomePriceBar(date(2026, 7, 2), 100, 100, 100, 100),
                OutcomePriceBar(date(2026, 7, 7), 130, 130, 130, 130),
            ),
        }
    )
    price_loader.load = lambda request: base

    OutcomeEvaluationPipeline(repository=repository, price_loader=price_loader).run(
        evaluation_as_of_session=date(2026, 7, 7)
    )

    final = next(row for row in repository.outcomes if row.evaluation_status == "final")
    assert final.metadata_json["primary_comparator_key"] == "QQQ"
    assert set(final.benchmark_returns) == {"QQQ", "SPY", "XLK"}
    assert final.peer_basket_return == 0.125
    assert "ranked:top2" not in final.benchmark_returns
    assert final.metadata_json["missing_comparator_keys"] == ["ranked:top2"]
    assert set(final.metadata_json["comparator_alphas"]) == {
        "QQQ", "SPY", "XLK", "peer:basket-1"
    }


def test_intraday_candidate_without_minute_start_price_stays_pending():
    decision_time = datetime(2026, 7, 2, 15, 0, 30, tzinfo=timezone.utc)
    candidate = SimpleNamespace(
        candidate_score_id="candidate-intraday-missing-start",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        direction="bullish",
        decision_time=decision_time,
        typical_horizon="intraday-2d",
        benchmark_context={"primary_benchmark": "QQQ"},
    )
    context = PersistedCandidateOutcomeContext(
        candidate=candidate,
        snapshot_type="intraday",
        trade_classification=None,
        peer_basket_id=None,
        sector_theme_symbols=(),
        peer_symbols=(),
        opportunity_symbols=(),
        has_complete_close=False,
        complete_close_at=None,
        due_evaluation_statuses=("final",),
    )
    repository = _Repository((context,))
    price_loader = _PriceLoader()
    result_payload = replace(price_loader.load(None), start_prices_by_symbol={})
    price_loader.load = lambda request: result_payload

    result = OutcomeEvaluationPipeline(
        repository=repository,
        price_loader=price_loader,
    ).run(evaluation_as_of_session=date(2026, 7, 7))

    assert result.pending_count == 1
    assert repository.outcomes == []
