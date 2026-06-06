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
from src.trading.signals import SignalSnapshotResult
from src.trading.signals.sources import EventNewsItemRecord
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
    prompt_template: Any
    prompt_run: PromptRunRecord | None
    usage_events: list[UsageEventRecord]
    decision_time: datetime
    available_for_decision_at: datetime
    key_drivers: list[str] = field(default_factory=list)
    counterarguments: list[str] = field(default_factory=list)
    invalidators: list[str] = field(default_factory=list)
    context_snapshot_json: dict[str, Any] = field(default_factory=dict)
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
        signal_snapshot_by_id = {
            snapshot.signal_snapshot_id: snapshot
            for snapshot in self.repository.load_signal_snapshots_for_decision(
                decision_time=decision_time,
                snapshot_type="pre_open",
            )
        }
        decisions: list[TradingDecisionRecord] = []
        for classification in classifications:
            candidate = candidate_by_id[classification.candidate_score_id]
            risk = risk_by_classification_id.get(classification.trade_classification_id)
            signal_snapshot = signal_snapshot_by_id.get(candidate.signal_snapshot_id)
            if signal_snapshot is None:
                decision = self._build_missing_signal_snapshot_decision(
                    candidate=candidate,
                    classification=classification,
                    risk=risk,
                    decision_time=decision_time,
                )
                self.repository.save_trading_decision(decision)
                self._record_manual_result(candidate, classification, risk)
                decisions.append(decision)
                continue
            payload = self._build_input_payload(candidate, classification, risk, signal_snapshot)
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
                key_drivers=list(final_output.get("key_drivers", [])),
                counterarguments=list(final_output.get("counterarguments", [])),
                invalidators=list(final_output.get("invalidators", [])),
                prompt_template=prompt_template,
                prompt_run=prompt_run,
                usage_events=list(usage_events),
                decision_time=decision_time,
                available_for_decision_at=candidate.available_for_decision_at,
                context_snapshot_json=payload,
                metadata_json={
                    "paper_trade_authorized": bool(
                        candidate.manual_request_id is None
                        or payload["manual_request_context"].get("manual_request_mode") == "paper_trade_eligible"
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
                    "key_drivers": final_output.get("key_drivers", []),
                    "counterarguments": final_output.get("counterarguments", []),
                    "risk_checks": final_output.get("risk_checks", []),
                    "learning_factors_used": final_output.get("learning_factors_used", []),
                    "signal_snapshot_id": signal_snapshot.signal_snapshot_id,
                    "source_freshness": signal_snapshot.source_freshness_json,
                    "selected_strategy_context": payload["classification_context"].get("selected_strategy_context", {}),
                    "historical_outcomes": payload["candidate_context"].get("historical_outcomes", []),
                    "fallback_action": final_output.get("fallback_action"),
                    "fallback_reason": None,
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
        signal_snapshot: SignalSnapshotResult,
    ) -> dict[str, Any]:
        evidence_items = self._build_evidence_items(signal_snapshot)
        input_model = TradingDecisionInput(
            ticker=candidate.ticker,
            decision_time=candidate.decision_time,
            available_for_decision_at=candidate.available_for_decision_at,
            has_existing_position=False,
            signal_snapshot={
                "signal_snapshot_id": signal_snapshot.signal_snapshot_id,
                "snapshot_type": signal_snapshot.snapshot_type,
                "decision_time": signal_snapshot.decision_time,
                "available_for_decision_at": signal_snapshot.available_for_decision_at,
                "signal_json": signal_snapshot.signal_json,
                "source_freshness_json": signal_snapshot.source_freshness_json,
                "missing_signals_json": signal_snapshot.missing_signals_json,
                "stale_signals_json": signal_snapshot.stale_signals_json,
                "evidence_items": evidence_items,
            },
            candidate_context={
                "candidate_score": candidate.candidate_score,
                "strategy_id": candidate.strategy_id,
                "strategy_version": candidate.strategy_version,
                "selection_source": candidate.selection_source,
                "selection_reason": candidate.selection_reason,
                "benchmark_context": candidate.benchmark_context,
                "core_signal_evidence": candidate.core_signal_evidence,
                "historical_outcomes": [],
            },
            classification_context={
                "expression_bucket_id": classification.expression_bucket_id,
                "trade_identity": classification.trade_identity,
                "classification_result_status": classification.result_status,
                "instrument_type": "stock" if classification.trade_identity != "watch_only" else "watch",
                "selected_strategy_context": classification.selected_strategy_context_json,
            },
            risk_context={
                "status": risk.status if risk is not None else None,
                "approved_weight": float(risk.approved_weight) if risk is not None else 0.0,
                "reason_code": risk.reason_code if risk is not None else None,
            },
            manual_request_context={
                "manual_request_id": candidate.manual_request_id,
                "manual_request_mode": self._manual_request_mode(candidate.manual_request_id),
            },
        )
        return input_model.model_dump(mode="json")

    def _build_evidence_items(
        self,
        signal_snapshot: SignalSnapshotResult,
    ) -> list[dict[str, str]]:
        news_refs = [
            ref
            for ref in signal_snapshot.source_record_refs_json
            if ref.get("source_table") == "event_news_items" and ref.get("source_record_id")
        ]
        if not news_refs:
            return []
        load_event_news_items = getattr(self.repository, "load_event_news_items", None)
        if load_event_news_items is None:
            return []
        news_items = load_event_news_items(
            source_record_ids=tuple(str(ref["source_record_id"]) for ref in news_refs)
        )
        news_by_id = {item.event_news_item_id: item for item in news_items}
        evidence_items: list[dict[str, str]] = []
        for ref in news_refs:
            source_record_id = str(ref["source_record_id"])
            item = news_by_id.get(source_record_id)
            if item is None:
                continue
            evidence_items.append(
                {
                    "source": str(ref.get("source") or item.provider),
                    "source_table": "event_news_items",
                    "source_record_id": source_record_id,
                    "source_text": _render_news_source_text(item),
                    "available_time": signal_snapshot.source_available_times_json.get(
                        source_record_id,
                        item.available_for_decision_at.isoformat(),
                    ),
                }
            )
        return evidence_items

    def _build_missing_signal_snapshot_decision(
        self,
        *,
        candidate: CandidateScoreRecord,
        classification: TradeClassificationRecord,
        risk: RiskDecisionRecord | None,
        decision_time: datetime,
    ) -> TradingDecisionRecord:
        fallback_action = "no_trade"
        manual_request_mode = self._manual_request_mode(candidate.manual_request_id)
        context_snapshot = {
            "ticker": candidate.ticker,
            "decision_time": decision_time.isoformat(),
            "available_for_decision_at": candidate.available_for_decision_at.isoformat(),
            "has_existing_position": False,
            "signal_snapshot": {
                "signal_snapshot_id": candidate.signal_snapshot_id,
                "missing": True,
            },
            "candidate_context": {
                "candidate_score": candidate.candidate_score,
                "strategy_id": candidate.strategy_id,
                "strategy_version": candidate.strategy_version,
                "selection_source": candidate.selection_source,
                "selection_reason": candidate.selection_reason,
                "benchmark_context": candidate.benchmark_context,
                "core_signal_evidence": candidate.core_signal_evidence,
                "historical_outcomes": [],
            },
            "classification_context": {
                "expression_bucket_id": classification.expression_bucket_id,
                "trade_identity": classification.trade_identity,
                "classification_result_status": classification.result_status,
                "instrument_type": "stock" if classification.trade_identity != "watch_only" else "watch",
                "selected_strategy_context": classification.selected_strategy_context_json,
            },
            "risk_context": {
                "status": risk.status if risk is not None else None,
                "approved_weight": float(risk.approved_weight) if risk is not None else 0.0,
                "reason_code": risk.reason_code if risk is not None else None,
            },
            "manual_request_context": {
                "manual_request_id": candidate.manual_request_id,
                "manual_request_mode": manual_request_mode,
            },
        }
        return TradingDecisionRecord(
            trading_decision_id=str(uuid.uuid4()),
            candidate_score_id=candidate.candidate_score_id,
            trade_classification_id=classification.trade_classification_id,
            risk_decision_id=risk.risk_decision_id if risk is not None else None,
            ticker=candidate.ticker,
            decision=fallback_action,
            strategy_id=candidate.strategy_id,
            strategy_version=candidate.strategy_version,
            expression_bucket_id=classification.expression_bucket_id,
            expression_bucket_version=classification.expression_bucket_version,
            trade_identity=classification.trade_identity,
            instrument_type="stock" if classification.trade_identity != "watch_only" else "watch",
            selection_source=candidate.selection_source,
            manual_request_id=candidate.manual_request_id,
            confidence=0.0,
            target_weight=0.0,
            approved_weight=float(risk.approved_weight if risk is not None else 0.0),
            max_loss_pct=0.0,
            time_horizon="monitor_only",
            thesis="Signal snapshot context was unavailable at decision time.",
            key_drivers=[],
            counterarguments=["Signal snapshot context was unavailable at decision time."],
            invalidators=list(candidate.invalidators),
            prompt_template=None,
            prompt_run=None,
            usage_events=[],
            decision_time=decision_time,
            available_for_decision_at=candidate.available_for_decision_at,
            context_snapshot_json=context_snapshot,
            metadata_json={
                "paper_trade_authorized": False,
                "selection_reason": candidate.selection_reason,
                "strategy_lifecycle_status": candidate.strategy_lifecycle_status,
                "strategy_source": candidate.strategy_source,
                "classification_result_status": classification.result_status,
                "risk_status": risk.status if risk is not None else None,
                "confidence_basis": {},
                "benchmark_context": candidate.benchmark_context,
                "key_drivers": [],
                "counterarguments": ["Signal snapshot context was unavailable at decision time."],
                "risk_checks": [],
                "learning_factors_used": [],
                "signal_snapshot_id": candidate.signal_snapshot_id,
                "source_freshness": {},
                "selected_strategy_context": classification.selected_strategy_context_json,
                "historical_outcomes": [],
                "fallback_action": fallback_action,
                "fallback_reason": "missing_signal_snapshot_context",
            },
        )

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


def _render_news_source_text(item: EventNewsItemRecord) -> str:
    parts = [part.strip() for part in (item.headline, item.summary) if isinstance(part, str) and part.strip()]
    return "\n\n".join(parts)
