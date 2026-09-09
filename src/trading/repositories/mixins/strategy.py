from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, and_, cast, exists, or_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from src.core import config as app_config
from src.db.models.trading import (
    CandidateOutcomeEvaluation,
    CandidateScore,
    DailyReflection,
    HistoricalReplayRun,
    LearningFactor,
    StrategyDefinition,
    StrategyEvaluationResult,
    StrategyProposal,
    StrategyRun,
    TradeClassification,
    TradingDecision,
    WatchCandidate,
    PaperOrder,
    PaperExecution,
    PeerBasket,
)
from src.trading.outcomes.context import (
    PersistedCandidateOutcomeContext,
    comparator_context,
    complete_close_from_lineage,
    due_evaluation_statuses,
)
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import (
    CandidateScoreRecord,
    StrategyDefinitionRecord,
    StrategyRunRecord,
)
from src.trading.strategies.selector import WatchCandidateRecord
from src.trading.phases.replay.historical import HistoricalReplayRunRecord
from src.trading.phases.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.repositories._base_common import _to_uuid, _to_uuid_or_none
from src.trading.repositories._base_payloads import _rejected_candidate_payload
from src.trading.repositories._base_records import (
    _candidate_outcome_record,
    _daily_reflection_record,
    _learning_factor_record,
)
from src.trading.trade_day import local_day_bounds_utc


def _trade_day_window(trade_date: date) -> tuple[object, object]:
    return local_day_bounds_utc(trade_date, app_config.SCHEDULER_TIMEZONE)


LONG_HORIZON_LOOKBACK_DAYS = 60


