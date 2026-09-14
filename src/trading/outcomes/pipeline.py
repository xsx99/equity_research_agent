"""Production maturity of already-persisted candidate scores."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable

from src.trading.outcomes.evaluator import evaluate_directional_outcome
from src.trading.outcomes.context import PersistedCandidateOutcomeContext
from src.trading.outcomes.finalization import resolve_finalization
from src.trading.outcomes.horizons import OutcomeHorizonPolicy, UnsupportedOutcomeHorizon
from src.trading.outcomes.lineage import persisted_candidate_maturation_run_id
from src.trading.outcomes.prices import OutcomePriceRequest
from src.trading.phases.replay.historical import HistoricalReplayRunRecord
from src.trading.phases.replay.outcomes import CandidateOutcomeEvaluationRecord


@dataclass(frozen=True)
class OutcomeEvaluationResult:
    created_interim_count: int
    created_final_count: int
    pending_count: int
    unsupported_horizon_count: int
    provider_error_count: int
    due_candidate_count: int = 0
    due_checkpoint_count: int = 0
    already_evaluated_count: int = 0
    reason_codes: tuple[str, ...] = ()
    missing_symbols: tuple[str, ...] = ()
    provider_errors: dict[str, str] | None = None
    comparator_coverage: dict[str, tuple[str, ...]] | None = None


class OutcomeEvaluationPipeline:
    """Measure persisted candidates without matching current strategy definitions."""

    def __init__(self, *, repository: Any, price_loader: Any, horizon_policy: OutcomeHorizonPolicy | None = None) -> None:
        self.repository = repository
        self.price_loader = price_loader
        self.horizon_policy = horizon_policy or OutcomeHorizonPolicy()

    def run(
        self,
        *,
        evaluation_as_of_session: date,
        source_decision_date: date | None = None,
        persist: bool = True,
    ) -> OutcomeEvaluationResult:
        load_kwargs: dict[str, Any] = {"evaluation_as_of_session": evaluation_as_of_session}
        if source_decision_date is not None:
            load_kwargs["source_decision_date"] = source_decision_date
        contexts = tuple(
            self.repository.load_due_candidate_outcome_contexts(**load_kwargs)
        )
        interim_count = final_count = pending_count = unsupported_horizon_count = provider_error_count = 0
        missing_symbols: set[str] = set()
        provider_errors: dict[str, str] = {}
        available_comparators: set[str] = set()
        missing_comparators: set[str] = set()
        due_checkpoint_count = sum(
            len(tuple(status for status in (context.due_evaluation_statuses or ()) if status != "unsupported_horizon"))
            if context.due_evaluation_statuses is not None
            else 0
            for context in contexts
        )
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
            due_statuses = context.due_evaluation_statuses
            if due_statuses is None:
                due_statuses = tuple(
                    status
                    for status, checkpoint in (
                        ("interim", checkpoints.interim_session),
                        ("final", checkpoints.final_session),
                    )
                    if checkpoint <= evaluation_as_of_session
                )
                due_checkpoint_count += len(due_statuses)
            price_result = self.price_loader.load(
                OutcomePriceRequest(
                    candidate_symbol=candidate.ticker,
                    snapshot_type=context.snapshot_type,
                    decision_time=candidate.decision_time,
                    horizon_end_at=self.horizon_policy.session_close(checkpoints.final_session),
                    sector_theme_symbols=context.sector_theme_symbols,
                    peer_symbols=context.peer_symbols,
                    opportunity_symbols=context.opportunity_symbols,
                    actual_close_at=(context.complete_close_at if context.has_complete_close else None),
                    primary_comparator_symbol=context.primary_comparator_key,
                )
            )
            provider_error_count += len(price_result.provider_errors)
            missing_symbols.update(price_result.missing_symbols)
            provider_errors.update(
                {f"{candidate.candidate_score_id}:{key}": value for key, value in price_result.provider_errors.items()}
            )
            run = self._run_record(
                candidate=candidate,
                snapshot_type=context.snapshot_type,
                evaluation_as_of_session=evaluation_as_of_session,
            )
            outcomes = []
            if "interim" in due_statuses:
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
                    available_comparators.update(outcome.metadata_json["comparator_coverage"]["available"])
                    missing_comparators.update(outcome.metadata_json["comparator_coverage"]["missing"])
            if "final" in due_statuses:
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
                    available_comparators.update(outcome.metadata_json["comparator_coverage"]["available"])
                    missing_comparators.update(outcome.metadata_json["comparator_coverage"]["missing"])
            if outcomes and persist:
                self.repository.save_historical_replay_run(run)
                self.repository.save_candidate_outcome_evaluations(tuple(outcomes))
        reason_codes = []
        if pending_count:
            reason_codes.append("missing_required_price")
        if provider_error_count:
            reason_codes.append("provider_error")
        if missing_comparators:
            reason_codes.append("missing_optional_comparator")
        if unsupported_horizon_count:
            reason_codes.append("unsupported_horizon")
        return OutcomeEvaluationResult(
            created_interim_count=interim_count,
            created_final_count=final_count,
            pending_count=pending_count,
            unsupported_horizon_count=unsupported_horizon_count,
            provider_error_count=provider_error_count,
            due_candidate_count=len(contexts),
            due_checkpoint_count=due_checkpoint_count,
            already_evaluated_count=0,
            reason_codes=tuple(reason_codes),
            missing_symbols=tuple(sorted(missing_symbols)),
            provider_errors=provider_errors,
            comparator_coverage={
                "available": tuple(sorted(available_comparators)),
                "missing": tuple(sorted(missing_comparators)),
            },
        )

    def _run_record(self, *, candidate: Any, snapshot_type: str, evaluation_as_of_session: date) -> HistoricalReplayRunRecord:
        evaluation_at = self.horizon_policy.session_close(evaluation_as_of_session)
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
            horizon_end_at=self.horizon_policy.session_close(checkpoint_session),
        )
        effective_session = (
            finalization.horizon_end_at.date()
            if evaluation_status == "final" and finalization.reason == "trade_closed"
            else checkpoint_session
        )
        candidate_bars = _bars_through(price_result.bars_by_symbol.get(candidate.ticker.upper(), ()), effective_session)
        if not candidate_bars:
            return None
        start_price = _start_price(
            context.snapshot_type,
            candidate.ticker.upper(),
            candidate_bars,
            price_result,
        )
        use_actual_close = evaluation_status == "final" and finalization.reason == "trade_closed"
        endpoint_bar = _bar_on_session(candidate_bars, effective_session)
        end_price = price_result.actual_close_prices_by_symbol.get(candidate.ticker.upper()) if use_actual_close else (
            endpoint_bar.close if endpoint_bar is not None else None
        )
        if None in {start_price, end_price}:
            return None
        simple_returns = _simple_comparator_returns(
            context=context,
            price_result=price_result,
            effective_session=effective_session,
            use_actual_close=use_actual_close,
        )
        primary_candidates = (
            (context.primary_comparator_key,)
            if context.primary_comparator_explicit
            else tuple(dict.fromkeys((context.primary_comparator_key, "QQQ", "SPY")))
        )
        primary = next((key for key in primary_candidates if key in simple_returns), None)
        if primary is None:
            return None
        benchmark_return = simple_returns[primary]
        benchmark_bars = _bars_through(price_result.bars_by_symbol.get(primary, ()), effective_session)
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
        horizon_end_at = (
            finalization.horizon_end_at
            if evaluation_status == "final"
            else self.horizon_policy.session_close(checkpoint_session)
        )
        composite_returns, missing_composites = _composite_comparator_returns(
            context=context,
            price_result=price_result,
            effective_session=effective_session,
            use_actual_close=use_actual_close,
        )
        all_returns = {**simple_returns, **composite_returns}
        comparator_alphas = {
            key: _directional_alpha(candidate.direction, metrics.metadata_json["underlying_return"], value)
            for key, value in all_returns.items()
            if metrics.directional_edge_eligible
        }
        peer_key = f"peer:{context.peer_basket_id}" if context.peer_basket_id else None
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
            benchmark_returns={
                key: value for key, value in all_returns.items() if key != peer_key
            },
            peer_basket_id=context.peer_basket_id,
            peer_basket_return=all_returns.get(peer_key) if peer_key else None,
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
                "comparator_alphas": comparator_alphas,
                "missing_comparator_keys": sorted(missing_composites),
                "comparator_coverage": {
                    "available": sorted(all_returns),
                    "missing": sorted(missing_composites),
                },
                "price_end_boundary": (
                    "actual_close_minute" if use_actual_close else "session_close"
                ),
            },
        )


def _bars_through(bars: Iterable[Any], checkpoint: date) -> tuple[Any, ...]:
    return tuple(bar for bar in bars if bar.session_date <= checkpoint)


def _bar_on_session(bars: Iterable[Any], session: date) -> Any | None:
    return next((bar for bar in bars if bar.session_date == session), None)


def _active_returns(candidate_bars: tuple[Any, ...], benchmark_bars: tuple[Any, ...]) -> tuple[float, ...]:
    by_date = {bar.session_date: bar for bar in benchmark_bars if bar.close is not None}
    values = []
    for candidate in candidate_bars:
        benchmark = by_date.get(candidate.session_date)
        if benchmark is None or candidate.close is None or candidate.open is None or benchmark.open is None:
            continue
        values.append((candidate.close - candidate.open) / candidate.open - (benchmark.close - benchmark.open) / benchmark.open)
    return tuple(values)


def _simple_comparator_returns(*, context: PersistedCandidateOutcomeContext, price_result: Any, effective_session: date, use_actual_close: bool) -> dict[str, float]:
    keys = {context.primary_comparator_key, "QQQ", "SPY", *context.sector_theme_symbols}
    returns: dict[str, float] = {}
    for key in sorted(keys):
        bars = _bars_through(price_result.bars_by_symbol.get(key, ()), effective_session)
        if not bars:
            continue
        start = _start_price(context.snapshot_type, key, bars, price_result)
        endpoint_bar = _bar_on_session(bars, effective_session)
        end = price_result.actual_close_prices_by_symbol.get(key) if use_actual_close else (
            endpoint_bar.close if endpoint_bar is not None else None
        )
        if start is None or end is None or start == 0:
            continue
        returns[key] = (end - start) / start
    return returns


def _composite_comparator_returns(*, context: PersistedCandidateOutcomeContext, price_result: Any, effective_session: date, use_actual_close: bool) -> tuple[dict[str, float], tuple[str, ...]]:
    available: dict[str, float] = {}
    missing: list[str] = []
    for key, members in sorted(context.comparator_members.items()):
        member_returns: dict[str, float] = {}
        for symbol in members:
            bars = _bars_through(price_result.bars_by_symbol.get(symbol, ()), effective_session)
            if not bars:
                break
            start = _start_price(context.snapshot_type, symbol, bars, price_result)
            endpoint_bar = _bar_on_session(bars, effective_session)
            end = price_result.actual_close_prices_by_symbol.get(symbol) if use_actual_close else (
                endpoint_bar.close if endpoint_bar is not None else None
            )
            if start is None or end is None or start == 0:
                break
            member_returns[symbol] = (end - start) / start
        if len(member_returns) != len(members):
            missing.append(key)
            continue
        persisted_weights = context.comparator_weights.get(key, {})
        if persisted_weights and set(persisted_weights) != set(members):
            missing.append(key)
            continue
        weights = persisted_weights or {symbol: 1.0 / len(members) for symbol in members}
        available[key] = sum(member_returns[symbol] * weights[symbol] for symbol in members)
    return available, tuple(missing)


def _directional_alpha(direction: str, candidate_return: float, comparator_return: float) -> float:
    if direction in {"bearish", "short", "risk_off"}:
        return comparator_return - candidate_return
    return candidate_return - comparator_return


def _start_price(
    snapshot_type: str,
    symbol: str,
    bars: tuple[Any, ...],
    price_result: Any,
) -> float | None:
    if snapshot_type == "pre_open":
        decision_session = price_result.start_boundary.date()
        decision_bar = _bar_on_session(bars, decision_session)
        return decision_bar.open if decision_bar is not None else None
    return price_result.start_prices_by_symbol.get(symbol)


def _trade_identity(classification: Any | None) -> str:
    return str(getattr(classification, "trade_identity", "watch_only"))
