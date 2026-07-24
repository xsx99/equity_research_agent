"""Ranking lifecycle: load, score, persist the full cohort, then expose research tickers."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from math import ceil
from typing import Any, Iterable

from src.trading.ranking.config import RankingConfig
from src.trading.ranking.loader import RankingInputBatch, RankingInputLoader
from src.trading.ranking.metrics import build_raw_metrics
from src.trading.ranking.peers import resolve_cohorts
from src.trading.ranking.records import (
    AssetSnapshot,
    PeerBasketMembership,
    RankingResult,
    TickerRelationship,
    UniverseRankingRecord,
    UniverseRankingRunRecord,
)
from src.trading.ranking.scoring import rank_universe


@dataclass(frozen=True)
class RankingPipelineResult:
    """Persisted run outputs made available to pre-open orchestration."""

    run: UniverseRankingRunRecord
    rankings: tuple[UniverseRankingRecord, ...]
    result: RankingResult
    inputs: RankingInputBatch


class UniverseRankingPipeline:
    """Orchestrates I/O around the pure cross-sectional ranking domain."""

    def __init__(self, *, loader: RankingInputLoader, repository: Any, config: RankingConfig) -> None:
        self.loader = loader
        self.repository = repository
        self.config = config

    def run(
        self,
        *,
        universe_snapshot_id: str,
        decision_time: datetime,
        assets: Iterable[AssetSnapshot],
        peer_baskets: Iterable[PeerBasketMembership] = (),
        relationships: Iterable[TickerRelationship] = (),
        manual_requests: Iterable[str] = (),
        watchlist_pins: Iterable[str] = (),
        open_positions: Iterable[str] = (),
        manual_includes: Iterable[str] = (),
        manual_excludes: Iterable[str] = (),
    ) -> RankingPipelineResult:
        asset_rows = tuple(assets)
        inputs = self.loader.load(
            (asset.ticker for asset in asset_rows),
            decision_time=decision_time,
        )
        metrics = {
            ticker: build_raw_metrics(
                ticker=ticker,
                bars=inputs.bars_by_ticker.get(ticker, ()),
                spy_bars=inputs.benchmark_bars,
                decision_time=decision_time,
            )
            for ticker in inputs.requested_tickers
        }
        resolutions = resolve_cohorts(
            metrics,
            asset_rows,
            peer_baskets,
            relationships,
            decision_time,
            self.config,
        )
        ranking_result = rank_universe(
            metrics,
            asset_rows,
            resolutions=resolutions,
            manual_requests=manual_requests,
            watchlist_pins=watchlist_pins,
            open_positions=open_positions,
            manual_includes=manual_includes,
            manual_excludes=manual_excludes,
            config=self.config,
        )
        ranked_count = sum(row.status == "ranked" for row in ranking_result.full_cohort)
        status = _run_status(
            input_count=len(inputs.requested_tickers),
            ranked_count=ranked_count,
            benchmark_available=bool(inputs.benchmark_bars),
            partial_errors=bool(inputs.chunk_errors),
        )
        run = UniverseRankingRunRecord(
            universe_ranking_run_id=str(uuid.uuid4()),
            universe_snapshot_id=universe_snapshot_id,
            decision_time=decision_time,
            model_version=self.config.model_version,
            config_json=self.config.to_dict(),
            input_count=len(inputs.requested_tickers),
            eligible_count=sum(metric.is_fully_eligible for metric in metrics.values()),
            shortlist_count=len(ranking_result.automatic_tickers),
            status=status,
            source_metadata_json={
                "cutoff_session": inputs.cutoff_session.session_date.isoformat(),
                "cutoff_scheduled_close": inputs.cutoff_session.scheduled_close.isoformat(),
                "chunk_errors": dict(inputs.chunk_errors),
            },
            error_metadata_json=(
                {"benchmark": "unavailable"} if not inputs.benchmark_bars else dict(inputs.chunk_errors)
            ),
            started_at=decision_time,
            completed_at=decision_time,
        )
        ranking_rows = tuple(
            _ranking_record(
                run_id=run.universe_ranking_run_id,
                row=row,
                raw_metrics=metrics[row.ticker],
                automatic_tickers=set(ranking_result.automatic_tickers),
                decision_time=decision_time,
            )
            for row in ranking_result.full_cohort
        )
        self.repository.save_universe_ranking_run(run, ranking_rows)
        return RankingPipelineResult(run, ranking_rows, ranking_result, inputs)


def _run_status(*, input_count: int, ranked_count: int, benchmark_available: bool, partial_errors: bool) -> str:
    if not benchmark_available or ranked_count < max(10, ceil(0.20 * input_count)):
        return "failed"
    if partial_errors or ranked_count < ceil(0.90 * input_count):
        return "degraded"
    return "succeeded"


def _ranking_record(
    *,
    run_id: str,
    row: Any,
    raw_metrics: Any,
    automatic_tickers: set[str],
    decision_time: datetime,
) -> UniverseRankingRecord:
    selected_peer = row.cohort_resolution.peer
    available_at = raw_metrics.max_available_for_decision_at or decision_time
    return UniverseRankingRecord(
        universe_ranking_id=str(uuid.uuid4()),
        universe_ranking_run_id=run_id,
        ticker=row.ticker,
        decision_time=decision_time,
        status=row.status,
        overall_rank=row.overall_rank,
        overall_percentile=row.overall_percentile,
        relative_strength_score=row.score,
        data_confidence=row.confidence,
        peer_group_type=selected_peer.cohort_type,
        peer_group_id=selected_peer.cohort_id,
        peer_group_size=selected_peer.size,
        is_automatic_shortlist=row.ticker in automatic_tickers,
        forced_inclusion_reasons=row.forced_reasons,
        raw_metrics_json=_json_metrics(raw_metrics),
        normalized_metrics_json=dict(row.normalized_metrics),
        positive_contributors_json=tuple(asdict(item) for item in row.positive_contributors),
        negative_contributors_json=tuple(asdict(item) for item in row.negative_contributors),
        missing_inputs=row.missing_inputs,
        source_refs=raw_metrics.source_refs,
        available_for_decision_at=available_at,
    )


def _json_metrics(metrics: Any) -> dict[str, Any]:
    payload = asdict(metrics)
    for field_name in ("last_bar_date", "max_available_for_decision_at"):
        value = payload.get(field_name)
        if value is not None:
            payload[field_name] = value.isoformat()
    return payload
