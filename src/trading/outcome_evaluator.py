"""Historical candidate outcome evaluation for PR03 replay."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from src.trading.strategy_matching import CandidateScoreRecord
from src.trading.trade_classifier import TradeClassificationRecord


@dataclass(frozen=True)
class PricePoint:
    """Point-in-time close/mark used for deterministic outcome measurement."""

    timestamp: datetime
    price: float


@dataclass(frozen=True)
class CandidateOutcomeEvaluationRecord:
    """Persistable deterministic outcome row for candidates/trades/watch items."""

    candidate_outcome_evaluation_id: str
    historical_replay_run_id: str | None
    candidate_score_id: str | None
    trade_classification_id: str | None
    ticker: str
    strategy_id: str
    strategy_version: str
    expression_bucket_id: str
    trade_identity: str
    direction: str
    catalyst_type: str | None
    confidence_bucket: str
    decision_time: datetime
    horizon_start_at: datetime
    horizon_end_at: datetime
    evaluation_status: str
    candidate_return: float | None
    benchmark_returns: dict[str, float]
    peer_basket_id: str | None
    peer_basket_return: float | None
    alpha: float | None
    max_favorable_excursion: float | None
    max_adverse_excursion: float | None
    regime: str | None
    sector_theme: str | None
    metadata_json: dict[str, Any] = field(default_factory=dict)


class OutcomeEvaluator:
    """Measure candidates against future market data without changing reconstruction."""

    def __init__(self, price_points: dict[str, Iterable[PricePoint]]) -> None:
        self.price_points = {
            ticker.upper(): sorted(points, key=lambda point: point.timestamp)
            for ticker, points in price_points.items()
        }

    def evaluate(
        self,
        candidate: CandidateScoreRecord,
        classification: TradeClassificationRecord | None,
        *,
        horizon_start_at: datetime,
        horizon_end_at: datetime,
        benchmark_symbols: Iterable[str] = ("QQQ", "SPY"),
        historical_replay_run_id: str | None = None,
        peer_basket_id: str | None = None,
        peer_basket_return: float | None = None,
        evaluation_status: str = "final",
    ) -> CandidateOutcomeEvaluationRecord:
        candidate_return, mfe, mae = self._returns_for_symbol(
            candidate.ticker,
            horizon_start_at,
            horizon_end_at,
        )
        benchmark_returns = {
            symbol.upper(): value
            for symbol in benchmark_symbols
            if (value := self._simple_return(symbol, horizon_start_at, horizon_end_at)) is not None
        }
        primary_benchmark = candidate.benchmark_context.get("primary_benchmark")
        benchmark_for_alpha = (
            benchmark_returns.get(str(primary_benchmark).upper())
            if primary_benchmark
            else next(iter(benchmark_returns.values()), None)
        )
        alpha = (
            candidate_return - benchmark_for_alpha
            if candidate_return is not None and benchmark_for_alpha is not None
            else None
        )
        expression_bucket_id = classification.expression_bucket_id if classification else "unclassified"
        trade_identity = classification.trade_identity if classification else "watch_only"
        confidence_bucket = _confidence_bucket(candidate, classification)
        return CandidateOutcomeEvaluationRecord(
            candidate_outcome_evaluation_id=str(uuid.uuid4()),
            historical_replay_run_id=historical_replay_run_id,
            candidate_score_id=candidate.candidate_score_id,
            trade_classification_id=classification.trade_classification_id if classification else None,
            ticker=candidate.ticker,
            strategy_id=candidate.strategy_id,
            strategy_version=candidate.strategy_version,
            expression_bucket_id=expression_bucket_id,
            trade_identity=trade_identity,
            direction=candidate.direction,
            catalyst_type=_catalyst_type(candidate),
            confidence_bucket=confidence_bucket,
            decision_time=candidate.decision_time,
            horizon_start_at=horizon_start_at,
            horizon_end_at=horizon_end_at,
            evaluation_status=evaluation_status,
            candidate_return=candidate_return,
            benchmark_returns=benchmark_returns,
            peer_basket_id=peer_basket_id,
            peer_basket_return=peer_basket_return,
            alpha=alpha,
            max_favorable_excursion=mfe,
            max_adverse_excursion=mae,
            regime=None,
            sector_theme=None,
            metadata_json={
                "selection_source": candidate.selection_source,
                "manual_request_id": candidate.manual_request_id,
                "rejection_reason": candidate.rejection_reason,
            },
        )

    def _returns_for_symbol(
        self,
        symbol: str,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[float | None, float | None, float | None]:
        points = _points_in_window(self.price_points.get(symbol.upper(), []), start_at, end_at)
        if len(points) < 2:
            return None, None, None
        start_price = points[0].price
        if start_price == 0:
            return None, None, None
        returns = [(point.price - start_price) / start_price for point in points]
        return returns[-1], max(returns), min(returns)

    def _simple_return(self, symbol: str, start_at: datetime, end_at: datetime) -> float | None:
        value, _mfe, _mae = self._returns_for_symbol(symbol, start_at, end_at)
        return value


def _points_in_window(points: list[PricePoint], start_at: datetime, end_at: datetime) -> list[PricePoint]:
    return [point for point in points if start_at <= point.timestamp <= end_at]


def _catalyst_type(candidate: CandidateScoreRecord) -> str | None:
    for key in (
        "events_news.catalyst_type",
        "events_news.own_earnings_event_type",
        "events_news.direct_negative_catalyst_type",
    ):
        if candidate.core_signal_evidence.get(key):
            return str(candidate.core_signal_evidence[key])
    return None


def _confidence_bucket(
    candidate: CandidateScoreRecord,
    classification: TradeClassificationRecord | None,
) -> str:
    expression_bucket_id = classification.expression_bucket_id if classification else "unclassified"
    trade_identity = classification.trade_identity if classification else "watch_only"
    return "|".join(
        (
            candidate.strategy_id,
            expression_bucket_id,
            trade_identity,
            candidate.direction,
            _catalyst_type(candidate) or "none",
        )
    )
