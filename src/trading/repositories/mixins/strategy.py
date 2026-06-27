from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from src.db.models.trading import (
    CandidateOutcomeEvaluation,
    CandidateScore,
    DailyReflection,
    LearningFactor,
    StrategyDefinition,
    StrategyEvaluationResult,
    StrategyProposal,
    StrategyRun,
    TradeClassification,
    WatchCandidate,
)
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import (
    CandidateScoreRecord,
    StrategyDefinitionRecord,
    StrategyRunRecord,
)
from src.trading.strategies.selector import WatchCandidateRecord
from src.trading.repositories._base_common import _to_uuid, _to_uuid_or_none
from src.trading.repositories._base_payloads import _rejected_candidate_payload
from src.trading.repositories._base_records import (
    _candidate_outcome_record,
    _daily_reflection_record,
    _learning_factor_record,
)


class StrategyRepositoryMixin:
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
        latest_reflection = max(
            (row for row in self.session.query(DailyReflection).all() if row.trade_date == trade_date),
            key=lambda row: row.created_at,
            default=None,
        )
        daily_reflections = (
            (_daily_reflection_record(latest_reflection),)
            if latest_reflection is not None
            else ()
        )
        return {
            "daily_reflections": daily_reflections,
            "learning_factors": tuple(
                _learning_factor_record(row)
                for row in self.session.query(LearningFactor).all()
                if row.trade_date == trade_date
            ),
            "rejected_candidates": tuple(
                _rejected_candidate_payload(row)
                for row in self.session.query(CandidateScore).all()
                if row.decision_time.date() == trade_date and row.rejection_reason
            ),
            "candidate_outcome_evaluations": tuple(
                _candidate_outcome_record(row)
                for row in self.session.query(CandidateOutcomeEvaluation).all()
                if row.decision_time.date() == trade_date
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