class StrategyRepositoryMixin:
    def save_historical_replay_run(self, run: HistoricalReplayRunRecord) -> None:
        _require_choice(run.snapshot_type, {"pre_open", "manual", "intraday"}, "snapshot_type")
        _require_choice(run.status, {"running", "succeeded", "failed"}, "historical_replay_run_status")
        row = self.session.query(HistoricalReplayRun).filter_by(
            historical_replay_run_id=_to_uuid(run.historical_replay_run_id)
        ).one_or_none()
        if row is None:
            row = HistoricalReplayRun(historical_replay_run_id=_to_uuid(run.historical_replay_run_id))
            self.session.add(row)
        row.decision_time = run.decision_time
        row.snapshot_type = run.snapshot_type
        row.evaluation_as_of_session = run.evaluation_as_of_session
        row.status = run.status
        row.started_at = run.started_at
        row.completed_at = run.completed_at
        row.decision_filter_json = dict(run.decision_filter_json)
        row.outcome_horizon_policy_json = dict(run.outcome_horizon_policy_json)
        row.metadata_json = dict(run.metadata_json)
        self.session.flush()

    def save_candidate_outcome_evaluations(
        self,
        outcomes: list[CandidateOutcomeEvaluationRecord] | tuple[CandidateOutcomeEvaluationRecord, ...],
    ) -> None:
        for outcome in outcomes:
            _require_choice(
                outcome.trade_identity,
                {"core_holding", "tactical_stock_trade", "tactical_option_trade", "risk_hedge_overlay", "watch_only"},
                "trade_identity",
            )
            _require_choice(outcome.evaluation_status, {"interim", "final"}, "evaluation_status")
            values = _candidate_outcome_values(outcome)
            bind = self.session.get_bind() if hasattr(self.session, "get_bind") else None
            if outcome.candidate_score_id is not None and getattr(getattr(bind, "dialect", None), "name", None) == "postgresql":
                statement = (
                    postgresql_insert(CandidateOutcomeEvaluation)
                    .values(**values)
                    .on_conflict_do_nothing(
                        constraint="uq_candidate_outcomes_maturation_checkpoint"
                    )
                )
                self.session.execute(statement)
                continue
            if outcome.candidate_score_id is None:
                row = self.session.query(CandidateOutcomeEvaluation).filter_by(
                    candidate_outcome_evaluation_id=_to_uuid(outcome.candidate_outcome_evaluation_id)
                ).one_or_none()
            else:
                row = self.session.query(CandidateOutcomeEvaluation).filter_by(
                    candidate_score_id=_to_uuid(outcome.candidate_score_id),
                    evaluation_status=outcome.evaluation_status,
                    horizon_end_at=outcome.horizon_end_at,
                ).one_or_none()
            if row is None:
                row = CandidateOutcomeEvaluation(
                    candidate_outcome_evaluation_id=_to_uuid(outcome.candidate_outcome_evaluation_id)
                )
                self.session.add(row)
            elif outcome.candidate_score_id is not None:
                continue
            row.historical_replay_run_id = _to_uuid_or_none(outcome.historical_replay_run_id)
            row.candidate_score_id = _to_uuid_or_none(outcome.candidate_score_id)
            row.trade_classification_id = _to_uuid_or_none(outcome.trade_classification_id)
            row.ticker = outcome.ticker
            row.strategy_id = outcome.strategy_id
            row.strategy_version = outcome.strategy_version
            row.expression_bucket_id = outcome.expression_bucket_id
            row.trade_identity = outcome.trade_identity
            row.direction = outcome.direction
            row.catalyst_type = outcome.catalyst_type
            row.confidence_bucket = outcome.confidence_bucket
            row.decision_time = outcome.decision_time
            row.horizon_start_at = outcome.horizon_start_at
            row.horizon_end_at = outcome.horizon_end_at
            row.evaluation_status = outcome.evaluation_status
            row.candidate_return = _decimal_or_none(outcome.candidate_return)
            row.benchmark_returns_json = dict(outcome.benchmark_returns)
            row.peer_basket_id = _to_uuid_or_none(outcome.peer_basket_id)
            row.peer_basket_return = _decimal_or_none(outcome.peer_basket_return)
            row.alpha = _decimal_or_none(outcome.alpha)
            row.max_favorable_excursion = _decimal_or_none(outcome.max_favorable_excursion)
            row.max_adverse_excursion = _decimal_or_none(outcome.max_adverse_excursion)
            row.regime = outcome.regime
            row.sector_theme = outcome.sector_theme
            row.metadata_json = dict(outcome.metadata_json)
        self.session.flush()

    def load_due_candidate_outcome_contexts(
        self,
        *,
        evaluation_as_of_session: date,
        source_decision_date: date | None = None,
    ) -> tuple[PersistedCandidateOutcomeContext, ...]:
        """Load persisted candidates whose interim or final checkpoint is due."""
        upper_date = (source_decision_date or evaluation_as_of_session) + timedelta(days=1)
        next_day = datetime.combine(
            upper_date,
            time.min,
            tzinfo=timezone.utc,
        )
        if source_decision_date is not None:
            first_day = datetime.combine(source_decision_date, time.min, tzinfo=timezone.utc)
        else:
            first_day = None
        missing_interim = ~exists().where(
            and_(
                CandidateOutcomeEvaluation.candidate_score_id == CandidateScore.candidate_score_id,
                CandidateOutcomeEvaluation.evaluation_status == "interim",
            )
        )
        missing_final = ~exists().where(
            and_(
                CandidateOutcomeEvaluation.candidate_score_id == CandidateScore.candidate_score_id,
                CandidateOutcomeEvaluation.evaluation_status == "final",
            )
        )
        candidate_query = self.session.query(CandidateScore).filter(
            CandidateScore.decision_time < next_day,
            or_(missing_interim, missing_final),
        )
        if first_day is not None:
            candidate_query = candidate_query.filter(CandidateScore.decision_time >= first_day)
        candidate_rows = candidate_query.all()
        if not candidate_rows:
            return ()

        candidate_ids = {row.candidate_score_id for row in candidate_rows}
        run_ids = {row.strategy_run_id for row in candidate_rows}
        runs = {
            row.strategy_run_id: row
            for row in self.session.query(StrategyRun)
            .filter(StrategyRun.strategy_run_id.in_(run_ids))
            .all()
        }
        classification_rows = self.session.query(TradeClassification).filter(
            TradeClassification.candidate_score_id.in_(candidate_ids)
        ).all()
        watch_rows = self.session.query(WatchCandidate).filter(
            WatchCandidate.candidate_score_id.in_(candidate_ids)
        ).all()
        outcome_rows = self.session.query(CandidateOutcomeEvaluation).filter(
            CandidateOutcomeEvaluation.candidate_score_id.in_(candidate_ids)
        ).all()
        decisions = self.session.query(TradingDecision).filter(
            TradingDecision.candidate_score_id.in_(candidate_ids)
        ).all()
        decision_ids = {row.trading_decision_id for row in decisions}
        orders = (
            self.session.query(PaperOrder)
            .filter(PaperOrder.trading_decision_id.in_(decision_ids))
            .all()
            if decision_ids
            else []
        )
        order_ids = {row.paper_order_id for row in orders}
        fills = (
            self.session.query(PaperExecution)
            .filter(PaperExecution.paper_order_id.in_(order_ids))
            .all()
            if order_ids
            else []
        )

        peer_ids = {
            _to_uuid(value)
            for row in candidate_rows
            if (value := dict(row.benchmark_context_json or {}).get("peer_basket_id"))
        }
        peer_baskets = {
            str(row.peer_basket_id): row
            for row in (
                self.session.query(PeerBasket)
                .filter(PeerBasket.peer_basket_id.in_(peer_ids))
                .all()
                if peer_ids
                else []
            )
        }

        contexts: list[PersistedCandidateOutcomeContext] = []
        for row in sorted(candidate_rows, key=lambda item: (item.decision_time, str(item.candidate_score_id))):
            run = runs.get(row.strategy_run_id)
            if run is None:
                continue
            candidate = _candidate_score_record(row)
            classification_row = next(
                (item for item in classification_rows if item.candidate_score_id == row.candidate_score_id),
                None,
            )
            classification = _trade_classification_record(classification_row) if classification_row else None
            watch_row = next(
                (item for item in watch_rows if item.candidate_score_id == row.candidate_score_id),
                None,
            )
            watch = _watch_candidate_record(watch_row, candidate) if watch_row else None
            candidate_decision_ids = {
                item.trading_decision_id
                for item in decisions
                if item.candidate_score_id == row.candidate_score_id
            }
            candidate_orders = tuple(
                item for item in orders if item.trading_decision_id in candidate_decision_ids
            )
            candidate_order_ids = {item.paper_order_id for item in candidate_orders}
            candidate_fills = tuple(
                item for item in fills if item.paper_order_id in candidate_order_ids
            )
            has_complete_close, complete_close_at = complete_close_from_lineage(
                candidate_orders,
                candidate_fills,
                trade_identity=getattr(classification, "trade_identity", None),
            )
            benchmark_context = dict(row.benchmark_context_json or {})
            persisted_peer_id = str(benchmark_context.get("peer_basket_id") or "") or None
            peer_row = peer_baskets.get(persisted_peer_id or "")
            comparator = comparator_context(
                benchmark_context,
                peer_basket_id=persisted_peer_id,
                peer_members=tuple(getattr(peer_row, "members_json", ()) or ()),
            )
            context = PersistedCandidateOutcomeContext(
                candidate=candidate,
                snapshot_type=str(run.snapshot_type),
                trade_classification=classification,
                watch_candidate=watch,
                selected_orders=candidate_orders,
                selected_fills=candidate_fills,
                has_complete_close=has_complete_close,
                complete_close_at=complete_close_at,
                **comparator,
            )
            due = due_evaluation_statuses(
                context,
                evaluation_as_of_session=evaluation_as_of_session,
                existing_outcomes=outcome_rows,
            )
            if due:
                contexts.append(
                    PersistedCandidateOutcomeContext(
                        **{
                            **context.__dict__,
                            "due_evaluation_statuses": due,
                        }
                    )
                )
        return tuple(contexts)

    def load_due_candidate_outcome_source_dates(
        self,
        evaluation_as_of_session: date,
    ) -> tuple[date, ...]:
        """Return bounded source dates that still lack an outcome checkpoint."""
        start_at = datetime.combine(
            evaluation_as_of_session - timedelta(days=270),
            time.min,
            tzinfo=timezone.utc,
        )
        end_at = datetime.combine(
            evaluation_as_of_session + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )
        missing_interim = ~exists().where(
            and_(
                CandidateOutcomeEvaluation.candidate_score_id
                == CandidateScore.candidate_score_id,
                CandidateOutcomeEvaluation.evaluation_status == "interim",
            )
        )
        missing_final = ~exists().where(
            and_(
                CandidateOutcomeEvaluation.candidate_score_id
                == CandidateScore.candidate_score_id,
                CandidateOutcomeEvaluation.evaluation_status == "final",
            )
        )
        rows = (
            self.session.query(cast(CandidateScore.decision_time, Date))
            .filter(
                CandidateScore.decision_time >= start_at,
                CandidateScore.decision_time < end_at,
                or_(missing_interim, missing_final),
            )
            .distinct()
            .order_by(cast(CandidateScore.decision_time, Date))
            .all()
        )
        return tuple(row[0] for row in rows if row[0] is not None)

    def save_strategy_definition(self, definition: StrategyDefinitionRecord) -> None:
        row = self.session.query(StrategyDefinition).filter_by(
            strategy_definition_id=_to_uuid(definition.strategy_definition_id)
        ).one_or_none()
        if row is None:
            row = StrategyDefinition(
                strategy_definition_id=_to_uuid(definition.strategy_definition_id),
                strategy_id=definition.strategy_id,
                version=definition.version,
            )
            self.session.add(row)
        row.display_name = definition.display_name
        row.strategy_layer = definition.strategy_layer
        row.typical_horizon = definition.typical_horizon
        row.allowed_common_stock_direction = "long_only"
        row.config_json = dict(definition.config_json)
        row.lifecycle_status = definition.lifecycle_status
        row.source = definition.source
        row.is_active = definition.is_active
        self.session.flush()
    def load_strategy_definitions(self) -> list[StrategyDefinitionRecord]:
        rows = self.session.query(StrategyDefinition).all()
        return [
            StrategyDefinitionRecord(
                strategy_definition_id=str(row.strategy_definition_id),
                strategy_id=row.strategy_id,
                version=row.version,
                display_name=row.display_name,
                strategy_layer=row.strategy_layer,
                typical_horizon=row.typical_horizon,
                config_json=dict(row.config_json or {}),
                lifecycle_status=row.lifecycle_status,
                is_active=bool(row.is_active),
                source=row.source,
            )
            for row in rows
        ]
    def load_active_strategy_definitions(self) -> list[StrategyDefinitionRecord]:
        return [
            row
            for row in self.load_strategy_definitions()
            if row.is_active and row.lifecycle_status in {"active", "experimental", "shadow"}
        ]
    def save_strategy_proposal(self, proposal: Any) -> None:
        row = StrategyProposal(
            strategy_proposal_id=_to_uuid(proposal.strategy_proposal_id),
            trade_date=proposal.trade_date,
            prompt_run_id=None,
            daily_reflection_id=_to_uuid_or_none(proposal.source_daily_reflection_id),
            proposal_status=proposal.proposal_status,
            proposed_strategy_id=proposal.proposed_strategy_id,
            display_name=proposal.display_name,
            proposed_lifecycle_status=proposal.proposed_lifecycle_status,
            duplicate_of_strategy_id=proposal.duplicate_of_strategy_id,
            rejection_reason=proposal.rejection_reason,
            source="reflection_learning",
            evidence_summary=proposal.evidence_summary,
            proposal_json=dict(proposal.proposal_json),
            metadata_json=dict(proposal.metadata_json),
        )
        self.session.add(row)
        self.session.flush()
    def save_strategy_run(self, run: StrategyRunRecord) -> None:
        row = self.session.query(StrategyRun).filter_by(strategy_run_id=_to_uuid(run.strategy_run_id)).one_or_none()
        if row is None:
            row = StrategyRun(strategy_run_id=_to_uuid(run.strategy_run_id))
            self.session.add(row)
        row.decision_time = run.decision_time
        row.snapshot_type = run.snapshot_type
        row.status = run.status
        row.metadata_json = dict(run.metadata_json)
        self.session.flush()
    def save_strategy_evaluation_result(self, result: Any) -> None:
        row = StrategyEvaluationResult(
            strategy_evaluation_result_id=_to_uuid(result.strategy_evaluation_result_id),
            strategy_definition_id=_to_uuid_or_none(result.strategy_definition_id),
            strategy_proposal_id=_to_uuid_or_none(result.strategy_proposal_id),
            strategy_id=result.strategy_id,
            evaluation_type=result.evaluation_type,
            evaluation_status=result.evaluation_status,
            prior_lifecycle_status=result.prior_lifecycle_status,
            new_lifecycle_status=result.new_lifecycle_status,
            reason_code=result.reason_code,
            evidence_summary=result.evidence_summary,
            metrics_json=dict(result.metrics_json),
            created_at=result.created_at,
        )
        self.session.add(row)
        self.session.flush()
    def load_strategy_evolution_inputs(self, *, trade_date: date) -> dict[str, object]:
        start_date = trade_date - timedelta(days=LONG_HORIZON_LOOKBACK_DAYS)
        start_utc, _ = _trade_day_window(start_date)
        _, end_utc = _trade_day_window(trade_date)
        daily_reflection_rows = sorted(
            self.session.query(DailyReflection)
            .filter(
                DailyReflection.trade_date >= start_date,
                DailyReflection.trade_date <= trade_date,
            )
            .all(),
            key=lambda row: (row.trade_date, row.created_at),
            reverse=True,
        )
        return {
            "daily_reflections": tuple(_daily_reflection_record(row) for row in daily_reflection_rows),
            "learning_factors": tuple(
                _learning_factor_record(row)
                for row in sorted(
                    self.session.query(LearningFactor)
                    .filter(
                        LearningFactor.trade_date >= start_date,
                        LearningFactor.trade_date <= trade_date,
                    )
                    .all(),
                    key=lambda item: item.trade_date,
                    reverse=True,
                )
            ),
            "rejected_candidates": tuple(
                _rejected_candidate_payload(row)
                for row in sorted(
                    self.session.query(CandidateScore)
                    .filter(
                        CandidateScore.decision_time >= start_utc,
                        CandidateScore.decision_time < end_utc,
                    )
                    .all(),
                    key=lambda item: item.decision_time,
                    reverse=True,
                )
                if row.rejection_reason
            ),
            "candidate_outcome_evaluations": tuple(
                _candidate_outcome_record(row)
                for row in sorted(
                    self.session.query(CandidateOutcomeEvaluation)
                    .filter(
                        CandidateOutcomeEvaluation.decision_time >= start_utc,
                        CandidateOutcomeEvaluation.decision_time < end_utc,
                    )
                    .all(),
                    key=lambda item: item.decision_time,
                    reverse=True,
                )
            ),
        }
    def save_candidate_scores(self, candidates: list[CandidateScoreRecord] | tuple[CandidateScoreRecord, ...]) -> None:
        for candidate in candidates:
            row = self.session.query(CandidateScore).filter_by(
                candidate_score_id=_to_uuid(candidate.candidate_score_id)
            ).one_or_none()
            if row is None:
                row = CandidateScore(candidate_score_id=_to_uuid(candidate.candidate_score_id))
                self.session.add(row)
            row.strategy_run_id = _to_uuid(candidate.strategy_run_id)
            row.signal_snapshot_id = _to_uuid_or_none(candidate.signal_snapshot_id)
            row.universe_ranking_run_id = _to_uuid_or_none(
                getattr(candidate, "universe_ranking_run_id", None)
            )
            row.universe_ranking_id = _to_uuid_or_none(
                getattr(candidate, "universe_ranking_id", None)
            )
            row.ticker = candidate.ticker
            row.strategy_id = candidate.strategy_id
            row.strategy_version = candidate.strategy_version
            row.strategy_definition_id = _to_uuid_or_none(candidate.strategy_definition_id)
            row.candidate_score = Decimal(str(candidate.candidate_score))
            row.candidate_status = candidate.candidate_status
            row.direction = candidate.direction
            row.action = candidate.action
            row.typical_horizon = candidate.typical_horizon
            row.core_signal_evidence_json = dict(candidate.core_signal_evidence)
            row.missing_required_signals_json = list(candidate.missing_required_signals)
            row.unsupported_missing_signal_families_json = list(candidate.unsupported_missing_signal_families)
            row.invalidators_json = list(candidate.invalidators)
            row.risk_tags_json = list(candidate.risk_tags)
            row.macro_compatibility = candidate.macro_compatibility
            row.selection_source = candidate.selection_source
            row.manual_request_id = _to_uuid_or_none(candidate.manual_request_id)
            row.selection_reason = candidate.selection_reason
            row.rejection_reason = candidate.rejection_reason
            row.benchmark_context_json = dict(candidate.benchmark_context)
            row.decision_time = candidate.decision_time
            row.available_for_decision_at = candidate.available_for_decision_at
            row.source_record_refs_json = list(candidate.source_record_refs_json)
        self.session.flush()
    def save_watch_candidates(
        self,
        watch_candidates: list[WatchCandidateRecord] | tuple[WatchCandidateRecord, ...],
    ) -> None:
        for watch in watch_candidates:
            row = self.session.query(WatchCandidate).filter_by(
                watch_candidate_id=_to_uuid(watch.watch_candidate_id)
            ).one_or_none()
            if row is None:
                row = WatchCandidate(
                    watch_candidate_id=_to_uuid(watch.watch_candidate_id)
                )
                self.session.add(row)
            row.candidate_score_id = _to_uuid(watch.candidate.candidate_score_id)
            row.strategy_run_id = _to_uuid(watch.candidate.strategy_run_id)
            row.ticker = watch.candidate.ticker
            row.watch_strategy_id = watch.watch_strategy_id
            row.watch_strategy_version = watch.watch_strategy_version
            row.watch_type = watch.watch_type
            row.result_status = watch.result_status
            row.watch_reason = watch.watch_reason
            row.selection_context_json = dict(watch.selection_context)
            row.decision_time = watch.candidate.decision_time
        self.session.flush()
    def save_trade_classifications(
        self,
        classifications: list[TradeClassificationRecord] | tuple[TradeClassificationRecord, ...],
    ) -> None:
        for classification in classifications:
            row = self.session.query(TradeClassification).filter_by(
                trade_classification_id=_to_uuid(classification.trade_classification_id)
            ).one_or_none()
            if row is None:
                row = TradeClassification(
                    trade_classification_id=_to_uuid(classification.trade_classification_id)
                )
                self.session.add(row)
            row.candidate_score_id = _to_uuid(classification.candidate_score_id)
            row.strategy_run_id = _to_uuid(classification.strategy_run_id)
            row.ticker = classification.ticker
            row.selected_strategy_id = classification.selected_strategy_id
            row.selected_strategy_version = classification.selected_strategy_version
            row.expression_bucket_id = classification.expression_bucket_id
            row.expression_bucket_version = classification.expression_bucket_version
            row.trade_identity = classification.trade_identity
            row.watch_type = classification.watch_type
            row.direction = classification.direction
            row.intended_horizon = classification.intended_horizon
            row.exit_policy = classification.exit_policy
            row.result_status = classification.result_status
            row.classification_reason = classification.classification_reason
            row.selected_strategy_context_json = dict(classification.selected_strategy_context_json)
            row.decision_time = classification.decision_time
        self.session.flush()
    def load_trade_classification(self, trade_classification_id: str | None) -> TradeClassificationRecord | None:
        if trade_classification_id is None:
            return None
        row = self.session.query(TradeClassification).filter_by(
            trade_classification_id=_to_uuid(trade_classification_id)
        ).one_or_none()
        if row is None:
            return None
        return TradeClassificationRecord(
            trade_classification_id=str(row.trade_classification_id),
            candidate_score_id=str(row.candidate_score_id),
            strategy_run_id=str(row.strategy_run_id),
            ticker=row.ticker,
            selected_strategy_id=row.selected_strategy_id,
            selected_strategy_version=row.selected_strategy_version,
            expression_bucket_id=row.expression_bucket_id,
            expression_bucket_version=row.expression_bucket_version,
            trade_identity=row.trade_identity,
            watch_type=row.watch_type,
            direction=row.direction,
            intended_horizon=row.intended_horizon,
            exit_policy=row.exit_policy,
            result_status=row.result_status,
            classification_reason=row.classification_reason,
            selected_strategy_context_json=dict(row.selected_strategy_context_json or {}),
            decision_time=row.decision_time,
        )


