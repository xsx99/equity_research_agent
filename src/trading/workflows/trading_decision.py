"""PR05 trading decision workflow."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.agents.trading import PromptRunRecord, TradingAgent, UsageEventRecord
from src.agents.trading_schemas import TradingDecisionInput
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.risk import RiskDecisionRecord
from src.trading.signals import SignalSnapshotResult
from src.trading.signals.event_news import build_event_news_signals
from src.trading.signals.sources import (
    EventNewsItemRecord,
    source_record_from_event_news_item,
)
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
        news_evidence_limit: int | None = None,
    ) -> None:
        self.repository = repository
        self.manual_request_service = manual_request_service
        self.news_evidence_limit = max(1, news_evidence_limit or _news_evidence_limit())
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
        previous_snapshot = self._load_previous_signal_snapshot(signal_snapshot)
        windowed_news_items = self._load_windowed_news_items(signal_snapshot, previous_snapshot)
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
                "signal_json": self._build_llm_signal_json(signal_snapshot, windowed_news_items),
                "source_freshness_json": signal_snapshot.source_freshness_json,
                "missing_signals_json": signal_snapshot.missing_signals_json,
                "stale_signals_json": signal_snapshot.stale_signals_json,
                "evidence_items": self._build_evidence_items(windowed_news_items, signal_snapshot),
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
        return _round_nested_floats(input_model.model_dump(mode="json"))

    def _build_evidence_items(
        self,
        news_items: tuple[EventNewsItemRecord, ...],
        signal_snapshot: SignalSnapshotResult,
    ) -> list[dict[str, str]]:
        evidence_items: list[dict[str, str]] = []
        for item in self._select_evidence_news_items(news_items):
            evidence_items.append(
                {
                    "source": item.provider,
                    "source_table": "event_news_items",
                    "source_record_id": item.event_news_item_id,
                    "source_text": _render_news_source_text(item),
                    "available_time": signal_snapshot.source_available_times_json.get(
                        item.event_news_item_id,
                        item.available_for_decision_at.isoformat(),
                    ),
                }
            )
        return evidence_items

    def _select_evidence_news_items(
        self,
        news_items: tuple[EventNewsItemRecord, ...],
    ) -> tuple[EventNewsItemRecord, ...]:
        representatives: dict[str, EventNewsItemRecord] = {}
        for item in news_items:
            group_key = str(
                item.metadata_json.get("duplicate_group_key")
                or item.dedupe_key
                or item.event_news_item_id
            )
            current = representatives.get(group_key)
            if current is None or _evidence_priority(item) < _evidence_priority(current):
                representatives[group_key] = item
        ranked = sorted(representatives.values(), key=_evidence_priority)
        return tuple(ranked[: self.news_evidence_limit])

    def _build_llm_signal_json(
        self,
        signal_snapshot: SignalSnapshotResult,
        news_items: tuple[EventNewsItemRecord, ...],
    ) -> dict[str, Any]:
        signal_json = {
            family: dict(values)
            for family, values in signal_snapshot.signal_json.items()
        }
        signal_json["events_news"] = self._build_windowed_events_news_view(
            base_values=signal_json.get("events_news", {}),
            news_items=news_items,
            decision_time=signal_snapshot.decision_time,
        )
        return signal_json

    def _build_windowed_events_news_view(
        self,
        *,
        base_values: dict[str, Any],
        news_items: tuple[EventNewsItemRecord, ...],
        decision_time: datetime,
    ) -> dict[str, Any]:
        if not news_items:
            return dict(base_values)
        windowed = build_event_news_signals(
            tuple(source_record_from_event_news_item(item) for item in news_items),
            decision_time=decision_time,
        ).values
        merged = dict(base_values)
        for key in _WINDOWED_EVENT_NEWS_FIELDS:
            merged[key] = windowed.get(key)
        return merged

    def _load_previous_signal_snapshot(
        self,
        signal_snapshot: SignalSnapshotResult,
    ) -> SignalSnapshotResult | None:
        loader = getattr(self.repository, "load_previous_signal_snapshot", None)
        if loader is None:
            return None
        return loader(
            ticker=signal_snapshot.ticker,
            before_decision_time=signal_snapshot.decision_time,
            snapshot_type=signal_snapshot.snapshot_type,
        )

    def _load_windowed_news_items(
        self,
        signal_snapshot: SignalSnapshotResult,
        previous_snapshot: SignalSnapshotResult | None,
    ) -> tuple[EventNewsItemRecord, ...]:
        news_refs = [
            ref
            for ref in signal_snapshot.source_record_refs_json
            if ref.get("source_table") == "event_news_items" and ref.get("source_record_id")
        ]
        if not news_refs:
            return ()
        load_event_news_items = getattr(self.repository, "load_event_news_items", None)
        if load_event_news_items is None:
            return ()
        news_items = load_event_news_items(
            source_record_ids=tuple(str(ref["source_record_id"]) for ref in news_refs)
        )
        news_by_id = {item.event_news_item_id: item for item in news_items}
        scan_start = previous_snapshot.decision_time if previous_snapshot is not None else None
        windowed: list[EventNewsItemRecord] = []
        for ref in news_refs:
            item = news_by_id.get(str(ref["source_record_id"]))
            if item is None:
                continue
            if scan_start is not None and item.available_for_decision_at <= scan_start:
                continue
            windowed.append(item)
        return tuple(windowed)

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


_WINDOWED_EVENT_NEWS_FIELDS = (
    "own_earnings_event_type",
    "analyst_upgrade_count",
    "analyst_downgrade_count",
    "price_target_revision_score",
    "guidance_news_flag",
    "customer_order_news_flag",
    "regulatory_news_flag",
    "high_signal_news_count_24h",
    "high_signal_news_count_7d",
    "sentiment_direction",
    "catalyst_quality_score",
    "direct_negative_catalyst_type",
)

_EVIDENCE_IMPORTANCE_PRIORITY = {"critical": 0, "high": 1, "medium": 2, "normal": 3, "low": 4}


def _news_evidence_limit() -> int:
    raw = os.getenv("TRADING_NEWS_EVIDENCE_LIMIT", "4").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 4


def _evidence_priority(item: EventNewsItemRecord) -> tuple[int, int, datetime, str]:
    importance_rank = _EVIDENCE_IMPORTANCE_PRIORITY.get(str(item.importance or "").casefold(), 5)
    specificity = int(item.metadata_json.get("specificity_score", 0))
    return (
        importance_rank,
        -specificity,
        item.available_for_decision_at,
        item.event_news_item_id,
    )


def _round_nested_floats(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, list):
        return [_round_nested_floats(item) for item in value]
    if isinstance(value, tuple):
        return [_round_nested_floats(item) for item in value]
    if isinstance(value, dict):
        return {key: _round_nested_floats(item) for key, item in value.items()}
    return value
