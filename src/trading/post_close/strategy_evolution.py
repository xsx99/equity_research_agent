"""PR10 strategy evolution pipeline and lifecycle gating."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, Iterable

from src.agents.strategy_evolution import StrategyEvolutionAgent
from src.agents.trading import PromptRunRecord, UsageEventRecord
from src.trading.post_close.reflection import DailyReflectionRecord, LearningFactorRecord
from src.trading.post_close.strategy_policy import experimental_strategy_weight_cap
from src.trading.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.strategies.matching import StrategyDefinitionRecord


COMPUTABLE_REQUIRED_SIGNALS = {
    "opening_gap_pct",
    "vwap_reclaim",
    "relative_volume",
    "opening_range_reclaim",
    "fresh_catalyst_type",
    "sector_rank_percentile",
    "vwap_hold",
    "opening_range_high_break",
}


@dataclass(frozen=True)
class StrategyEvolutionRequest:
    """Structured PR10 input assembled after reflection."""

    trade_date: date
    decision_time: datetime
    available_for_decision_at: datetime
    daily_reflections: tuple[DailyReflectionRecord, ...] = ()
    learning_factors: tuple[LearningFactorRecord, ...] = ()
    rejected_candidates: tuple[dict[str, Any], ...] = ()
    candidate_outcome_evaluations: tuple[CandidateOutcomeEvaluationRecord, ...] = ()


@dataclass(frozen=True)
class StrategyProposalRecord:
    """Persistable strategy proposal artifact."""

    strategy_proposal_id: str
    trade_date: date
    prompt_template: Any
    prompt_run: PromptRunRecord
    usage_events: list[UsageEventRecord]
    proposal_status: str
    proposed_strategy_id: str
    display_name: str
    proposed_lifecycle_status: str | None
    duplicate_of_strategy_id: str | None
    rejection_reason: str | None
    evidence_summary: str
    proposal_json: dict[str, Any]
    metadata_json: dict[str, Any]


@dataclass(frozen=True)
class StrategyEvaluationResultRecord:
    """Persisted lifecycle evidence and transition audit row."""

    strategy_evaluation_result_id: str
    strategy_id: str
    strategy_definition_id: str | None
    strategy_proposal_id: str | None
    evaluation_type: str
    evaluation_status: str
    prior_lifecycle_status: str | None
    new_lifecycle_status: str | None
    reason_code: str
    evidence_summary: str
    metrics_json: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class StrategyEvolutionResult:
    """Persisted PR10 outputs."""

    strategy_proposals: tuple[StrategyProposalRecord, ...]
    strategy_definitions: tuple[StrategyDefinitionRecord, ...]
    strategy_evaluation_results: tuple[StrategyEvaluationResultRecord, ...]
    lifecycle_updates: tuple[StrategyEvaluationResultRecord, ...]


class StrategyEvolutionPipeline:
    """Persist strategy proposals and deterministic lifecycle transitions."""

    def __init__(
        self,
        *,
        repository: Any,
        prompt_registry: Any,
        model_name: str,
        agent_runner: Any,
    ) -> None:
        self.repository = repository
        self.agent = StrategyEvolutionAgent(
            tool_registry=None,
            prompt_registry=prompt_registry,
            model_name=model_name,
            agent_runner=agent_runner,
        )

    def run(self, *, request: StrategyEvolutionRequest) -> StrategyEvolutionResult:
        payload = {
            "trade_date": request.trade_date.isoformat(),
            "decision_time": request.decision_time.isoformat(),
            "available_for_decision_at": request.available_for_decision_at.isoformat(),
            "strategy_proposal_hints": [
                hint
                for reflection in request.daily_reflections
                for hint in reflection.strategy_proposal_hints
            ],
            "candidate_learning_factors": [
                _learning_factor_payload(factor)
                for factor in request.learning_factors
                if factor.status == "candidate"
            ],
            "observation_learning_factors": [
                _learning_factor_payload(factor)
                for factor in request.learning_factors
                if factor.status == "observation"
            ],
            "rejected_candidates": list(request.rejected_candidates),
            "outcome_performance_summaries": [
                _outcome_payload(row) for row in request.candidate_outcome_evaluations
            ],
            "existing_strategies": [
                _strategy_payload(row) for row in self.repository.load_strategy_definitions()
            ],
        }
        result = self.agent.run(payload, context=None)
        prompt_template = result.metadata["prompt_template"]
        prompt_run = result.metadata["prompt_run"]
        usage_events = result.metadata["usage_events"]
        self.repository.save_prompt_template(prompt_template)
        self.repository.save_prompt_run(prompt_run)
        self.repository.save_usage_events(usage_events)

        proposals: list[StrategyProposalRecord] = []
        created_definitions: list[StrategyDefinitionRecord] = []
        evaluation_results: list[StrategyEvaluationResultRecord] = []
        lifecycle_updates: list[StrategyEvaluationResultRecord] = []

        existing_definitions = list(self.repository.load_strategy_definitions())
        if not result.success:
            failed = StrategyProposalRecord(
                strategy_proposal_id=str(uuid.uuid4()),
                trade_date=request.trade_date,
                prompt_template=prompt_template,
                prompt_run=prompt_run,
                usage_events=list(usage_events),
                proposal_status="proposal_failed",
                proposed_strategy_id="proposal_failed",
                display_name="Proposal Failed",
                proposed_lifecycle_status=None,
                duplicate_of_strategy_id=None,
                rejection_reason="validation_failed_after_retry",
                evidence_summary="proposal_failed",
                proposal_json=dict(result.output_data or {}),
                metadata_json={"fallback_action": result.output_data.get("fallback_action")},
            )
            self.repository.save_strategy_proposal(failed)
            return StrategyEvolutionResult(
                strategy_proposals=(failed,),
                strategy_definitions=(),
                strategy_evaluation_results=(),
                lifecycle_updates=(),
            )

        for proposal_json in result.output_data.get("proposals", []):
            duplicate = find_duplicate_strategy(
                proposal=proposal_json,
                existing_definitions=existing_definitions,
            )
            if duplicate is not None:
                proposal = StrategyProposalRecord(
                    strategy_proposal_id=str(uuid.uuid4()),
                    trade_date=request.trade_date,
                    prompt_template=prompt_template,
                    prompt_run=prompt_run,
                    usage_events=list(usage_events),
                    proposal_status="duplicate_rejected",
                    proposed_strategy_id=str(proposal_json["proposed_strategy_id"]),
                    display_name=str(proposal_json["display_name"]),
                    proposed_lifecycle_status=None,
                    duplicate_of_strategy_id=duplicate.strategy_id,
                    rejection_reason="duplicate_strategy",
                    evidence_summary=str(proposal_json["evidence_summary"]),
                    proposal_json=dict(proposal_json),
                    metadata_json={},
                )
                self.repository.save_strategy_proposal(proposal)
                proposals.append(proposal)
                continue

            strategy_definition_id = str(uuid.uuid4())
            candidate_definition = StrategyDefinitionRecord(
                strategy_definition_id=strategy_definition_id,
                strategy_id=str(proposal_json["proposed_strategy_id"]),
                version="v1",
                display_name=str(proposal_json["display_name"]),
                strategy_layer="tactical_pattern",
                typical_horizon=str(proposal_json["typical_horizon"]),
                config_json={
                    "strategy_id": str(proposal_json["proposed_strategy_id"]),
                    "display_name": str(proposal_json["display_name"]),
                    "strategy_layer": "tactical_pattern",
                    "typical_horizon": str(proposal_json["typical_horizon"]),
                    "core_thesis": str(proposal_json["core_thesis"]),
                    "required_signals": list(proposal_json.get("required_signals", [])),
                    "optional_signals": list(proposal_json.get("optional_signals", [])),
                    "scoring_rules": dict(proposal_json.get("scoring_rules", {})),
                    "risk_tags": list(proposal_json.get("risk_tags", [])),
                    "macro_blocked_regimes": list(proposal_json.get("macro_blocked_regimes", [])),
                    "invalidators": list(proposal_json.get("invalidators", [])),
                },
                lifecycle_status="candidate",
                is_active=True,
                source="reflection_learning",
            )
            self.repository.save_strategy_definition(candidate_definition)

            final_definition = candidate_definition
            if required_signals_are_computable(proposal_json.get("required_signals", [])):
                final_definition = replace(candidate_definition, lifecycle_status="shadow")
                self.repository.save_strategy_definition(final_definition)
                transition = StrategyEvaluationResultRecord(
                    strategy_evaluation_result_id=str(uuid.uuid4()),
                    strategy_id=final_definition.strategy_id,
                    strategy_definition_id=final_definition.strategy_definition_id,
                    strategy_proposal_id=None,
                    evaluation_type="lifecycle_transition",
                    evaluation_status="promoted",
                    prior_lifecycle_status="candidate",
                    new_lifecycle_status="shadow",
                    reason_code="required_signals_computable",
                    evidence_summary="Proposal required signals are computable in current scan pipeline.",
                    metrics_json={"required_signals": list(proposal_json.get("required_signals", []))},
                    created_at=request.decision_time,
                )
                self.repository.save_strategy_evaluation_result(transition)
                evaluation_results.append(transition)
                lifecycle_updates.append(transition)

            proposal = StrategyProposalRecord(
                strategy_proposal_id=str(uuid.uuid4()),
                trade_date=request.trade_date,
                prompt_template=prompt_template,
                prompt_run=prompt_run,
                usage_events=list(usage_events),
                proposal_status="accepted",
                proposed_strategy_id=final_definition.strategy_id,
                display_name=final_definition.display_name,
                proposed_lifecycle_status=final_definition.lifecycle_status,
                duplicate_of_strategy_id=None,
                rejection_reason=None,
                evidence_summary=str(proposal_json["evidence_summary"]),
                proposal_json=dict(proposal_json),
                metadata_json={"strategy_definition_id": final_definition.strategy_definition_id},
            )
            self.repository.save_strategy_proposal(proposal)
            proposals.append(proposal)
            created_definitions.append(final_definition)
            existing_definitions.append(final_definition)

        for definition in self.repository.load_strategy_definitions():
            transition = maybe_promote_strategy_from_outcomes(
                definition=definition,
                outcomes=request.candidate_outcome_evaluations,
                decision_time=request.decision_time,
            )
            if transition is None:
                continue
            updated = replace(definition, lifecycle_status=transition.new_lifecycle_status or definition.lifecycle_status)
            self.repository.save_strategy_definition(updated)
            self.repository.save_strategy_evaluation_result(transition)
            evaluation_results.append(transition)
            lifecycle_updates.append(transition)
            created_definitions.append(updated)

        return StrategyEvolutionResult(
            strategy_proposals=tuple(proposals),
            strategy_definitions=tuple(created_definitions),
            strategy_evaluation_results=tuple(evaluation_results),
            lifecycle_updates=tuple(lifecycle_updates),
        )


def required_signals_are_computable(required_signals: Iterable[str]) -> bool:
    required = {str(signal) for signal in required_signals}
    return bool(required) and required <= COMPUTABLE_REQUIRED_SIGNALS


def find_duplicate_strategy(
    *,
    proposal: dict[str, Any],
    existing_definitions: Iterable[StrategyDefinitionRecord],
) -> StrategyDefinitionRecord | None:
    proposal_required = {str(item) for item in proposal.get("required_signals", [])}
    proposal_risk_tags = {str(item) for item in proposal.get("risk_tags", [])}
    proposal_horizon = str(proposal.get("typical_horizon", ""))
    proposal_thesis_tokens = _normalize_text_tokens(str(proposal.get("core_thesis", "")))
    for definition in existing_definitions:
        config = definition.config_json or {}
        required_overlap = _jaccard(proposal_required, set(config.get("required_signals") or []))
        risk_overlap = _jaccard(proposal_risk_tags, set(config.get("risk_tags") or []))
        same_horizon = proposal_horizon == str(definition.typical_horizon)
        thesis_overlap = _jaccard(proposal_thesis_tokens, _normalize_text_tokens(str(config.get("core_thesis") or "")))
        if same_horizon and required_overlap >= 0.75 and (risk_overlap >= 0.5 or thesis_overlap >= 0.5):
            return definition
    return None


def maybe_promote_strategy_from_outcomes(
    *,
    definition: StrategyDefinitionRecord,
    outcomes: Iterable[CandidateOutcomeEvaluationRecord],
    decision_time: datetime,
) -> StrategyEvaluationResultRecord | None:
    if definition.lifecycle_status not in {"shadow", "experimental"}:
        return None
    relevant = [row for row in outcomes if row.strategy_id == definition.strategy_id and row.evaluation_status == "final"]
    if len(relevant) < 3:
        return None
    mean_alpha = sum(float(row.alpha or 0.0) for row in relevant) / len(relevant)
    win_rate = sum(1 for row in relevant if float(row.alpha or 0.0) > 0) / len(relevant)
    if definition.lifecycle_status == "shadow" and mean_alpha > 0 and win_rate >= 0.6:
        return StrategyEvaluationResultRecord(
            strategy_evaluation_result_id=str(uuid.uuid4()),
            strategy_id=definition.strategy_id,
            strategy_definition_id=definition.strategy_definition_id,
            strategy_proposal_id=None,
            evaluation_type="lifecycle_transition",
            evaluation_status="promoted",
            prior_lifecycle_status="shadow",
            new_lifecycle_status="experimental",
            reason_code="positive_shadow_evidence",
            evidence_summary="Repeated positive shadow evidence met the promotion gate.",
            metrics_json={"sample_size": len(relevant), "mean_alpha": mean_alpha, "win_rate": win_rate},
            created_at=decision_time,
        )
    if definition.lifecycle_status == "experimental" and mean_alpha > 0.01 and win_rate >= 0.6:
        return StrategyEvaluationResultRecord(
            strategy_evaluation_result_id=str(uuid.uuid4()),
            strategy_id=definition.strategy_id,
            strategy_definition_id=definition.strategy_definition_id,
            strategy_proposal_id=None,
            evaluation_type="lifecycle_transition",
            evaluation_status="promoted",
            prior_lifecycle_status="experimental",
            new_lifecycle_status="active",
            reason_code="positive_experimental_evidence",
            evidence_summary="Experimental paper-trade evidence met the active promotion gate.",
            metrics_json={"sample_size": len(relevant), "mean_alpha": mean_alpha, "win_rate": win_rate},
            created_at=decision_time,
        )
    return None

def _learning_factor_payload(factor: LearningFactorRecord) -> dict[str, Any]:
    return {
        "factor_key": factor.factor_key,
        "title": factor.title,
        "factor_type": factor.factor_type,
        "condition": factor.condition,
        "recommendation": factor.recommendation,
        "confidence": factor.confidence,
        "effect_tags": list(factor.effect_tags),
        "evidence": list(factor.evidence),
    }


def _outcome_payload(row: CandidateOutcomeEvaluationRecord) -> dict[str, Any]:
    return {
        "strategy_id": row.strategy_id,
        "ticker": row.ticker,
        "alpha": row.alpha,
        "candidate_return": row.candidate_return,
        "regime": row.regime,
        "sector_theme": row.sector_theme,
        "metadata_json": dict(row.metadata_json),
    }


def _strategy_payload(row: StrategyDefinitionRecord) -> dict[str, Any]:
    return {
        "strategy_id": row.strategy_id,
        "display_name": row.display_name,
        "typical_horizon": row.typical_horizon,
        "lifecycle_status": row.lifecycle_status,
        "source": row.source,
        "config_json": dict(row.config_json),
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _normalize_text_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}
