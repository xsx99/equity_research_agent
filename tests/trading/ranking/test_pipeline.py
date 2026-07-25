from datetime import date, datetime, timedelta, timezone

import pytest

from src.trading.ranking.calendar import RankingSession
from src.trading.ranking.config import RankingConfig
from src.trading.ranking.loader import RankingInputBatch
from src.trading.ranking.pipeline import UniverseRankingPipeline
from src.trading.ranking.records import AdjustedDailyBar, AssetSnapshot
from src.trading.repositories.in_memory import InMemoryTradingRepository


class _Loader:
    def __init__(self, batch: RankingInputBatch) -> None:
        self.batch = batch

    def load(self, tickers, *, decision_time):
        return self.batch


def _bars(ticker: str) -> tuple[AdjustedDailyBar, ...]:
    start = date(2026, 4, 17)
    available_at = datetime(2026, 7, 20, 20, tzinfo=timezone.utc)
    return tuple(
        AdjustedDailyBar(
            session_date=start + timedelta(days=index),
            close=100.0 + index,
            volume=1_000_000 + index,
            available_for_decision_at=available_at,
            adjustment_source="fixture",
            source_refs=(f"fixture:{ticker}:{index}",),
        )
        for index in range(65)
    )


def _batch(*, include_benchmark: bool = True, errors: dict[str, str] | None = None) -> RankingInputBatch:
    tickers = tuple(f"T{index:02d}" for index in range(10))
    bars = {ticker: _bars(ticker) for ticker in tickers}
    return RankingInputBatch(
        requested_tickers=tickers,
        bars_by_ticker=bars,
        benchmark_bars=_bars("SPY") if include_benchmark else (),
        cutoff_session=RankingSession(date(2026, 7, 20), datetime(2026, 7, 20, 20, tzinfo=timezone.utc)),
        chunk_errors=errors or {},
    )


def test_pipeline_persists_full_cohort_before_returning_result():
    repository = InMemoryTradingRepository()
    decision_time = datetime(2026, 7, 21, 13, 30, tzinfo=timezone.utc)
    pipeline = UniverseRankingPipeline(loader=_Loader(_batch()), repository=repository, config=RankingConfig(min_cohort_size=1))

    result = pipeline.run(
        universe_snapshot_id="snapshot-id",
        decision_time=decision_time,
        assets=tuple(AssetSnapshot(ticker, 1_000_000.0, freshness_session_lag=0) for ticker in _batch().requested_tickers),
    )

    assert result.run.status == "succeeded"
    assert len(result.rankings) == 10
    assert repository.load_universe_ranking_run(result.run.universe_ranking_run_id) == result.run
    assert repository.load_universe_rankings(result.run.universe_ranking_run_id) == result.rankings


def test_pipeline_persists_insufficient_rows_and_failed_status_when_benchmark_is_missing():
    repository = InMemoryTradingRepository()
    decision_time = datetime(2026, 7, 21, 13, 30, tzinfo=timezone.utc)
    pipeline = UniverseRankingPipeline(loader=_Loader(_batch(include_benchmark=False)), repository=repository, config=RankingConfig(min_cohort_size=1))

    result = pipeline.run(
        universe_snapshot_id="snapshot-id",
        decision_time=decision_time,
        assets=tuple(AssetSnapshot(ticker, 1_000_000.0, freshness_session_lag=0) for ticker in _batch().requested_tickers),
    )

    assert result.run.status == "failed"
    assert {row.status for row in result.rankings} == {"insufficient_data"}


def test_pipeline_marks_partial_input_as_degraded_and_does_not_return_after_persistence_failure():
    decision_time = datetime(2026, 7, 21, 13, 30, tzinfo=timezone.utc)
    assets = tuple(AssetSnapshot(ticker, 1_000_000.0, freshness_session_lag=0) for ticker in _batch().requested_tickers)
    degraded = UniverseRankingPipeline(
        loader=_Loader(_batch(errors={"T00,T01": "timeout"})),
        repository=InMemoryTradingRepository(),
        config=RankingConfig(min_cohort_size=1),
    )
    assert degraded.run(universe_snapshot_id="snapshot-id", decision_time=decision_time, assets=assets).run.status == "degraded"

    class _FailingRepository:
        def save_universe_ranking_run(self, run, rankings):
            raise RuntimeError("persistence unavailable")

    failing = UniverseRankingPipeline(
        loader=_Loader(_batch()),
        repository=_FailingRepository(),
        config=RankingConfig(min_cohort_size=1),
    )
    with pytest.raises(RuntimeError, match="persistence unavailable"):
        failing.run(universe_snapshot_id="snapshot-id", decision_time=decision_time, assets=assets)
