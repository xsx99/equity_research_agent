"""Production maturity of already-persisted candidate scores."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from typing import Any, Iterable

from src.trading.outcomes.evaluator import evaluate_directional_outcome
from src.trading.outcomes.finalization import resolve_finalization
from src.trading.outcomes.horizons import OutcomeHorizonPolicy, UnsupportedOutcomeHorizon
from src.trading.outcomes.lineage import persisted_candidate_maturation_run_id
from src.trading.outcomes.prices import OutcomePriceRequest
from src.trading.phases.replay.historical import HistoricalReplayRunRecord
from src.trading.phases.replay.outcomes import CandidateOutcomeEvaluationRecord


@dataclass(frozen=True)
class PersistedCandidateOutcomeContext:
    """Original candidate and decision-time context loaded by the repository."""

    candidate: Any
    snapshot_type: str
    trade_classification: Any | None
    peer_basket_id: str | None
    sector_theme_symbols: tuple[str, ...]
    peer_symbols: tuple[str, ...]
    opportunity_symbols: tuple[str, ...]
    has_complete_close: bool
    complete_close_at: datetime | None


@dataclass(frozen=True)
class OutcomeEvaluationResult:
    created_interim_count: int
    created_final_count: int
    pending_count: int
    unsupported_horizon_count: int
    provider_error_count: int


class OutcomeEvaluationPipeline:
    """Measure persisted candidates without matching current strategy definitions."""

    def __init__(self, *, repository: Any, price_loader: Any, horizon_policy: OutcomeHorizonPolicy | None = None) -> None:
        self.repository = repository
        self.price_loader = price_loader
        self.horizon_policy = horizon_policy or OutcomeHorizonPolicy()

    def run(self, *, evaluation_as_of_session: date) -> OutcomeEvaluationResult:
        contexts = tuple(
            self.repository.load_due_candidate_outcome_contexts(
                evaluation_as_of_session=evaluation_as_of_session
            )
        )
        interim_count = final_count = pending_count = unsupported_horizon_count = provider_error_count = 0
        for context in contexts:
            candidate = context.candidate
            try:
                checkpoints = self.horizon_policy.checkpoints_for(
                    typical_horizon=candidate.typical_horizon,
                    decision_session=candidate.decision_time.date(),
                )
            except UnsupportedOutcomeHorizon:
                unsupported_horizon_count += 1
                continue
            price_result = self.price_loader.load(
                OutcomePriceRequest(
                    candidate_symbol=candidate.ticker,
                    snapshot_type=context.snapshot_type,
                    decision_time=candidate.decision_time,
                    horizon_end_at=_session_close_utc(checkpoints.final_session),
                    sector_theme_symbols=context.sector_theme_symbols,
                    peer_symbols=context.peer_symbols,
                    opportunity_symbols=context.opportunity_symbols,
                )
            )
            provider_error_count += len(price_result.provider_errors)
            run = self._run_record(
                candidate=candidate,
                snapshot_type=context.snapshot_type,
                evaluation_as_of_session=evaluation_as_of_session,
            )
            outcomes = []
            if checkpoints.interim_session <= evaluation_as_of_session:
                outcome = self._evaluate_checkpoint(
                    context=context,
                    price_result=price_result,
                    run_id=run.historical_replay_run_id,
                    evaluation_status="interim",
                    checkpoint_session=checkpoints.interim_session,
                )
                if outcome is None:
                    pending_count += 1
                else:
                    interim_count += 1
                    outcomes.append(outcome)
            if checkpoints.final_session <= evaluation_as_of_session:
                outcome = self._evaluate_checkpoint(
                    context=context,
                    price_result=price_result,
                    run_id=run.historical_replay_run_id,
                    evaluation_status="final",
                    checkpoint_session=checkpoints.final_session,
                )
                if outcome is None:
                    pending_count += 1
                else:
                    final_count += 1
                    outcomes.append(outcome)
            if outcomes:
                self.repository.save_historical_replay_run(run)
                self.repository.save_candidate_outcome_evaluations(tuple(outcomes))
        return OutcomeEvaluationResult(
            created_interim_count=interim_count,
            created_final_count=final_count,
            pending_count=pending_count,
            unsupported_horizon_count=unsupported_horizon_count,
            provider_error_count=provider_error_count,
        )

    def _run_record(self, *, candidate: Any, snapshot_type: str, evaluation_as_of_session: date) -> HistoricalReplayRunRecord:
        evaluation_at = _session_close_utc(evaluation_as_of_session)
        return HistoricalReplayRunRecord(
            historical_replay_run_id=persisted_candidate_maturation_run_id(
                source_decision_time=candidate.decision_time,
                snapshot_type=snapshot_type,
                evaluation_as_of_session=evaluation_at,
            ),
            decision_time=candidate.decision_time,
            snapshot_type=snapshot_type,
            status="succeeded",
            started_at=evaluation_at,
            completed_at=evaluation_at,
            decision_filter_json={"candidate_score_id": candidate.candidate_score_id},
            outcome_horizon_policy_json={"typical_horizon": candidate.typical_horizon},
            evaluation_as_of_session=evaluation_at,
            metadata_json={"mode": "persisted_candidate_maturation"},
        )

    def _evaluate_checkpoint(
        self,
        *,
        context: PersistedCandidateOutcomeContext,
        price_result: Any,
        run_id: str,
        evaluation_status: str,
        checkpoint_session: date,
    ) -> CandidateOutcomeEvaluationRecord | None:
        candidate = context.candidate
        finalization = resolve_finalization(
            trade_identity=_trade_identity(context.trade_classification),
            has_complete_close=context.has_complete_close,
            complete_close_at=context.complete_close_at,
            horizon_end_at=_session_close_utc(checkpoint_session),
        )
        effective_session = (
            finalization.horizon_end_at.date()
            if evaluation_status == "final" and finalization.reason == "trade_closed"
            else checkpoint_session
        )
        candidate_bars = _bars_through(price_result.bars_by_symbol.get(candidate.ticker.upper(), ()), effective_session)
        primary = str(candidate.benchmark_context.get("primary_benchmark") or "QQQ").upper()
        benchmark_bars = _bars_through(price_result.bars_by_symbol.get(primary, ()), effective_session)
        if len(candidate_bars) < 2 or len(benchmark_bars) < 2:
            return None
        start_price = candidate_bars[0].open
        end_price = candidate_bars[-1].close
        benchmark_start = benchmark_bars[0].open
        benchmark_end = benchmark_bars[-1].close
        if None in {start_price, end_price, benchmark_start, benchmark_end}:
            return None
        benchmark_return = (benchmark_end - benchmark_start) / benchmark_start
        active_returns = _active_returns(candidate_bars, benchmark_bars)
        metrics = evaluate_directional_outcome(
            direction=candidate.direction,
            candidate_start_price=start_price,
            candidate_end_price=end_price,
            path_high_prices=(bar.high for bar in candidate_bars if bar.high is not None),
            path_low_prices=(bar.low for bar in candidate_bars if bar.low is not None),
            primary_comparator_return=benchmark_return,
            aligned_active_returns=active_returns,
        )
        classification = context.trade_classification
        horizon_end_at = finalization.horizon_end_at if evaluation_status == "final" else _session_close_utc(checkpoint_session)
        return CandidateOutcomeEvaluationRecord(
            candidate_outcome_evaluation_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "|".join((candidate.candidate_score_id, evaluation_status, horizon_end_at.isoformat())))),
            historical_replay_run_id=run_id,
            candidate_score_id=candidate.candidate_score_id,
            trade_classification_id=getattr(classification, "trade_classification_id", None),
            ticker=candidate.ticker,
            strategy_id=candidate.strategy_id,
            strategy_version=candidate.strategy_version,
            expression_bucket_id=getattr(classification, "expression_bucket_id", "unclassified"),
            trade_identity=_trade_identity(classification),
            direction=candidate.direction,
            catalyst_type=None,
            confidence_bucket=f"{candidate.strategy_id}|{candidate.direction}",
            decision_time=candidate.decision_time,
            horizon_start_at=candidate.decision_time,
            horizon_end_at=horizon_end_at,
            evaluation_status=evaluation_status,
            candidate_return=metrics.candidate_return,
            benchmark_returns={primary: benchmark_return},
            peer_basket_id=context.peer_basket_id,
            peer_basket_return=None,
            alpha=metrics.alpha,
            max_favorable_excursion=metrics.max_favorable_excursion,
            max_adverse_excursion=metrics.max_adverse_excursion,
            regime=None,
            sector_theme=None,
            metadata_json={
                **metrics.metadata_json,
                **dict(price_result.metadata_json),
                "finalization_reason": finalization.reason,
                "primary_comparator_key": primary,
            },
        )


def _bars_through(bars: Iterable[Any], checkpoint: date) -> tuple[Any, ...]:
    return tuple(bar for bar in bars if bar.session_date <= checkpoint)


def _active_returns(candidate_bars: tuple[Any, ...], benchmark_bars: tuple[Any, ...]) -> tuple[float, ...]:
    by_date = {bar.session_date: bar for bar in benchmark_bars if bar.close is not None}
    values = []
    for candidate in candidate_bars:
        benchmark = by_date.get(candidate.session_date)
        if benchmark is None or candidate.close is None or candidate.open is None or benchmark.open is None:
            continue
        values.append((candidate.close - candidate.open) / candidate.open - (benchmark.close - benchmark.open) / benchmark.open)
    return tuple(values)


def _trade_identity(classification: Any | None) -> str:
    return str(getattr(classification, "trade_identity", "watch_only"))


def _session_close_utc(session: date) -> datetime:
    return datetime.combine(session, time(20, 0), tzinfo=timezone.utc)
