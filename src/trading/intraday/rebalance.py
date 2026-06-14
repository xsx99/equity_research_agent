"""Intraday rebalance prompt handling, guardrails, and optional execution for PR8."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import ValidationError

from src.agents.prompt_registry import PromptRegistry
from src.agents.trading import PromptRunRecord, UsageEventRecord, _coerce_json_object, _normalize_runner_response
from src.agents.trading_schemas import (
    IntradayRebalanceInput,
    IntradayRebalanceOutput,
    IntradayRebalanceOutputFallback,
)
from src.trading.risk import PortfolioRiskIntentRecord, PositionRiskActionRecord, RiskConfigResolver, RiskDecisionRecord
from src.trading.workflows.paper_execution import PaperExecutionWorkflow
from src.trading.workflows.trading_decision import TradingDecisionRecord


AgentRunner = Callable[[str, str], Any]


@dataclass(frozen=True)
class IntradayRebalanceRequest:
    """Operator- and signal-driven intraday rebalance request."""

    ticker: str
    baseline_signal_snapshot_id: str
    intraday_signal_snapshot_id: str
    previous_intraday_snapshot_id: str | None
    selection_source: str
    strategy_id: str
    strategy_version: str
    expression_bucket_id: str
    expression_bucket_version: str
    trade_identity: str
    instrument_type: str
    decision_time: datetime
    available_for_decision_at: datetime
    current_price: float
    atr_pct: float
    average_daily_dollar_volume: float
    existing_position: bool
    current_position_quantity: float
    current_position_market_value: float
    candidate_score: float
    target_weight: float
    signal_freshness: dict[str, str]
    delta_vs_baseline_json: dict[str, Any]
    delta_vs_previous_json: dict[str, Any]
    alerts: tuple[dict[str, Any], ...]
    allow_open_new: bool
    direct_company_negative_evidence: bool
    bearish_signal_sources: tuple[str, ...]
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntradayRebalanceDecisionRecord:
    """Persisted intraday rebalance decision plus prompt telemetry."""

    intraday_rebalance_decision_id: str
    ticker: str
    action: str
    status: str
    reason_code: str
    confidence: float
    target_weight: float
    approved_quantity: float
    thesis: str
    urgency: str
    rationale: tuple[str, ...]
    prompt_template: Any
    prompt_run: PromptRunRecord
    usage_events: list[UsageEventRecord]
    decision_time: datetime
    available_for_decision_at: datetime
    risk_decision_id: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntradayRebalancePipelineResult:
    """Persisted intraday rebalance artifacts."""

    decisions: tuple[IntradayRebalanceDecisionRecord, ...]


class IntradayRebalancePipeline:
    """Run bounded intraday rebalance decisions with guardrails and optional execution."""

    def __init__(
        self,
        *,
        repository: Any,
        prompt_registry: PromptRegistry,
        model_name: str,
        agent_runner: AgentRunner,
        broker: Any | None = None,
    ) -> None:
        self.repository = repository
        self.prompt_registry = prompt_registry
        self.model_name = model_name
        self.agent_runner = agent_runner
        self.broker = broker

    def run(
        self,
        *,
        rebalance_requests: tuple[IntradayRebalanceRequest, ...],
        portfolio_context: Any,
        risk_appetite: str,
        portfolio_risk_intent: PortfolioRiskIntentRecord | None = None,
        trade_date: datetime | None = None,
        execute_approved: bool = False,
    ) -> IntradayRebalancePipelineResult:
        resolver = RiskConfigResolver()
        config = resolver.resolve(
            risk_appetite=risk_appetite,
            portfolio_context=portfolio_context,
            macro_risk_budget_multiplier=1.0,
        )
        decisions: list[IntradayRebalanceDecisionRecord] = []
        execution_decisions: list[TradingDecisionRecord] = []
        execution_risk_decisions: list[RiskDecisionRecord] = []

        for request in rebalance_requests:
            output, prompt_template, prompt_run, usage_events, status, reason_code = self._run_agent(request)
            final_output, status, reason_code = self._apply_guardrails(
                request=request,
                output=output,
                status=status,
                reason_code=reason_code,
            )
            final_output, status, reason_code = self._apply_portfolio_risk_intent(
                request=request,
                output=final_output,
                status=status,
                reason_code=reason_code,
                portfolio_risk_intent=portfolio_risk_intent,
            )
            risk_decision = None
            approved_quantity = 0.0
            if final_output["action"] in {"exit", "reduce"} and request.existing_position:
                approved_quantity = request.current_position_quantity
                risk_decision = RiskDecisionRecord.create(
                    candidate_score_id=None,
                    trade_classification_id=None,
                    position_sizing_decision_id=None,
                    ticker=request.ticker,
                    status="approved",
                    reason_code="intraday_rebalance_existing_position",
                    approved_weight=0.0,
                    approved_notional=request.current_position_market_value,
                    approved_quantity=approved_quantity,
                    portfolio_risk_snapshot_id=None,
                    applied_rules=["intraday_existing_position"],
                    binding_constraint=_binding_constraint(portfolio_risk_intent),
                    lookahead_risk_source=_lookahead_risk_source(
                        portfolio_risk_intent,
                        request=request,
                    ),
                    generated_hedge_action=_generated_hedge_action(portfolio_risk_intent),
                    decision_time=request.decision_time,
                )

            decision = IntradayRebalanceDecisionRecord(
                intraday_rebalance_decision_id=str(uuid.uuid4()),
                ticker=request.ticker,
                action=str(final_output["action"]),
                status=status,
                reason_code=reason_code,
                confidence=float(final_output.get("confidence", 0.0)),
                target_weight=float(final_output.get("target_weight", 0.0)),
                approved_quantity=approved_quantity,
                thesis=str(final_output.get("thesis", "")),
                urgency=str(final_output.get("urgency", "low")),
                rationale=tuple(final_output.get("rationale", ())),
                prompt_template=prompt_template,
                prompt_run=prompt_run,
                usage_events=list(usage_events),
                decision_time=request.decision_time,
                available_for_decision_at=request.available_for_decision_at,
                risk_decision_id=risk_decision.risk_decision_id if risk_decision is not None else None,
                metadata_json={
                    "baseline_signal_snapshot_id": request.baseline_signal_snapshot_id,
                    "intraday_signal_snapshot_id": request.intraday_signal_snapshot_id,
                    "previous_intraday_snapshot_id": request.previous_intraday_snapshot_id,
                    "signal_freshness": dict(request.signal_freshness),
                    "delta_vs_baseline_json": dict(request.delta_vs_baseline_json),
                    "delta_vs_previous_json": dict(request.delta_vs_previous_json),
                    "resolver_version": config.resolver_version,
                },
            )
            self.repository.save_prompt_template(prompt_template)
            self.repository.save_prompt_run(prompt_run)
            self.repository.save_usage_events(usage_events)
            self.repository.save_intraday_rebalance_decision(decision)
            decisions.append(decision)

            if (
                execute_approved
                and self.broker is not None
                and risk_decision is not None
                and decision.status == "approved"
                and decision.action in {"exit", "reduce"}
            ):
                execution_decisions.append(self._to_trading_decision(request, decision, prompt_template, prompt_run, usage_events))
                execution_risk_decisions.append(risk_decision)

        if execute_approved and self.broker is not None and execution_decisions:
            PaperExecutionWorkflow(
                repository=self.repository,
                broker=self.broker,
            ).run(
                trading_decisions=tuple(execution_decisions),
                risk_decisions=tuple(execution_risk_decisions),
                trade_date=trade_date or rebalance_requests[0].decision_time,
            )

        return IntradayRebalancePipelineResult(decisions=tuple(decisions))

    def _run_agent(
        self,
        request: IntradayRebalanceRequest,
    ) -> tuple[dict[str, Any], Any, PromptRunRecord, list[UsageEventRecord], str, str]:
        payload = IntradayRebalanceInput(
            ticker=request.ticker,
            strategy_id=request.strategy_id,
            expression_bucket_id=request.expression_bucket_id,
            trade_identity=request.trade_identity,
            instrument_type=request.instrument_type,
            selection_source=request.selection_source,
            decision_time=request.decision_time,
            available_for_decision_at=request.available_for_decision_at,
            current_price=request.current_price,
            atr_pct=request.atr_pct,
            average_daily_dollar_volume=request.average_daily_dollar_volume,
            existing_position=request.existing_position,
            current_position_quantity=request.current_position_quantity,
            current_position_market_value=request.current_position_market_value,
            candidate_score=request.candidate_score,
            target_weight=request.target_weight,
            signal_freshness=request.signal_freshness,
            delta_vs_baseline_json=request.delta_vs_baseline_json,
            delta_vs_previous_json=request.delta_vs_previous_json,
            alerts=list(request.alerts),
            allow_open_new=request.allow_open_new,
            direct_company_negative_evidence=request.direct_company_negative_evidence,
            bearish_signal_sources=list(request.bearish_signal_sources),
            metadata_json=request.metadata_json,
        )
        rendered = self.prompt_registry.render(
            "intraday_rebalance",
            "v1",
            {
                "ticker": payload.ticker,
                "input_payload_json": json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            },
        )
        validation_errors: list[str] = []
        usage_events: list[UsageEventRecord] = []
        raw_output_text = ""
        parsed_output_json: dict[str, Any] = {}
        final_error: str | None = None

        for attempt in range(2):
            prompt = rendered.text if attempt == 0 else _repair_prompt(rendered.text, validation_errors[-1])
            response = self.agent_runner(prompt, self.model_name)
            raw_output_text, usage = _normalize_runner_response(response, self.model_name)
            usage_events.append(UsageEventRecord(retry_count=attempt, status="succeeded", **usage))
            try:
                parsed_output_json = _coerce_json_object(raw_output_text)
                output = IntradayRebalanceOutput.model_validate(parsed_output_json)
                prompt_run = PromptRunRecord(
                    pipeline_name="intraday_rebalance",
                    rendered_prompt_hash=rendered.rendered_prompt_hash,
                    rendered_prompt_redacted=prompt,
                    input_context_json=payload.model_dump(mode="json"),
                    raw_output_text=raw_output_text,
                    parsed_output_json=output.model_dump(mode="json"),
                    parse_status="succeeded",
                    validation_errors_json=list(validation_errors),
                    fallback_action=None,
                    error_message=None,
                )
                return output.model_dump(mode="json"), rendered.template, prompt_run, usage_events, "approved", "llm_action"
            except (ValidationError, ValueError, TypeError) as exc:
                final_error = str(exc)
                validation_errors.append(final_error)

        fallback = IntradayRebalanceOutputFallback(
            ticker=request.ticker,
            action="hold",
            fallback_reason="validation_failed_after_retry",
            schema_version="v1",
            generated_at=datetime.now(timezone.utc),
        )
        prompt_run = PromptRunRecord(
            pipeline_name="intraday_rebalance",
            rendered_prompt_hash=rendered.rendered_prompt_hash,
            rendered_prompt_redacted=_repair_prompt(rendered.text, validation_errors[-1]),
            input_context_json=payload.model_dump(mode="json"),
            raw_output_text=raw_output_text,
            parsed_output_json=fallback.model_dump(mode="json"),
            parse_status="failed",
            validation_errors_json=list(validation_errors),
            fallback_action="hold",
            error_message=final_error,
        )
        return fallback.model_dump(mode="json"), rendered.template, prompt_run, usage_events, "fallback", "classification_failed"

    def _apply_guardrails(
        self,
        *,
        request: IntradayRebalanceRequest,
        output: dict[str, Any],
        status: str,
        reason_code: str,
    ) -> tuple[dict[str, Any], str, str]:
        action = str(output["action"])
        if action == "open_new" and (not request.allow_open_new or request.existing_position):
            output["action"] = "hold"
            return output, "blocked", "open_new_disabled"
        if action in {"reduce", "exit"} and not request.existing_position:
            output["action"] = "hold"
            return output, "blocked", "no_existing_position"
        return output, status, reason_code

    def _apply_portfolio_risk_intent(
        self,
        *,
        request: IntradayRebalanceRequest,
        output: dict[str, Any],
        status: str,
        reason_code: str,
        portfolio_risk_intent: PortfolioRiskIntentRecord | None,
    ) -> tuple[dict[str, Any], str, str]:
        planner_action = _matching_planner_position_action(
            portfolio_risk_intent,
            ticker=request.ticker,
            trade_identity=request.trade_identity,
        )
        if planner_action is None:
            return output, status, reason_code
        if planner_action.action == "block_open" and not request.existing_position:
            output["action"] = "hold"
            return output, "blocked", planner_action.reason_code
        if planner_action.action in {"force_reduce", "reduce"} and request.existing_position:
            output["action"] = "reduce"
            output["target_weight"] = 0.0
            return output, "approved", planner_action.reason_code
        return output, status, reason_code

    def _to_trading_decision(
        self,
        request: IntradayRebalanceRequest,
        decision: IntradayRebalanceDecisionRecord,
        prompt_template: Any,
        prompt_run: PromptRunRecord,
        usage_events: list[UsageEventRecord],
    ) -> TradingDecisionRecord:
        return TradingDecisionRecord(
            trading_decision_id=str(uuid.uuid4()),
            candidate_score_id=None,
            trade_classification_id=None,
            risk_decision_id=decision.risk_decision_id,
            ticker=request.ticker,
            decision=decision.action,
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            expression_bucket_id=request.expression_bucket_id,
            expression_bucket_version=request.expression_bucket_version,
            trade_identity=request.trade_identity,
            instrument_type=request.instrument_type,
            selection_source=request.selection_source,
            manual_request_id=None,
            confidence=decision.confidence,
            target_weight=decision.target_weight,
            approved_weight=0.0,
            max_loss_pct=0.0,
            time_horizon="intraday",
            thesis=decision.thesis,
            invalidators=[],
            prompt_template=prompt_template,
            prompt_run=prompt_run,
            usage_events=list(usage_events),
            decision_time=request.decision_time,
            available_for_decision_at=request.available_for_decision_at,
            metadata_json={"paper_trade_authorized": True, "intraday_rebalance": True},
        )


def _repair_prompt(rendered_text: str, validation_error: str) -> str:
    return (
        f"{rendered_text.rstrip()}\n\n"
        "Previous validation error:\n"
        f"{validation_error}\n\n"
        "Return only one corrected JSON object with no markdown."
    )


def _matching_planner_position_action(
    portfolio_risk_intent: PortfolioRiskIntentRecord | None,
    *,
    ticker: str,
    trade_identity: str,
) -> PositionRiskActionRecord | None:
    if portfolio_risk_intent is None:
        return None
    matches = [
        action
        for action in portfolio_risk_intent.position_actions
        if action.ticker == ticker and action.trade_identity == trade_identity
    ]
    if not matches:
        return None
    priority = {"block_open": 0, "force_reduce": 1, "reduce": 2, "allow": 3}
    return sorted(matches, key=lambda action: priority.get(action.action, 99))[0]


def _generated_hedge_action(portfolio_risk_intent: PortfolioRiskIntentRecord | None) -> dict[str, object] | None:
    if portfolio_risk_intent is None or not portfolio_risk_intent.hedge_actions:
        return None
    action = portfolio_risk_intent.hedge_actions[0]
    return {
        "action": action.action,
        "risk_source": action.risk_source,
        "severity": action.severity,
        "target_underlier": action.target_underlier,
        "target_exposure_type": action.target_exposure_type,
        "coverage_ratio": action.coverage_ratio,
        "reason_code": action.reason_code,
        "metadata_json": dict(action.metadata_json),
    }


def _binding_constraint(portfolio_risk_intent: PortfolioRiskIntentRecord | None) -> str | None:
    if portfolio_risk_intent is None or not portfolio_risk_intent.binding_constraints:
        return None
    return portfolio_risk_intent.binding_constraints[0]


def _lookahead_risk_source(
    portfolio_risk_intent: PortfolioRiskIntentRecord | None,
    *,
    request: IntradayRebalanceRequest,
) -> str | None:
    planner_action = _matching_planner_position_action(
        portfolio_risk_intent,
        ticker=request.ticker,
        trade_identity=request.trade_identity,
    )
    if planner_action is not None:
        return planner_action.risk_source
    if portfolio_risk_intent is None or not portfolio_risk_intent.hedge_actions:
        return None
    return portfolio_risk_intent.hedge_actions[0].risk_source
