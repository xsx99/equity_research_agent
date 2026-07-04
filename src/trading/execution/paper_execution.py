"""PR06 Alpaca-backed paper stock execution workflow."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any
import uuid

from src.trading.brokers.paper_option import (
    PaperOptionBroker,
    PaperOptionOrderLeg,
    PaperOptionOrderRecord,
    PaperOptionOrderRequest,
    PaperOptionPosition,
)
from src.trading.brokers.paper_stock import PaperOrderRequest, PaperOrderRecord, PaperStockBroker
from src.trading.execution.attempts import (
    ExecutionAttemptRecord,
    REASON_BROKER_ERROR,
    REASON_BROKER_UNAVAILABLE,
    REASON_INSTRUMENT_MISMATCH,
    REASON_MISSING_CREDENTIALS,
    REASON_NOT_AUTHORIZED,
    REASON_NOT_EXECUTABLE_ACTION,
    REASON_NO_FILL,
    REASON_ORDER_REJECTED,
    REASON_RISK_MISSING,
    REASON_RISK_REJECTED,
    failed,
    skipped,
    submitted,
)
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.options.strategy import OptionStrategyDecisionRecord, OptionsStrategyLayer
from src.trading.portfolio.state import PortfolioSnapshot
from src.trading.risk import (
    OptionLegRiskInput,
    OptionRiskInput,
    OptionRiskManager,
    RiskDecisionRecord,
    TradeRiskRequest,
)
from src.trading.risk.hedges import RiskHedgeDecisionRecord
from src.trading.risk.options import OptionRiskSnapshotRecord
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.portfolio.sync import BrokerPortfolioSyncWorkflow
from src.trading.decision.pipeline import TradingDecisionRecord
from src.trading.execution.paper_execution_options import (
    _build_execution_fallback_option_risk_input,
    _build_execution_fallback_option_trade_risk_request,
    _build_execution_fallback_trade_risk_request,
    _build_option_order_request,
    _fallback_option_strategy_payload,
    _hedge_risk_decision_from_generated_action,
    _hedge_trading_decision_from_generated_action,
    _matching_open_option_position,
    _materialized_option_positions,
    _option_decision_from_trading_decision,
    _remaining_fallback_expression_bucket_ids,
    _risk_hedge_option_strategy_type,
)


@dataclass(frozen=True)
class PaperExecutionWorkflowResult:
    """Persisted artifacts produced by the PR06 stock paper broker path."""

    paper_orders: tuple[PaperOrderRecord, ...]
    paper_option_orders: tuple[PaperOptionOrderRecord, ...]
    portfolio_snapshots: tuple[PortfolioSnapshot, ...]
    execution_attempts: tuple[ExecutionAttemptRecord, ...] = ()


class PaperExecutionWorkflow:
    """Execute stock paper trades from validated PR05 decisions."""

    def __init__(
        self,
        *,
        repository: Any,
        broker: PaperStockBroker,
        option_broker: PaperOptionBroker | None = None,
        manual_request_service: ManualTickerRequestService | None = None,
        config_resolver: Any | None = None,
        position_sizer: Any | None = None,
        risk_manager: Any | None = None,
        option_risk_manager: OptionRiskManager | None = None,
    ) -> None:
        self.repository = repository
        self.broker = broker
        self.option_broker = option_broker
        self.manual_request_service = manual_request_service
        self.portfolio_sync = BrokerPortfolioSyncWorkflow(repository=repository, broker=broker)
        self.options_strategy_layer = OptionsStrategyLayer()
        self.config_resolver = config_resolver
        self.position_sizer = position_sizer
        self.risk_manager = risk_manager
        self.option_risk_manager = option_risk_manager

    def run(
        self,
        *,
        trading_decisions: tuple[TradingDecisionRecord, ...],
        risk_decisions: tuple[RiskDecisionRecord, ...],
        trade_date: datetime,
        phase: str = "preopen",
    ) -> PaperExecutionWorkflowResult:
        risk_by_id = {decision.risk_decision_id: decision for decision in risk_decisions}
        orders: list[PaperOrderRecord] = []
        option_orders: list[PaperOptionOrderRecord] = []
        snapshots: list[PortfolioSnapshot] = []
        attempts: list[ExecutionAttemptRecord] = []
        for trading_decision in trading_decisions:
            if trading_decision.instrument_type == "option":
                self._execute_option_expression_plan(
                    trading_decision=trading_decision,
                    risk_decision=risk_by_id.get(trading_decision.risk_decision_id),
                    trade_date=trade_date,
                    option_orders=option_orders,
                    orders=orders,
                    snapshots=snapshots,
                    phase=phase,
                    attempts=attempts,
                )
                continue
            self._execute_stock_decision(
                trading_decision=trading_decision,
                risk_decision=risk_by_id.get(trading_decision.risk_decision_id),
                trade_date=trade_date,
                orders=orders,
                snapshots=snapshots,
                phase=phase,
                attempts=attempts,
            )
        self._execute_generated_hedges(
            risk_decisions=risk_decisions,
            trade_date=trade_date,
            option_orders=option_orders,
            phase=phase,
            attempts=attempts,
        )
        return PaperExecutionWorkflowResult(
            paper_orders=tuple(orders),
            paper_option_orders=tuple(option_orders),
            portfolio_snapshots=tuple(snapshots),
            execution_attempts=tuple(attempts),
        )

    def _execute_generated_hedges(
        self,
        *,
        risk_decisions: tuple[RiskDecisionRecord, ...],
        trade_date: datetime,
        option_orders: list[PaperOptionOrderRecord],
        phase: str,
        attempts: list[ExecutionAttemptRecord],
    ) -> None:
        if self.option_broker is None:
            return
        seen: set[tuple[str, str, str]] = set()
        for risk_decision in risk_decisions:
            payload = risk_decision.generated_hedge_action
            if risk_decision.status not in {"approved", "reduced"} or not isinstance(payload, dict):
                continue
            key = (
                str(payload.get("action") or ""),
                str(payload.get("target_underlier") or ""),
                str(payload.get("reason_code") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            trading_decision = _hedge_trading_decision_from_generated_action(
                risk_decision=risk_decision,
                hedge_action=payload,
                trade_date=trade_date,
            )
            if trading_decision is None:
                continue
            self.repository.save_trading_decision(trading_decision)
            hedge_risk_decision = _hedge_risk_decision_from_generated_action(
                risk_decision=risk_decision,
                hedge_action=payload,
            )
            self._handle_option_decision(
                trading_decision=trading_decision,
                risk_decision=hedge_risk_decision,
                trade_date=trade_date,
                option_orders=option_orders,
                phase=phase,
                attempts=attempts,
            )

    def _execute_option_expression_plan(
        self,
        *,
        trading_decision: TradingDecisionRecord,
        risk_decision: RiskDecisionRecord | None,
        trade_date: datetime,
        option_orders: list[PaperOptionOrderRecord],
        orders: list[PaperOrderRecord],
        snapshots: list[PortfolioSnapshot],
        phase: str,
        attempts: list[ExecutionAttemptRecord],
    ) -> None:
        current_decision = trading_decision
        current_risk_decision = risk_decision
        while current_decision is not None:
            if current_decision.instrument_type == "stock":
                if current_decision.expression_bucket_id != trading_decision.expression_bucket_id:
                    current_risk_decision = self._reapprove_stock_fallback(
                        trading_decision=current_decision,
                        trade_date=trade_date,
                    ) or current_risk_decision
                current_risk_decision = self._attach_execution_risk_decision(
                    trading_decision=current_decision,
                    risk_decision=current_risk_decision,
                )
                self._execute_stock_decision(
                    trading_decision=current_decision,
                    risk_decision=current_risk_decision,
                    trade_date=trade_date,
                    orders=orders,
                    snapshots=snapshots,
                    phase=phase,
                    attempts=attempts,
                )
                return
            next_decision, next_risk_decision = self._handle_option_decision(
                trading_decision=current_decision,
                risk_decision=current_risk_decision,
                trade_date=trade_date,
                option_orders=option_orders,
                phase=phase,
                attempts=attempts,
            )
            if next_decision is not None and next_decision.expression_bucket_id != current_decision.expression_bucket_id:
                current_decision = self._persist_fallback_resolution(
                    source_decision=current_decision,
                    resolved_decision=next_decision,
                )
                current_risk_decision = next_risk_decision
                continue
            current_decision, current_risk_decision = next_decision, next_risk_decision

    def _handle_option_decision(
        self,
        *,
        trading_decision: TradingDecisionRecord,
        risk_decision: RiskDecisionRecord | None,
        trade_date: datetime,
        option_orders: list[PaperOptionOrderRecord],
        phase: str,
        attempts: list[ExecutionAttemptRecord],
    ) -> tuple[TradingDecisionRecord | None, RiskDecisionRecord | None]:
        option_decision = _option_decision_from_trading_decision(
            trading_decision=trading_decision,
            trade_date=trade_date,
        )
        if option_decision is None:
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_NOT_EXECUTABLE_ACTION,
                ),
                attempts=attempts,
            )
            return self._next_expression_decision(trading_decision), risk_decision
        self.repository.save_option_strategy_decision(option_decision)
        if option_decision.status == "rejected":
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_NOT_EXECUTABLE_ACTION,
                    detail=option_decision.rejection_reason,
                    risk_decision_id=risk_decision.risk_decision_id if risk_decision is not None else None,
                ),
                attempts=attempts,
            )
            return self._next_expression_decision(trading_decision), risk_decision
        self.repository.save_option_strategy_legs(self.options_strategy_layer.build_legs(option_decision))
        active_risk_decision = risk_decision
        if self._is_execution_fallback(trading_decision) or active_risk_decision is None:
            active_risk_decision = self._reapprove_option_fallback(
                trading_decision=trading_decision,
                option_decision=option_decision,
                trade_date=trade_date,
            )
        if self.option_broker is None:
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_BROKER_UNAVAILABLE,
                    risk_decision_id=active_risk_decision.risk_decision_id if active_risk_decision is not None else None,
                ),
                attempts=attempts,
            )
            return self._next_expression_decision(trading_decision), active_risk_decision
        if active_risk_decision is None:
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_RISK_MISSING,
                ),
                attempts=attempts,
            )
            return self._next_expression_decision(trading_decision), active_risk_decision
        if active_risk_decision.status not in {"approved", "reduced"}:
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_RISK_REJECTED,
                    risk_decision_id=active_risk_decision.risk_decision_id,
                ),
                attempts=attempts,
            )
            return self._next_expression_decision(trading_decision), active_risk_decision
        active_risk_decision = self._attach_execution_risk_decision(
            trading_decision=trading_decision,
            risk_decision=active_risk_decision,
        )
        existing_position = _matching_open_option_position(
            repository=self.repository,
            trading_decision=trading_decision,
            option_decision=option_decision,
        )
        order_request = _build_option_order_request(
            trading_decision=trading_decision,
            risk_decision=active_risk_decision,
            option_decision=option_decision,
            trade_date=trade_date,
            existing_position=existing_position,
        )
        if order_request is None:
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_NOT_EXECUTABLE_ACTION,
                    risk_decision_id=active_risk_decision.risk_decision_id,
                ),
                attempts=attempts,
            )
            return self._next_expression_decision(trading_decision), active_risk_decision
        order = self.option_broker.submit_order(order_request)
        self.repository.save_paper_option_order(order)
        if order.status == "rejected":
            rejection_reason = str(order.rejection_reason or "").strip()
            if rejection_reason == REASON_MISSING_CREDENTIALS:
                reason_code = REASON_MISSING_CREDENTIALS
                outcome_factory = failed
            elif rejection_reason == REASON_BROKER_ERROR:
                reason_code = REASON_BROKER_ERROR
                outcome_factory = failed
            else:
                reason_code = REASON_ORDER_REJECTED
                outcome_factory = skipped
            self._save_execution_attempt(
                outcome_factory(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=reason_code,
                    paper_option_order_id=order.paper_option_order_id,
                    risk_decision_id=active_risk_decision.risk_decision_id,
                    detail=order.rejection_reason,
                ),
                attempts=attempts,
            )
            return self._next_expression_decision(trading_decision), active_risk_decision
        option_orders.append(order)
        execution = self.option_broker.find_execution_by_order_id(order.paper_option_order_id)
        if execution is None:
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_NO_FILL,
                    risk_decision_id=active_risk_decision.risk_decision_id,
                ),
                attempts=attempts,
            )
            return self._next_expression_decision(trading_decision), active_risk_decision
        if execution is not None and not self.repository.has_paper_option_execution(execution.paper_option_execution_id):
            self.repository.save_paper_option_execution(execution)
            for position in _materialized_option_positions(
                trading_decision=trading_decision,
                option_decision=option_decision,
                order_request=order_request,
                order=order,
                execution=execution,
                existing_position=existing_position,
            ):
                self.repository.save_paper_option_position(position)
            hedge_payload = (
                dict(trading_decision.metadata_json.get("generated_hedge_action") or {})
                if trading_decision.trade_identity == "risk_hedge_overlay"
                else None
            )
            self.repository.save_option_risk_snapshot(
                OptionRiskSnapshotRecord.create(
                    ticker=option_decision.ticker,
                    trade_identity=option_decision.trade_identity,
                    option_strategy_type=option_decision.option_strategy_type,
                    underlying_price=option_decision.underlying_price,
                    portfolio_delta=option_decision.portfolio_delta,
                    portfolio_gamma=option_decision.portfolio_gamma,
                    portfolio_theta=option_decision.portfolio_theta,
                    portfolio_vega=option_decision.portfolio_vega,
                    net_debit_or_credit=option_decision.net_debit_or_credit,
                    max_loss=option_decision.max_loss,
                    max_profit=option_decision.max_profit,
                    margin_requirement=option_decision.margin_requirement,
                    buying_power_effect=option_decision.buying_power_effect,
                    assignment_notional=option_decision.assignment_notional,
                    worst_case_assignment_notional=option_decision.assignment_notional,
                    margin_model_profile=option_decision.margin_model_profile,
                    margin_model_version=option_decision.margin_model_version,
                    margin_requirement_source=option_decision.margin_requirement_source,
                    risk_status="approved",
                    reason_code="within_limits",
                    created_at=execution.executed_at,
                    metadata_json=option_decision.metadata_json,
                )
            )
            if trading_decision.trade_identity == "risk_hedge_overlay":
                self.repository.save_risk_hedge_decision(
                    RiskHedgeDecisionRecord.create(
                        risk_decision_id=active_risk_decision.risk_decision_id,
                        ticker=trading_decision.ticker,
                        action=trading_decision.decision,
                        option_strategy_type=_risk_hedge_option_strategy_type(
                            trading_decision=trading_decision,
                            option_decision=option_decision,
                            existing_position=existing_position,
                        ),
                        rationale="risk_manager_generated_overlay",
                        hedge_cost=abs(execution.net_cash_effect),
                        protected_notional=max(
                            float((hedge_payload or {}).get("protected_notional") or 0.0),
                            option_decision.assignment_notional,
                            option_decision.buying_power_effect,
                        ),
                        metadata_json={
                            **dict(option_decision.metadata_json),
                            **({"generated_hedge_action": hedge_payload} if hedge_payload is not None else {}),
                        },
                    )
                )
        self._save_execution_attempt(
            submitted(
                trading_decision=trading_decision,
                phase=phase,
                paper_option_order_id=order.paper_option_order_id,
                risk_decision_id=active_risk_decision.risk_decision_id,
            ),
            attempts=attempts,
        )
        return None, None

    def _execute_stock_decision(
        self,
        *,
        trading_decision: TradingDecisionRecord,
        risk_decision: RiskDecisionRecord | None,
        trade_date: datetime,
        orders: list[PaperOrderRecord],
        snapshots: list[PortfolioSnapshot],
        phase: str,
        attempts: list[ExecutionAttemptRecord],
    ) -> None:
        if trading_decision.instrument_type != "stock":
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_INSTRUMENT_MISMATCH,
                ),
                attempts=attempts,
            )
            return
        if trading_decision.decision not in {"enter_long", "reduce", "exit", "enter_short"}:
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_NOT_EXECUTABLE_ACTION,
                ),
                attempts=attempts,
            )
            return
        if not bool(trading_decision.paper_trade_authorized) and trading_decision.manual_request_id is None:
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_NOT_AUTHORIZED,
                ),
                attempts=attempts,
            )
            return
        if risk_decision is None:
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_RISK_MISSING,
                ),
                attempts=attempts,
            )
            return
        if risk_decision.status not in {"approved", "reduced"}:
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_RISK_REJECTED,
                    risk_decision_id=risk_decision.risk_decision_id,
                ),
                attempts=attempts,
            )
            return
        manual_request_mode = self._manual_request_mode(
            trading_decision.manual_request_id,
            fallback_mode=trading_decision.metadata_json.get("manual_request_mode"),
        )
        order = self.broker.submit_order(
            PaperOrderRequest.from_trading_decision(
                trading_decision=trading_decision,
                risk_decision=risk_decision,
                trade_date=trade_date.date(),
                manual_request_mode=manual_request_mode,
            )
        )
        self.repository.save_paper_order(order)
        orders.append(order)
        execution = self.broker.find_execution_by_order_id(order.paper_order_id)
        if execution is None:
            self._save_execution_attempt(
                skipped(
                    trading_decision=trading_decision,
                    phase=phase,
                    reason_code=REASON_NO_FILL,
                    risk_decision_id=risk_decision.risk_decision_id,
                ),
                attempts=attempts,
            )
            return
        if self.repository.has_paper_execution(execution.paper_execution_id):
            self._save_execution_attempt(
                submitted(
                    trading_decision=trading_decision,
                    phase=phase,
                    paper_order_id=order.paper_order_id,
                    risk_decision_id=risk_decision.risk_decision_id,
                ),
                attempts=attempts,
            )
            return
        self.repository.save_paper_execution(execution)
        sync_result = self.portfolio_sync.run(
            as_of=execution.executed_at,
            extra_position_metadata={
                trading_decision.ticker: {
                    "strategy_id": trading_decision.strategy_id,
                    "trade_identity": trading_decision.trade_identity,
                }
            },
        )
        snapshots.append(sync_result.snapshot)
        self._save_execution_attempt(
            submitted(
                trading_decision=trading_decision,
                phase=phase,
                paper_order_id=order.paper_order_id,
                risk_decision_id=risk_decision.risk_decision_id,
            ),
            attempts=attempts,
        )

    def _save_execution_attempt(
        self,
        attempt: ExecutionAttemptRecord,
        *,
        attempts: list[ExecutionAttemptRecord],
    ) -> None:
        self.repository.save_execution_attempt(attempt)
        attempts.append(attempt)

    def _next_expression_decision(
        self,
        trading_decision: TradingDecisionRecord,
    ) -> TradingDecisionRecord | None:
        classification_context = dict(trading_decision.context_snapshot_json.get("classification_context") or {})
        current_expression_id = str(trading_decision.expression_bucket_id)
        matched_current = False
        for plan in classification_context.get("expression_fallback_plan") or []:
            expression_bucket_id = str(plan.get("expression_bucket_id") or current_expression_id)
            if not matched_current:
                if expression_bucket_id == current_expression_id:
                    matched_current = True
                continue
            decision_action = str(plan.get("decision_action") or "").strip()
            instrument_type = str(plan.get("instrument_type") or "").strip()
            if instrument_type == "stock" and decision_action not in {"enter_long", "reduce", "exit", "enter_short"}:
                continue
            if instrument_type == "option" and decision_action not in {"open_option_strategy", "close_option_strategy", "roll_option_strategy", "adjust_option_strategy"}:
                continue
            if instrument_type not in {"stock", "option"}:
                continue
            metadata_json = dict(trading_decision.metadata_json)
            metadata_json["execution_fallback_from_expression_bucket_id"] = trading_decision.expression_bucket_id
            metadata_json["execution_fallback_to_expression_bucket_id"] = expression_bucket_id
            if instrument_type == "option":
                option_strategy_payload = _fallback_option_strategy_payload(
                    trading_decision,
                    expression_bucket_id=expression_bucket_id,
                )
                if not isinstance(option_strategy_payload, dict):
                    continue
                metadata_json["option_strategy"] = option_strategy_payload
            return TradingDecisionRecord(
                trading_decision_id=trading_decision.trading_decision_id,
                candidate_score_id=trading_decision.candidate_score_id,
                trade_classification_id=trading_decision.trade_classification_id,
                risk_decision_id=trading_decision.risk_decision_id,
                ticker=trading_decision.ticker,
                decision=decision_action,
                strategy_id=trading_decision.strategy_id,
                strategy_version=trading_decision.strategy_version,
                expression_bucket_id=expression_bucket_id,
                expression_bucket_version=str(plan.get("expression_bucket_version") or trading_decision.expression_bucket_version),
                trade_identity=str(plan.get("trade_identity") or trading_decision.trade_identity),
                instrument_type=instrument_type,
                selection_source=trading_decision.selection_source,
                manual_request_id=trading_decision.manual_request_id,
                confidence=trading_decision.confidence,
                target_weight=trading_decision.target_weight,
                approved_weight=trading_decision.approved_weight,
                max_loss_pct=trading_decision.max_loss_pct,
                time_horizon=trading_decision.time_horizon,
                thesis=trading_decision.thesis,
                prompt_template=trading_decision.prompt_template,
                prompt_run=trading_decision.prompt_run,
                usage_events=trading_decision.usage_events,
                decision_time=trading_decision.decision_time,
                available_for_decision_at=trading_decision.available_for_decision_at,
                paper_trade_authorized=trading_decision.paper_trade_authorized,
                key_drivers=list(trading_decision.key_drivers),
                counterarguments=list(trading_decision.counterarguments),
                invalidators=list(trading_decision.invalidators),
                context_snapshot_json=dict(trading_decision.context_snapshot_json),
                metadata_json=metadata_json,
            )
        return None

    def _reapprove_stock_fallback(
        self,
        *,
        trading_decision: TradingDecisionRecord,
        trade_date: datetime,
    ) -> RiskDecisionRecord | None:
        if self.config_resolver is None or self.position_sizer is None or self.risk_manager is None:
            return None
        portfolio_sync = self.portfolio_sync.run(as_of=trade_date, persist=False)
        portfolio_context = portfolio_sync.portfolio_context
        config = self.config_resolver.resolve(
            risk_appetite="balanced",
            portfolio_context=portfolio_context,
            macro_risk_budget_multiplier=1.0,
        )
        request = _build_execution_fallback_trade_risk_request(trading_decision)
        sizing = self.position_sizer.size_position(request, portfolio_context, config)
        decision = self.risk_manager.evaluate(request, sizing, portfolio_context, config)
        self.repository.save_position_sizing_decision(sizing)
        self.repository.save_risk_decision(decision)
        return decision

    def _reapprove_option_fallback(
        self,
        *,
        trading_decision: TradingDecisionRecord,
        option_decision: OptionStrategyDecisionRecord,
        trade_date: datetime,
    ) -> RiskDecisionRecord | None:
        if self.config_resolver is None or self.position_sizer is None or self.risk_manager is None:
            return None
        portfolio_sync = self.portfolio_sync.run(as_of=trade_date, persist=False)
        portfolio_context = portfolio_sync.portfolio_context
        config = self.config_resolver.resolve(
            risk_appetite="balanced",
            portfolio_context=portfolio_context,
            macro_risk_budget_multiplier=1.0,
        )
        request = _build_execution_fallback_option_trade_risk_request(trading_decision)
        sizing = self.position_sizer.size_position(request, portfolio_context, config)
        decision = self.risk_manager.evaluate(request, sizing, portfolio_context, config)
        self.repository.save_position_sizing_decision(sizing)
        self.repository.save_risk_decision(decision)
        if decision.status not in {"approved", "reduced"} or self.option_risk_manager is None:
            return decision
        contracts = max(1, int(round(decision.approved_quantity or 1)))
        option_risk = _build_execution_fallback_option_risk_input(option_decision, contracts=contracts)
        assessment = self.option_risk_manager.evaluate_assignment_risk(
            option_risk,
            portfolio_context=portfolio_context,
            config=config,
        )
        if assessment.status == "approved":
            return decision
        self.repository.save_option_risk_snapshot(
            OptionRiskSnapshotRecord.create(
                ticker=option_decision.ticker,
                trade_identity=option_decision.trade_identity,
                option_strategy_type=option_decision.option_strategy_type,
                underlying_price=option_decision.underlying_price,
                portfolio_delta=assessment.portfolio_delta,
                portfolio_gamma=assessment.portfolio_gamma,
                portfolio_theta=assessment.portfolio_theta,
                portfolio_vega=assessment.portfolio_vega,
                net_debit_or_credit=option_decision.net_debit_or_credit,
                max_loss=option_decision.max_loss,
                max_profit=option_decision.max_profit,
                margin_requirement=option_risk.margin_requirement,
                buying_power_effect=option_risk.buying_power_effect,
                assignment_notional=option_decision.assignment_notional * contracts,
                worst_case_assignment_notional=assessment.worst_case_assignment_notional,
                margin_model_profile=option_decision.margin_model_profile,
                margin_model_version=option_decision.margin_model_version,
                margin_requirement_source=option_decision.margin_requirement_source,
                risk_status=assessment.status,
                reason_code=assessment.reason_code,
                created_at=trade_date,
                metadata_json=option_decision.metadata_json,
            )
        )
        assignment_rejection = RiskDecisionRecord.create(
            candidate_score_id=decision.candidate_score_id,
            trade_classification_id=decision.trade_classification_id,
            position_sizing_decision_id=decision.position_sizing_decision_id,
            ticker=decision.ticker,
            status="rejected",
            reason_code=assessment.reason_code,
            approved_weight=0.0,
            approved_notional=0.0,
            approved_quantity=0.0,
            portfolio_risk_snapshot_id=decision.portfolio_risk_snapshot_id,
            applied_rules=[*decision.applied_rules, "option_assignment_risk_check"],
            decision_time=decision.decision_time,
            metadata_json={"superseded_risk_decision_id": decision.risk_decision_id},
        )
        self.repository.save_risk_decision(assignment_rejection)
        return assignment_rejection

    def _is_execution_fallback(self, trading_decision: TradingDecisionRecord) -> bool:
        metadata_json = trading_decision.metadata_json
        return bool(
            metadata_json.get("execution_fallback_from_expression_bucket_id")
            and metadata_json.get("execution_fallback_to_expression_bucket_id")
        )

    def _persist_fallback_resolution(
        self,
        *,
        source_decision: TradingDecisionRecord,
        resolved_decision: TradingDecisionRecord,
    ) -> TradingDecisionRecord:
        source_classification = getattr(self.repository, "load_trade_classification", lambda _id: None)(
            source_decision.trade_classification_id
        )
        selected_strategy_context = dict(
            (source_classification.selected_strategy_context_json if source_classification is not None else {})
            or source_decision.context_snapshot_json.get("classification_context", {}).get("selected_strategy_context")
            or {}
        )
        selected_strategy_context["selected_expression_bucket_id"] = resolved_decision.expression_bucket_id
        selected_strategy_context["fallback_expression_bucket_ids"] = _remaining_fallback_expression_bucket_ids(
            resolved_decision
        )
        selected_strategy_context["execution_resolved_from_expression_bucket_id"] = source_decision.expression_bucket_id
        strategy_run_id = (
            source_classification.strategy_run_id
            if source_classification is not None
            else str(
                source_decision.context_snapshot_json.get("candidate_context", {}).get("strategy_run_id")
                or "00000000-0000-0000-0000-000000000000"
            )
        )
        classification = TradeClassificationRecord(
            trade_classification_id=str(uuid.uuid4()),
            candidate_score_id=str(
                (source_classification.candidate_score_id if source_classification is not None else source_decision.candidate_score_id)
                or "00000000-0000-0000-0000-000000000000"
            ),
            strategy_run_id=strategy_run_id,
            ticker=resolved_decision.ticker,
            selected_strategy_id=resolved_decision.strategy_id,
            selected_strategy_version=resolved_decision.strategy_version,
            expression_bucket_id=resolved_decision.expression_bucket_id,
            expression_bucket_version=resolved_decision.expression_bucket_version,
            trade_identity=resolved_decision.trade_identity,
            watch_type=None,
            direction=str(
                (source_classification.direction if source_classification is not None else source_decision.context_snapshot_json.get("candidate_context", {}).get("direction"))
                or "bullish"
            ),
            intended_horizon=str(
                (source_classification.intended_horizon if source_classification is not None else resolved_decision.time_horizon)
                or resolved_decision.time_horizon
            ),
            exit_policy=str(
                (source_classification.exit_policy if source_classification is not None else selected_strategy_context.get("default_exit_policy"))
                or resolved_decision.metadata_json.get("selected_strategy_context", {}).get("default_exit_policy")
                or "strategy_invalidators_or_target_horizon"
            ),
            result_status="actionable_trade",
            classification_reason="resolved_expression_fallback",
            selected_strategy_context_json=selected_strategy_context,
            decision_time=resolved_decision.decision_time,
        )
        self.repository.save_trade_classifications((classification,))
        context_snapshot_json = dict(resolved_decision.context_snapshot_json)
        classification_context = dict(context_snapshot_json.get("classification_context") or {})
        classification_context["trade_identity"] = resolved_decision.trade_identity
        classification_context["expression_bucket_id"] = resolved_decision.expression_bucket_id
        classification_context["instrument_type"] = resolved_decision.instrument_type
        classification_context["selected_strategy_context"] = selected_strategy_context
        context_snapshot_json["classification_context"] = classification_context
        metadata_json = dict(resolved_decision.metadata_json)
        metadata_json["execution_resolved_from_trading_decision_id"] = source_decision.trading_decision_id
        metadata_json["execution_resolved_from_trade_classification_id"] = source_decision.trade_classification_id
        metadata_json["execution_resolved_from_expression_bucket_id"] = source_decision.expression_bucket_id
        persisted = TradingDecisionRecord(
            trading_decision_id=str(uuid.uuid4()),
            candidate_score_id=resolved_decision.candidate_score_id,
            trade_classification_id=classification.trade_classification_id,
            risk_decision_id=None,
            ticker=resolved_decision.ticker,
            decision=resolved_decision.decision,
            strategy_id=resolved_decision.strategy_id,
            strategy_version=resolved_decision.strategy_version,
            expression_bucket_id=resolved_decision.expression_bucket_id,
            expression_bucket_version=resolved_decision.expression_bucket_version,
            trade_identity=resolved_decision.trade_identity,
            instrument_type=resolved_decision.instrument_type,
            selection_source=resolved_decision.selection_source,
            manual_request_id=resolved_decision.manual_request_id,
            confidence=resolved_decision.confidence,
            target_weight=resolved_decision.target_weight,
            approved_weight=resolved_decision.approved_weight,
            max_loss_pct=resolved_decision.max_loss_pct,
            time_horizon=resolved_decision.time_horizon,
            thesis=resolved_decision.thesis,
            prompt_template=resolved_decision.prompt_template,
            prompt_run=resolved_decision.prompt_run,
            usage_events=resolved_decision.usage_events,
            decision_time=resolved_decision.decision_time,
            available_for_decision_at=resolved_decision.available_for_decision_at,
            paper_trade_authorized=resolved_decision.paper_trade_authorized,
            key_drivers=list(resolved_decision.key_drivers),
            counterarguments=list(resolved_decision.counterarguments),
            invalidators=list(resolved_decision.invalidators),
            context_snapshot_json=context_snapshot_json,
            metadata_json=metadata_json,
        )
        self.repository.save_trading_decision(persisted)
        return persisted

    def _attach_execution_risk_decision(
        self,
        *,
        trading_decision: TradingDecisionRecord,
        risk_decision: RiskDecisionRecord | None,
    ) -> RiskDecisionRecord | None:
        if risk_decision is None:
            return None
        aligned = risk_decision
        if aligned.trade_classification_id != trading_decision.trade_classification_id:
            aligned = RiskDecisionRecord(
                risk_decision_id=str(uuid.uuid4()),
                candidate_score_id=aligned.candidate_score_id,
                trade_classification_id=trading_decision.trade_classification_id,
                position_sizing_decision_id=aligned.position_sizing_decision_id,
                ticker=aligned.ticker,
                status=aligned.status,
                reason_code=aligned.reason_code,
                approved_weight=aligned.approved_weight,
                approved_notional=aligned.approved_notional,
                approved_quantity=aligned.approved_quantity,
                portfolio_risk_snapshot_id=aligned.portfolio_risk_snapshot_id,
                applied_rules=list(aligned.applied_rules),
                generated_hedge_action=aligned.generated_hedge_action,
                decision_time=aligned.decision_time,
                metadata_json={
                    **dict(aligned.metadata_json),
                    "reused_original_risk_decision_id": aligned.risk_decision_id,
                },
            )
            self.repository.save_risk_decision(aligned)
        updated_decision = TradingDecisionRecord(
            trading_decision_id=trading_decision.trading_decision_id,
            candidate_score_id=trading_decision.candidate_score_id,
            trade_classification_id=trading_decision.trade_classification_id,
            risk_decision_id=aligned.risk_decision_id,
            ticker=trading_decision.ticker,
            decision=trading_decision.decision,
            strategy_id=trading_decision.strategy_id,
            strategy_version=trading_decision.strategy_version,
            expression_bucket_id=trading_decision.expression_bucket_id,
            expression_bucket_version=trading_decision.expression_bucket_version,
            trade_identity=trading_decision.trade_identity,
            instrument_type=trading_decision.instrument_type,
            selection_source=trading_decision.selection_source,
            manual_request_id=trading_decision.manual_request_id,
            confidence=trading_decision.confidence,
            target_weight=trading_decision.target_weight,
            approved_weight=trading_decision.approved_weight,
            max_loss_pct=trading_decision.max_loss_pct,
            time_horizon=trading_decision.time_horizon,
            thesis=trading_decision.thesis,
            prompt_template=trading_decision.prompt_template,
            prompt_run=trading_decision.prompt_run,
            usage_events=trading_decision.usage_events,
            decision_time=trading_decision.decision_time,
            available_for_decision_at=trading_decision.available_for_decision_at,
            paper_trade_authorized=trading_decision.paper_trade_authorized,
            key_drivers=list(trading_decision.key_drivers),
            counterarguments=list(trading_decision.counterarguments),
            invalidators=list(trading_decision.invalidators),
            context_snapshot_json=dict(trading_decision.context_snapshot_json),
            metadata_json=dict(trading_decision.metadata_json),
        )
        self.repository.save_trading_decision(updated_decision)
        return aligned

    def _manual_request_mode(self, request_id: str | None, *, fallback_mode: str | None = None) -> str | None:
        if request_id is None:
            return fallback_mode
        if self.manual_request_service is None:
            return fallback_mode
        for request in self.manual_request_service.load_active():
            if request.request_id == request_id:
                return request.mode
        return fallback_mode
