"""PR05 trading decision workflow."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.agents.trading import PromptRunRecord, TradingAgent, UsageEventRecord
from src.agents.trading_schemas import TradingDecisionInput
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.risk import RiskDecisionRecord
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord


@dataclass(frozen=True)
class TradingDecisionRecord:
    """Persistable PR05 trading decision artifact."""

    trading_decision_id: str
    candidate_score_id: str | None
    trade_classification_id: str | None
    risk_decision_id: str | None
    ticker: str
    decision: str
    strategy_id: str
    strategy_version: str
    expression_bucket_id: str
    expression_bucket_version: str
    trade_identity: str
    instrument_type: str
    selection_source: str
    manual_request_id: str | None
    confidence: float
    target_weight: float
    approved_weight: float
    max_loss_pct: float
    time_horizon: str
    thesis: str
    invalidators: list[str]
    prompt_template: Any
    prompt_run: PromptRunRecord
    usage_events: list[UsageEventRecord]
    decision_time: datetime
    available_for_decision_at: datetime
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TradingDecisionPipelineResult:
    """Persisted PR05 decision artifacts."""

    decisions: tuple[TradingDecisionRecord, ...]


class TradingDecisionPipeline:
    """Generate bounded trading decisions without broker side effects."""

    def __init__(
        self,
        *,
        repository: Any,
        prompt_registry: Any,
        manual_request_service: ManualTickerRequestService | None = None,
        model_name: str,
        agent_runner: Any,
    ) -> None:
        self.repository = repository
        self.manual_request_service = manual_request_service
        self.agent = TradingAgent(
            tool_registry=None,
            prompt_registry=prompt_registry,
            model_name=model_name,
            agent_runner=agent_runner,
        )

    def run(
        self,
        *,
        candidates: tuple[CandidateScoreRecord, ...],
        classifications: tuple[TradeClassificationRecord, ...],
        risk_decisions: tuple[RiskDecisionRecord, ...],
        decision_time: datetime,
    ) -> TradingDecisionPipelineResult:
        candidate_by_id = {candidate.candidate_score_id: candidate for candidate in candidates}
        risk_by_classification_id = {
            decision.trade_classification_id: decision
            for decision in risk_decisions
            if decision.trade_classification_id is not None
        }
        decisions: list[TradingDecisionRecord] = []
        for classification in classifications:
            candidate = candidate_by_id[classification.candidate_score_id]
            risk = risk_by_classification_id.get(classification.trade_classification_id)
            payload = self._build_input_payload(candidate, classification, risk)
            result = self.agent.run(payload, context=None)  # ToolContext is unused here.
            prompt_template = result.metadata["prompt_template"]
            prompt_run = result.metadata["prompt_run"]
            usage_events = result.metadata["usage_events"]
            final_output = dict(result.output_data or {})
            final_output = self._apply_guardrails(
                final_output=final_output,
                candidate=candidate,
                classification=classification,
                risk=risk,
            )
            decision = TradingDecisionRecord(
                trading_decision_id=str(uuid.uuid4()),
                candidate_score_id=candidate.candidate_score_id,
                trade_classification_id=classification.trade_classification_id,
                risk_decision_id=risk.risk_decision_id if risk is not None else None,
                ticker=candidate.ticker,
                decision=str(final_output["decision"]),
                strategy_id=candidate.strategy_id,
                strategy_version=candidate.strategy_version,
                expression_bucket_id=classification.expression_bucket_id,
                expression_bucket_version=classification.expression_bucket_version,
                trade_identity=classification.trade_identity,
                instrument_type=str(final_output.get("instrument_type", "stock")),
                selection_source=candidate.selection_source,
                manual_request_id=candidate.manual_request_id,
                confidence=float(final_output.get("confidence", 0.0)),
                target_weight=float(final_output.get("target_weight", 0.0)),
                approved_weight=float(risk.approved_weight if risk is not None else 0.0),
                max_loss_pct=float(final_output.get("max_loss_pct", 0.0)),
                time_horizon=str(final_output.get("time_horizon", classification.intended_horizon)),
                thesis=str(final_output.get("thesis", "")),
                invalidators=list(final_output.get("invalidators", [])),
                prompt_template=prompt_template,
                prompt_run=prompt_run,
                usage_events=list(usage_events),
                decision_time=decision_time,
                available_for_decision_at=candidate.available_for_decision_at,
                metadata_json={
                    "paper_trade_authorized": bool(
                        candidate.manual_request_id is None
                        or payload["manual_request_mode"] == "paper_trade_eligible"
                    )
                    and candidate.strategy_lifecycle_status in {"active", "experimental"}
                    and str(final_output["decision"]) not in {"no_trade", "hold"},
                    "selection_reason": candidate.selection_reason,
                    "strategy_lifecycle_status": candidate.strategy_lifecycle_status,
                    "strategy_source": candidate.strategy_source,
                    "classification_result_status": classification.result_status,
                    "risk_status": risk.status if risk is not None else None,
                    "confidence_basis": final_output.get("confidence_basis", {}),
                    "benchmark_context": final_output.get("benchmark_context", {}),
                    "key_signals": final_output.get("key_signals", []),
                    "risk_checks": final_output.get("risk_checks", []),
                    "learning_factors_used": final_output.get("learning_factors_used", []),
                    "source_availability": payload["source_availability"],
                    "selected_strategy_context": payload["selected_strategy_context"],
                    "historical_outcomes": payload["historical_outcomes"],
                    "fallback_action": final_output.get("fallback_action"),
                },
            )
            self.repository.save_prompt_template(prompt_template)
            self.repository.save_prompt_run(prompt_run)
            self.repository.save_usage_events(usage_events)
            self.repository.save_trading_decision(decision)
            self._record_manual_result(candidate, classification, risk)
            decisions.append(decision)
        return TradingDecisionPipelineResult(decisions=tuple(decisions))

    def _build_input_payload(
        self,
        candidate: CandidateScoreRecord,
        classification: TradeClassificationRecord,
        risk: RiskDecisionRecord | None,
    ) -> dict[str, Any]:
        input_model = TradingDecisionInput(
            ticker=candidate.ticker,
            strategy_id=candidate.strategy_id,
            expression_bucket_id=classification.expression_bucket_id,
            trade_identity=classification.trade_identity,
            instrument_type="stock" if classification.trade_identity != "watch_only" else "watch",
            selection_source=candidate.selection_source,
            manual_request_id=candidate.manual_request_id,
            manual_request_mode=self._manual_request_mode(candidate.manual_request_id),
            decision_time=candidate.decision_time,
            available_for_decision_at=candidate.available_for_decision_at,
            has_existing_position=False,
            candidate_score=candidate.candidate_score,
            classification_result_status=classification.result_status,
            benchmark_context=candidate.benchmark_context,
            confidence_basis={},
            risk_context={
                "status": risk.status if risk is not None else None,
                "approved_weight": float(risk.approved_weight) if risk is not None else 0.0,
                "reason_code": risk.reason_code if risk is not None else None,
            },
            source_availability={"source_record_refs_count": len(candidate.source_record_refs_json)},
            historical_outcomes=[],
            selected_strategy_context=classification.selected_strategy_context_json,
        )
        return input_model.model_dump(mode="json")

    def _apply_guardrails(
        self,
        *,
        final_output: dict[str, Any],
        candidate: CandidateScoreRecord,
        classification: TradeClassificationRecord,
        risk: RiskDecisionRecord | None,
    ) -> dict[str, Any]:
        decision = str(final_output["decision"])
        if decision == "enter_short" and str(final_output.get("instrument_type")) == "stock":
            final_output["decision"] = "no_trade"
            final_output["thesis"] = (
                f"{final_output.get('thesis', '')} Short common-stock trades are disabled in V2."
            ).strip()
        if risk is not None and risk.status == "rejected" and decision not in {"hold", "exit", "reduce", "no_trade"}:
            final_output["decision"] = "no_trade"
        if candidate.manual_request_id is not None and self._manual_request_mode(candidate.manual_request_id) == "review_only":
            if decision not in {"hold", "exit", "reduce", "no_trade"}:
                final_output["decision"] = "no_trade"
        if classification.trade_identity == "watch_only" and decision not in {"hold", "no_trade"}:
            final_output["decision"] = "no_trade"
        if candidate.strategy_lifecycle_status == "candidate" and decision not in {"hold", "no_trade"}:
            final_output["decision"] = "no_trade"
        return final_output

    def _record_manual_result(
        self,
        candidate: CandidateScoreRecord,
        classification: TradeClassificationRecord,
        risk: RiskDecisionRecord | None,
    ) -> None:
        if self.manual_request_service is None or candidate.manual_request_id is None:
            return
        result_status = classification.result_status
        if risk is not None and risk.status == "rejected":
            result_status = "blocked_by_risk"
        self.manual_request_service.record_evaluation(
            candidate.manual_request_id,
            result_status=result_status,
            signal_snapshot_id=candidate.signal_snapshot_id,
        )

    def _manual_request_mode(self, request_id: str | None) -> str | None:
        if request_id is None or self.manual_request_service is None:
            return None
        for request in self.manual_request_service.load_active():
            if request.request_id == request_id:
                return request.mode
        return None