def _decimal_or_none(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _candidate_outcome_values(outcome: CandidateOutcomeEvaluationRecord) -> dict[str, Any]:
    return {
        "candidate_outcome_evaluation_id": _to_uuid(outcome.candidate_outcome_evaluation_id),
        "historical_replay_run_id": _to_uuid_or_none(outcome.historical_replay_run_id),
        "candidate_score_id": _to_uuid_or_none(outcome.candidate_score_id),
        "trade_classification_id": _to_uuid_or_none(outcome.trade_classification_id),
        "ticker": outcome.ticker,
        "strategy_id": outcome.strategy_id,
        "strategy_version": outcome.strategy_version,
        "expression_bucket_id": outcome.expression_bucket_id,
        "trade_identity": outcome.trade_identity,
        "direction": outcome.direction,
        "catalyst_type": outcome.catalyst_type,
        "confidence_bucket": outcome.confidence_bucket,
        "decision_time": outcome.decision_time,
        "horizon_start_at": outcome.horizon_start_at,
        "horizon_end_at": outcome.horizon_end_at,
        "evaluation_status": outcome.evaluation_status,
        "candidate_return": _decimal_or_none(outcome.candidate_return),
        "benchmark_returns_json": dict(outcome.benchmark_returns),
        "peer_basket_id": _to_uuid_or_none(outcome.peer_basket_id),
        "peer_basket_return": _decimal_or_none(outcome.peer_basket_return),
        "alpha": _decimal_or_none(outcome.alpha),
        "max_favorable_excursion": _decimal_or_none(outcome.max_favorable_excursion),
        "max_adverse_excursion": _decimal_or_none(outcome.max_adverse_excursion),
        "regime": outcome.regime,
        "sector_theme": outcome.sector_theme,
        "metadata_json": dict(outcome.metadata_json),
    }


def _candidate_score_record(row: Any) -> CandidateScoreRecord:
    return CandidateScoreRecord(
        candidate_score_id=str(row.candidate_score_id),
        strategy_run_id=str(row.strategy_run_id),
        signal_snapshot_id=str(row.signal_snapshot_id) if row.signal_snapshot_id else "",
        universe_ranking_run_id=(
            str(row.universe_ranking_run_id) if getattr(row, "universe_ranking_run_id", None) else None
        ),
        universe_ranking_id=(
            str(row.universe_ranking_id) if getattr(row, "universe_ranking_id", None) else None
        ),
        ticker=row.ticker,
        strategy_id=row.strategy_id,
        strategy_version=row.strategy_version,
        strategy_definition_id=str(row.strategy_definition_id) if row.strategy_definition_id else "",
        candidate_score=float(row.candidate_score),
        candidate_status=row.candidate_status,
        direction=row.direction,
        action=row.action,
        typical_horizon=row.typical_horizon,
        core_signal_evidence=dict(row.core_signal_evidence_json or {}),
        missing_required_signals=list(row.missing_required_signals_json or ()),
        unsupported_missing_signal_families=list(row.unsupported_missing_signal_families_json or ()),
        invalidators=list(row.invalidators_json or ()),
        risk_tags=list(row.risk_tags_json or ()),
        macro_compatibility=row.macro_compatibility,
        selection_source=row.selection_source,
        manual_request_id=str(row.manual_request_id) if row.manual_request_id else None,
        selection_reason=row.selection_reason,
        rejection_reason=row.rejection_reason,
        benchmark_context=dict(row.benchmark_context_json or {}),
        decision_time=row.decision_time,
        available_for_decision_at=row.available_for_decision_at,
        source_record_refs_json=list(row.source_record_refs_json or ()),
    )


def _trade_classification_record(row: Any) -> TradeClassificationRecord:
    return TradeClassificationRecord(
        trade_classification_id=str(row.trade_classification_id),
        candidate_score_id=str(row.candidate_score_id),
        strategy_run_id=str(row.strategy_run_id),
        ticker=row.ticker,
        selected_strategy_id=row.selected_strategy_id,
        selected_strategy_version=row.selected_strategy_version,
        expression_bucket_id=row.expression_bucket_id,
        expression_bucket_version=row.expression_bucket_version,
        trade_identity=row.trade_identity,
        watch_type=row.watch_type,
        direction=row.direction,
        intended_horizon=row.intended_horizon,
        exit_policy=row.exit_policy,
        result_status=row.result_status,
        classification_reason=row.classification_reason,
        selected_strategy_context_json=dict(row.selected_strategy_context_json or {}),
        decision_time=row.decision_time,
    )


def _watch_candidate_record(row: Any, candidate: CandidateScoreRecord) -> WatchCandidateRecord:
    return WatchCandidateRecord(
        watch_candidate_id=str(row.watch_candidate_id),
        candidate=candidate,
        watch_strategy_id=row.watch_strategy_id,
        watch_strategy_version=row.watch_strategy_version,
        watch_type=row.watch_type,
        result_status=row.result_status,
        watch_reason=row.watch_reason,
        selection_context=dict(row.selection_context_json or {}),
    )


def _require_choice(value: str, allowed: set[str], name: str) -> None:
    if value not in allowed:
        raise ValueError(f"unsupported_{name}:{value}")
