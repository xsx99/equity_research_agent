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
from src.trading.workflows.portfolio_sync import BrokerPortfolioSyncWorkflow
from src.trading.workflows.trading_decision import TradingDecisionRecord


@dataclass(frozen=True)
class PaperExecutionWorkflowResult:
    """Persisted artifacts produced by the PR06 stock paper broker path."""

    paper_orders: tuple[PaperOrderRecord, ...]
    paper_option_orders: tuple[PaperOptionOrderRecord, ...]
    portfolio_snapshots: tuple[PortfolioSnapshot, ...]


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
    ) -> PaperExecutionWorkflowResult:
        risk_by_id = {decision.risk_decision_id: decision for decision in risk_decisions}
        orders: list[PaperOrderRecord] = []
        option_orders: list[PaperOptionOrderRecord] = []
        snapshots: list[PortfolioSnapshot] = []
        for trading_decision in trading_decisions:
            if trading_decision.instrument_type == "option":
                self._execute_option_expression_plan(
                    trading_decision=trading_decision,
                    risk_decision=risk_by_id.get(trading_decision.risk_decision_id),
                    trade_date=trade_date,
                    option_orders=option_orders,
                    orders=orders,
                    snapshots=snapshots,
                )
                continue
            self._execute_stock_decision(
                trading_decision=trading_decision,
                risk_decision=risk_by_id.get(trading_decision.risk_decision_id),
                trade_date=trade_date,
                orders=orders,
                snapshots=snapshots,
            )
        self._execute_generated_hedges(
            risk_decisions=risk_decisions,
            trade_date=trade_date,
            option_orders=option_orders,
        )
        return PaperExecutionWorkflowResult(
            paper_orders=tuple(orders),
            paper_option_orders=tuple(option_orders),
            portfolio_snapshots=tuple(snapshots),
        )

    def _execute_generated_hedges(
        self,
        *,
        risk_decisions: tuple[RiskDecisionRecord, ...],
        trade_date: datetime,
        option_orders: list[PaperOptionOrderRecord],
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
                )
                return
            next_decision, next_risk_decision = self._handle_option_decision(
                trading_decision=current_decision,
                risk_decision=current_risk_decision,
                trade_date=trade_date,
                option_orders=option_orders,
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
    ) -> tuple[TradingDecisionRecord | None, RiskDecisionRecord | None]:
        option_decision = _option_decision_from_trading_decision(
            trading_decision=trading_decision,
            trade_date=trade_date,
        )
        if option_decision is None:
            return self._next_expression_decision(trading_decision), risk_decision
        self.repository.save_option_strategy_decision(option_decision)
        if option_decision.status == "rejected":
            return self._next_expression_decision(trading_decision), risk_decision
        self.repository.save_option_strategy_legs(self.options_strategy_layer.build_legs(option_decision))
        active_risk_decision = risk_decision
        if self._is_execution_fallback(trading_decision) or active_risk_decision is None:
            active_risk_decision = self._reapprove_option_fallback(
                trading_decision=trading_decision,
                option_decision=option_decision,
                trade_date=trade_date,
            )
        if self.option_broker is None or active_risk_decision is None:
            return self._next_expression_decision(trading_decision), active_risk_decision
        if active_risk_decision.status not in {"approved", "reduced"}:
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
            return self._next_expression_decision(trading_decision), active_risk_decision
        order = self.option_broker.submit_order(order_request)
        self.repository.save_paper_option_order(order)
        option_orders.append(order)
        if order.status == "rejected":
            return self._next_expression_decision(trading_decision), active_risk_decision
        execution = self.option_broker.find_execution_by_order_id(order.paper_option_order_id)
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
        return None, None

    def _execute_stock_decision(
        self,
        *,
        trading_decision: TradingDecisionRecord,
        risk_decision: RiskDecisionRecord | None,
        trade_date: datetime,
        orders: list[PaperOrderRecord],
        snapshots: list[PortfolioSnapshot],
    ) -> None:
        if trading_decision.instrument_type != "stock":
            return
        if trading_decision.decision not in {"enter_long", "reduce", "exit", "enter_short"}:
            return
        if not bool(trading_decision.metadata_json.get("paper_trade_authorized", False)) and trading_decision.manual_request_id is None:
            return
        if risk_decision is None:
            return
        if risk_decision.status not in {"approved", "reduced"}:
            return
        manual_request_mode = self._manual_request_mode(trading_decision.manual_request_id)
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
            return
        if self.repository.has_paper_execution(execution.paper_execution_id):
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
            key_drivers=list(trading_decision.key_drivers),
            counterarguments=list(trading_decision.counterarguments),
            invalidators=list(trading_decision.invalidators),
            context_snapshot_json=dict(trading_decision.context_snapshot_json),
            metadata_json=dict(trading_decision.metadata_json),
        )
        self.repository.save_trading_decision(updated_decision)
        return aligned

    def _manual_request_mode(self, request_id: str | None) -> str | None:
        if request_id is None or self.manual_request_service is None:
            return None
        for request in self.manual_request_service.load_active():
            if request.request_id == request_id:
                return request.mode
        return None


def _hedge_trading_decision_from_generated_action(
    *,
    risk_decision: RiskDecisionRecord,
    hedge_action: dict[str, Any],
    trade_date: datetime,
) -> TradingDecisionRecord | None:
    decision_action = _hedge_decision_action(hedge_action)
    if decision_action is None:
        return None
    ticker = str(hedge_action.get("target_underlier") or "").strip().upper()
    if not ticker:
        return None
    option_strategy_payload = _generated_hedge_option_strategy_payload(
        hedge_action=hedge_action,
        trade_date=trade_date,
    )
    metadata_json = {
        "paper_trade_authorized": True,
        "generated_hedge_action": dict(hedge_action),
        "option_strategy": option_strategy_payload,
    }
    return TradingDecisionRecord(
        trading_decision_id=str(uuid.uuid4()),
        candidate_score_id=risk_decision.candidate_score_id,
        trade_classification_id=None,
        risk_decision_id=risk_decision.risk_decision_id,
        ticker=ticker,
        decision=decision_action,
        strategy_id="risk_manager_hedge_overlay_v1",
        strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="risk_hedge_overlay",
        instrument_type="option",
        selection_source="risk_manager",
        manual_request_id=None,
        confidence=1.0,
        target_weight=0.0,
        approved_weight=0.0,
        max_loss_pct=1.0,
        time_horizon="1d-5d",
        thesis="Risk hedge overlay generated from residual portfolio risk.",
        prompt_template=object(),
        prompt_run=None,
        usage_events=[],
        decision_time=trade_date,
        available_for_decision_at=trade_date,
        key_drivers=[str(hedge_action.get("reason_code") or "risk_overlay")],
        counterarguments=[],
        invalidators=[],
        context_snapshot_json={
            "generated_by": "risk_manager",
            "source_risk_decision_id": risk_decision.risk_decision_id,
        },
        metadata_json=metadata_json,
    )


def _hedge_risk_decision_from_generated_action(
    *,
    risk_decision: RiskDecisionRecord,
    hedge_action: dict[str, Any],
) -> RiskDecisionRecord:
    underlying_price = max(float(hedge_action.get("underlying_price") or 100.0), 1.0)
    protected_notional = max(float(hedge_action.get("protected_notional") or 0.0), underlying_price * 100.0)
    contracts = max(1.0, round(protected_notional / (underlying_price * 100.0)))
    return RiskDecisionRecord(
        risk_decision_id=risk_decision.risk_decision_id,
        candidate_score_id=risk_decision.candidate_score_id,
        trade_classification_id=None,
        position_sizing_decision_id=risk_decision.position_sizing_decision_id,
        ticker=str(hedge_action.get("target_underlier") or risk_decision.ticker),
        status=risk_decision.status,
        reason_code=str(hedge_action.get("reason_code") or risk_decision.reason_code),
        approved_weight=0.0,
        approved_notional=protected_notional,
        approved_quantity=contracts,
        portfolio_risk_snapshot_id=risk_decision.portfolio_risk_snapshot_id,
        applied_rules=[*list(risk_decision.applied_rules), "generated_risk_hedge_overlay"],
        generated_hedge_action=dict(hedge_action),
        decision_time=risk_decision.decision_time,
        metadata_json=dict(risk_decision.metadata_json),
    )


def _hedge_decision_action(hedge_action: dict[str, Any]) -> str | None:
    action = str(hedge_action.get("action") or "")
    return {
        "open_hedge": "open_option_strategy",
        "close_hedge": "close_option_strategy",
        "adjust_hedge": "adjust_option_strategy",
    }.get(action)


def _generated_hedge_option_strategy_payload(
    *,
    hedge_action: dict[str, Any],
    trade_date: datetime,
) -> dict[str, Any]:
    option_strategy_type = str(hedge_action.get("option_strategy_type") or "long_put")
    underlying_price = max(float(hedge_action.get("underlying_price") or 100.0), 1.0)
    chosen_price = round(max(1.0, underlying_price * 0.02), 2)
    if option_strategy_type == "long_call":
        option_type = "call"
        delta = 0.30
    else:
        option_type = "put"
        delta = -0.30
    strike = round(underlying_price * 0.95, 2) if option_type == "put" else round(underlying_price * 1.05, 2)
    leg_payload = {
        "option_type": option_type,
        "side": "buy",
        "quantity": 1,
        "strike": strike,
        "expiry": trade_date.date().isoformat(),
        "dte": 5,
        "delta": delta,
        "gamma": 0.02,
        "theta": -0.01,
        "vega": 0.05,
        "iv_rank": None,
        "bid": round(chosen_price * 0.95, 2),
        "ask": round(chosen_price * 1.05, 2),
        "mid": chosen_price,
        "chosen_price": chosen_price,
        "implied_volatility": None,
    }
    max_loss = chosen_price * 100.0
    return {
        "option_strategy_decision_id": str(uuid.uuid4()),
        "option_strategy_type": option_strategy_type,
        "status": "ready",
        "rejection_reason": None,
        "underlying_price": underlying_price,
        "net_debit_or_credit": chosen_price,
        "max_loss": max_loss,
        "max_profit": None,
        "breakevens": (),
        "margin_requirement": max_loss,
        "buying_power_effect": max_loss,
        "assignment_notional": 0.0,
        "portfolio_delta": delta,
        "portfolio_gamma": 0.02,
        "portfolio_theta": -0.01,
        "portfolio_vega": 0.05,
        "event_through_expiry": False,
        "strategy_pairing_method": "single_leg",
        "assignment_plan": None,
        "margin_model_profile": "estimated_fidelity_like_conservative_v1",
        "margin_model_version": "v1",
        "margin_requirement_source": "simulated_formula",
        "profit_target_pct": 0.0,
        "max_loss_rule": "",
        "roll_conditions": (),
        "close_conditions": (),
        "metadata_json": {"legs": [leg_payload], "hedge_action": dict(hedge_action)},
    }


def _matching_open_option_position(
    *,
    repository: Any,
    trading_decision: TradingDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
) -> PaperOptionPosition | None:
    positions = getattr(repository, "load_paper_option_positions", lambda: ())()
    hedge_overlay_fallback: PaperOptionPosition | None = None
    for position in positions:
        if position.status != "open":
            continue
        if position.ticker != trading_decision.ticker:
            continue
        if position.trade_identity != trading_decision.trade_identity:
            continue
        if position.strategy_id != trading_decision.strategy_id:
            continue
        if (
            trading_decision.trade_identity == "risk_hedge_overlay"
            and trading_decision.strategy_id == "risk_manager_hedge_overlay_v1"
            and hedge_overlay_fallback is None
        ):
            hedge_overlay_fallback = position
        if position.option_strategy_type != option_decision.option_strategy_type:
            continue
        return position
    return hedge_overlay_fallback


def _build_option_order_request(
    *,
    trading_decision: TradingDecisionRecord,
    risk_decision: RiskDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
    trade_date: datetime,
    existing_position: PaperOptionPosition | None,
) -> PaperOptionOrderRequest | None:
    quantity = max(1, int(round(risk_decision.approved_quantity or 1)))
    open_legs = _paper_option_order_legs_from_decision(option_decision, action=trading_decision.decision)
    close_legs = _paper_option_close_legs_from_position(
        existing_position=existing_position,
        option_decision=option_decision,
    )
    action = trading_decision.decision
    if action == "open_option_strategy":
        return _open_option_order_request(
            trading_decision=trading_decision,
            risk_decision=risk_decision,
            option_decision=option_decision,
            trade_date=trade_date,
            quantity=quantity,
            legs=open_legs,
        )
    if action == "close_option_strategy":
        return _close_option_order_request(
            trading_decision=trading_decision,
            risk_decision=risk_decision,
            option_decision=option_decision,
            trade_date=trade_date,
            quantity=quantity,
            close_legs=close_legs,
        )
    if action in {"roll_option_strategy", "adjust_option_strategy"}:
        if not close_legs or not open_legs:
            return None
        return PaperOptionOrderRequest(
            trading_decision_id=trading_decision.trading_decision_id,
            risk_decision_id=risk_decision.risk_decision_id,
            option_strategy_decision_id=option_decision.option_strategy_decision_id,
            ticker=trading_decision.ticker,
            strategy_id=trading_decision.strategy_id,
            option_strategy_type=option_decision.option_strategy_type,
            action=action,
            trade_date=trade_date.date(),
            quantity=quantity,
            limit_price=option_decision.net_debit_or_credit,
            max_loss=option_decision.max_loss,
            margin_requirement=option_decision.margin_requirement,
            buying_power_effect=option_decision.buying_power_effect,
            trade_identity=trading_decision.trade_identity,
            order_class="mleg",
            legs=tuple([*close_legs, *open_legs]),
        )
    return PaperOptionOrderRequest(
        trading_decision_id=trading_decision.trading_decision_id,
        risk_decision_id=risk_decision.risk_decision_id,
        option_strategy_decision_id=option_decision.option_strategy_decision_id,
        ticker=trading_decision.ticker,
        strategy_id=trading_decision.strategy_id,
        option_strategy_type=option_decision.option_strategy_type,
        action=action,
        trade_date=trade_date.date(),
        quantity=quantity,
        limit_price=option_decision.net_debit_or_credit,
        max_loss=option_decision.max_loss,
        margin_requirement=option_decision.margin_requirement,
        buying_power_effect=option_decision.buying_power_effect,
        trade_identity=trading_decision.trade_identity,
    )


def _open_option_order_request(
    *,
    trading_decision: TradingDecisionRecord,
    risk_decision: RiskDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
    trade_date: datetime,
    quantity: int,
    legs: tuple[PaperOptionOrderLeg, ...],
) -> PaperOptionOrderRequest | None:
    if not legs:
        return None
    shared_kwargs = dict(
        trading_decision_id=trading_decision.trading_decision_id,
        risk_decision_id=risk_decision.risk_decision_id,
        option_strategy_decision_id=option_decision.option_strategy_decision_id,
        ticker=trading_decision.ticker,
        strategy_id=trading_decision.strategy_id,
        option_strategy_type=option_decision.option_strategy_type,
        action=trading_decision.decision,
        trade_date=trade_date.date(),
        quantity=quantity,
        limit_price=option_decision.net_debit_or_credit,
        max_loss=option_decision.max_loss,
        margin_requirement=option_decision.margin_requirement,
        buying_power_effect=option_decision.buying_power_effect,
        trade_identity=trading_decision.trade_identity,
    )
    if len(legs) == 1:
        leg = legs[0]
        return PaperOptionOrderRequest(
            **shared_kwargs,
            contract_symbol=leg.contract_symbol,
            position_intent=leg.position_intent,
        )
    return PaperOptionOrderRequest(
        **shared_kwargs,
        order_class="mleg",
        legs=legs,
    )


def _close_option_order_request(
    *,
    trading_decision: TradingDecisionRecord,
    risk_decision: RiskDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
    trade_date: datetime,
    quantity: int,
    close_legs: tuple[PaperOptionOrderLeg, ...],
) -> PaperOptionOrderRequest | None:
    if not close_legs:
        return None
    shared_kwargs = dict(
        trading_decision_id=trading_decision.trading_decision_id,
        risk_decision_id=risk_decision.risk_decision_id,
        option_strategy_decision_id=option_decision.option_strategy_decision_id,
        ticker=trading_decision.ticker,
        strategy_id=trading_decision.strategy_id,
        option_strategy_type=option_decision.option_strategy_type,
        action=trading_decision.decision,
        trade_date=trade_date.date(),
        quantity=quantity,
        limit_price=option_decision.net_debit_or_credit,
        max_loss=option_decision.max_loss,
        margin_requirement=option_decision.margin_requirement,
        buying_power_effect=option_decision.buying_power_effect,
        trade_identity=trading_decision.trade_identity,
    )
    if len(close_legs) == 1:
        leg = close_legs[0]
        return PaperOptionOrderRequest(
            **shared_kwargs,
            contract_symbol=leg.contract_symbol,
            position_intent=leg.position_intent,
        )
    return PaperOptionOrderRequest(
        **shared_kwargs,
        order_class="mleg",
        legs=close_legs,
    )


def _paper_option_order_legs_from_decision(
    option_decision: OptionStrategyDecisionRecord,
    *,
    action: str,
) -> tuple[PaperOptionOrderLeg, ...]:
    position_intent_map = {
        "buy": "buy_to_open",
        "sell": "sell_to_open",
    }
    legs: list[PaperOptionOrderLeg] = []
    for payload in option_decision.metadata_json.get("legs", []):
        if not isinstance(payload, dict):
            continue
        side = str(payload.get("side") or "")
        position_intent = position_intent_map.get(side)
        if position_intent is None:
            continue
        legs.append(
            PaperOptionOrderLeg(
                contract_symbol=_option_contract_symbol_from_payload(option_decision.ticker, payload),
                ratio_qty=int(payload.get("ratio_qty") or payload.get("quantity") or 1),
                position_intent=position_intent,
            )
        )
    return tuple(legs)


def _paper_option_close_legs_from_position(
    *,
    existing_position: PaperOptionPosition | None,
    option_decision: OptionStrategyDecisionRecord,
) -> tuple[PaperOptionOrderLeg, ...]:
    if existing_position is not None:
        broker_leg_refs = existing_position.metadata_json.get("broker_leg_refs")
        if isinstance(broker_leg_refs, list):
            refs = _paper_option_legs_from_broker_refs(broker_leg_refs, close_existing=True)
            if refs:
                return refs
    fallback_payloads = option_decision.metadata_json.get("legs", [])
    refs: list[PaperOptionOrderLeg] = []
    for payload in fallback_payloads:
        if not isinstance(payload, dict):
            continue
        side = str(payload.get("side") or "")
        if side not in {"buy", "sell"}:
            continue
        refs.append(
            PaperOptionOrderLeg(
                contract_symbol=_option_contract_symbol_from_payload(option_decision.ticker, payload),
                ratio_qty=int(payload.get("ratio_qty") or payload.get("quantity") or 1),
                position_intent="sell_to_close" if side == "buy" else "buy_to_close",
            )
        )
    return tuple(refs)


def _paper_option_legs_from_broker_refs(
    refs_payload: list[Any],
    *,
    close_existing: bool,
) -> tuple[PaperOptionOrderLeg, ...]:
    legs: list[PaperOptionOrderLeg] = []
    for item in refs_payload:
        if not isinstance(item, dict):
            continue
        contract_symbol = item.get("contract_symbol")
        if not isinstance(contract_symbol, str) or not contract_symbol:
            continue
        raw_intent = str(item.get("position_intent") or "")
        if close_existing:
            position_intent = _closing_position_intent(raw_intent)
        else:
            position_intent = raw_intent or "buy_to_open"
        legs.append(
            PaperOptionOrderLeg(
                contract_symbol=contract_symbol,
                ratio_qty=int(item.get("ratio_qty") or 1),
                position_intent=position_intent,
            )
        )
    return tuple(legs)


def _closing_position_intent(raw_intent: str) -> str:
    return {
        "buy_to_open": "sell_to_close",
        "sell_to_open": "buy_to_close",
        "buy_to_close": "buy_to_close",
        "sell_to_close": "sell_to_close",
    }.get(raw_intent, "sell_to_close")


def _option_contract_symbol_from_payload(ticker: str, payload: dict[str, Any]) -> str:
    contract_symbol = payload.get("contract_symbol")
    if isinstance(contract_symbol, str) and contract_symbol:
        return contract_symbol
    expiry = datetime.fromisoformat(str(payload["expiry"])).date()
    option_code = "C" if str(payload.get("option_type")) == "call" else "P"
    strike_component = f"{int(round(float(payload['strike']) * 1000)):08d}"
    return f"{ticker.upper()}{expiry.strftime('%y%m%d')}{option_code}{strike_component}"


def _broker_leg_refs_from_request(request: PaperOptionOrderRequest) -> list[dict[str, Any]]:
    if request.order_class == "mleg":
        return [
            {
                "contract_symbol": leg.contract_symbol,
                "ratio_qty": leg.ratio_qty,
                "position_intent": leg.position_intent,
            }
            for leg in request.legs
        ]
    if request.contract_symbol is None:
        return []
    return [
        {
            "contract_symbol": request.contract_symbol,
            "ratio_qty": 1,
            "position_intent": request.position_intent,
        }
    ]


def _opening_broker_leg_refs_from_request(request: PaperOptionOrderRequest) -> list[dict[str, Any]]:
    refs = _broker_leg_refs_from_request(request)
    open_refs = [item for item in refs if str(item.get("position_intent") or "").endswith("_open")]
    return open_refs or refs


def _risk_hedge_option_strategy_type(
    *,
    trading_decision: TradingDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
    existing_position: PaperOptionPosition | None,
) -> str:
    if (
        trading_decision.trade_identity == "risk_hedge_overlay"
        and existing_position is not None
        and trading_decision.decision in {"close_option_strategy", "adjust_option_strategy"}
    ):
        return existing_position.option_strategy_type
    return option_decision.option_strategy_type


def _materialized_option_positions(
    *,
    trading_decision: TradingDecisionRecord,
    option_decision: OptionStrategyDecisionRecord,
    order_request: PaperOptionOrderRequest,
    order: PaperOptionOrderRequest | Any,
    execution: Any,
    existing_position: PaperOptionPosition | None,
) -> tuple[PaperOptionPosition, ...]:
    action = trading_decision.decision
    if action == "close_option_strategy":
        if existing_position is None:
            return ()
        return (
            PaperOptionPosition(
                paper_option_position_id=existing_position.paper_option_position_id,
                option_strategy_decision_id=existing_position.option_strategy_decision_id,
                ticker=existing_position.ticker,
                strategy_id=existing_position.strategy_id,
                option_strategy_type=existing_position.option_strategy_type,
                trade_identity=existing_position.trade_identity,
                quantity=existing_position.quantity,
                opened_at=existing_position.opened_at,
                updated_at=execution.executed_at,
                status="closed",
                expiry=existing_position.expiry,
                max_loss=existing_position.max_loss,
                margin_requirement=0.0,
                buying_power_effect=0.0,
                assignment_notional=0.0,
                metadata_json={
                    **dict(existing_position.metadata_json),
                    "lifecycle_action": action,
                    "closing_order_id": order.paper_option_order_id,
                    "closing_broker_order_id": order.broker_order_id,
                },
            ),
        )
    if action == "roll_option_strategy":
        positions: list[PaperOptionPosition] = []
        if existing_position is not None:
            positions.append(
                PaperOptionPosition(
                    paper_option_position_id=existing_position.paper_option_position_id,
                    option_strategy_decision_id=existing_position.option_strategy_decision_id,
                    ticker=existing_position.ticker,
                    strategy_id=existing_position.strategy_id,
                    option_strategy_type=existing_position.option_strategy_type,
                    trade_identity=existing_position.trade_identity,
                    quantity=existing_position.quantity,
                    opened_at=existing_position.opened_at,
                    updated_at=execution.executed_at,
                    status="closed",
                    expiry=existing_position.expiry,
                    max_loss=existing_position.max_loss,
                    margin_requirement=0.0,
                    buying_power_effect=0.0,
                    assignment_notional=0.0,
                    metadata_json={
                        **dict(existing_position.metadata_json),
                        "lifecycle_action": action,
                        "replacement_order_id": order.paper_option_order_id,
                        "closing_broker_order_id": order.broker_order_id,
                    },
                )
            )
        positions.append(
            PaperOptionPosition(
                paper_option_position_id=order.paper_option_order_id,
                option_strategy_decision_id=option_decision.option_strategy_decision_id,
                ticker=order.ticker,
                strategy_id=order.strategy_id,
                option_strategy_type=order.option_strategy_type,
                trade_identity=order.trade_identity,
                quantity=order.quantity,
                opened_at=execution.executed_at,
                updated_at=execution.executed_at,
                status="open",
                expiry=option_decision.expiry,
                max_loss=option_decision.max_loss,
                margin_requirement=option_decision.margin_requirement,
                buying_power_effect=option_decision.buying_power_effect,
                assignment_notional=option_decision.assignment_notional,
                metadata_json={
                    **dict(option_decision.metadata_json),
                    "lifecycle_action": action,
                        "broker_leg_refs": _opening_broker_leg_refs_from_request(order_request),
                    "opening_broker_order_id": order.broker_order_id,
                    **(
                        {"supersedes_option_position_id": existing_position.paper_option_position_id}
                        if existing_position is not None
                        else {}
                    ),
                },
            )
        )
        return tuple(positions)
    if action == "adjust_option_strategy" and existing_position is not None:
        return (
            PaperOptionPosition(
                paper_option_position_id=existing_position.paper_option_position_id,
                option_strategy_decision_id=option_decision.option_strategy_decision_id,
                ticker=existing_position.ticker,
                strategy_id=existing_position.strategy_id,
                option_strategy_type=existing_position.option_strategy_type,
                trade_identity=existing_position.trade_identity,
                quantity=order.quantity,
                opened_at=existing_position.opened_at,
                updated_at=execution.executed_at,
                status="open",
                expiry=option_decision.expiry,
                max_loss=option_decision.max_loss,
                margin_requirement=option_decision.margin_requirement,
                buying_power_effect=option_decision.buying_power_effect,
                assignment_notional=option_decision.assignment_notional,
                metadata_json={
                    **dict(existing_position.metadata_json),
                    **dict(option_decision.metadata_json),
                    "lifecycle_action": action,
                    "broker_leg_refs": _opening_broker_leg_refs_from_request(order_request),
                    "opening_broker_order_id": order.broker_order_id,
                },
            ),
        )
    return (
        PaperOptionPosition(
            paper_option_position_id=order.paper_option_order_id,
            option_strategy_decision_id=option_decision.option_strategy_decision_id,
            ticker=order.ticker,
            strategy_id=order.strategy_id,
            option_strategy_type=order.option_strategy_type,
            trade_identity=order.trade_identity,
            quantity=order.quantity,
            opened_at=execution.executed_at,
            updated_at=execution.executed_at,
            status="open",
            expiry=option_decision.expiry,
            max_loss=option_decision.max_loss,
            margin_requirement=option_decision.margin_requirement,
            buying_power_effect=option_decision.buying_power_effect,
            assignment_notional=option_decision.assignment_notional,
            metadata_json={
                **dict(option_decision.metadata_json),
                "broker_leg_refs": _opening_broker_leg_refs_from_request(order_request),
                "opening_broker_order_id": order.broker_order_id,
            },
        ),
    )


def _build_execution_fallback_trade_risk_request(
    trading_decision: TradingDecisionRecord,
) -> TradeRiskRequest:
    candidate_context = dict(trading_decision.context_snapshot_json.get("candidate_context") or {})
    risk_context = dict(trading_decision.context_snapshot_json.get("risk_context") or {})
    candidate = SimpleNamespace(
        candidate_score_id=trading_decision.candidate_score_id,
        ticker=trading_decision.ticker,
        candidate_score=float(candidate_context.get("candidate_score", trading_decision.confidence)),
        decision_time=trading_decision.decision_time,
        direction="bullish" if trading_decision.decision != "enter_short" else "bearish",
        strategy_lifecycle_status=str(trading_decision.metadata_json.get("strategy_lifecycle_status") or "active"),
    )
    classification = SimpleNamespace(
        trade_classification_id=trading_decision.trade_classification_id,
        trade_identity=trading_decision.trade_identity,
    )
    price = float(
        trading_decision.metadata_json.get("option_strategy", {}).get("underlying_price")
        or risk_context.get("price")
        or 1.0
    )
    return TradeRiskRequest(
        candidate=candidate,
        classification=classification,
        instrument_type="stock",
        target_weight=float(risk_context.get("approved_weight") or trading_decision.approved_weight or trading_decision.target_weight or 0.0),
        confidence=float(trading_decision.confidence),
        sector=None,
        beta_bucket=None,
        volatility_bucket="medium",
        liquidity_bucket="liquid",
        event_type=None,
        macro_sensitivity=None,
        price=price,
        atr_pct=0.0,
        average_daily_dollar_volume=0.0,
        signal_freshness={},
        estimated_margin_requirement=max(price, 1.0),
        estimated_buying_power_effect=max(price, 1.0),
        estimated_initial_margin_requirement=max(price, 1.0),
        estimated_maintenance_margin_requirement=max(price * 0.5, 1.0),
    )


def _option_decision_from_trading_decision(
    *,
    trading_decision: TradingDecisionRecord,
    trade_date: datetime,
) -> OptionStrategyDecisionRecord | None:
    option_strategy_payload = trading_decision.metadata_json.get("option_strategy")
    if not isinstance(option_strategy_payload, dict):
        return None
    return OptionStrategyDecisionRecord(
        option_strategy_decision_id=str(option_strategy_payload["option_strategy_decision_id"]),
        trading_decision_id=trading_decision.trading_decision_id,
        ticker=trading_decision.ticker,
        trade_identity=trading_decision.trade_identity,
        decision_action=trading_decision.decision,
        option_strategy_type=str(option_strategy_payload["option_strategy_type"]),
        status=str(option_strategy_payload.get("status", "ready")),
        rejection_reason=option_strategy_payload.get("rejection_reason"),
        strategy_id=trading_decision.strategy_id,
        strategy_version=trading_decision.strategy_version,
        expression_bucket_id=trading_decision.expression_bucket_id,
        expression_bucket_version=trading_decision.expression_bucket_version,
        underlying_price=float(option_strategy_payload["underlying_price"]),
        expiry=trade_date.date(),
        net_debit_or_credit=float(option_strategy_payload["net_debit_or_credit"]),
        max_loss=float(option_strategy_payload["max_loss"]),
        max_profit=float(option_strategy_payload.get("max_profit")) if option_strategy_payload.get("max_profit") is not None else None,
        breakevens=tuple(float(item) for item in option_strategy_payload.get("breakevens", [])),
        margin_requirement=float(option_strategy_payload["margin_requirement"]),
        buying_power_effect=float(option_strategy_payload["buying_power_effect"]),
        assignment_notional=float(option_strategy_payload.get("assignment_notional", 0.0)),
        portfolio_delta=float(option_strategy_payload.get("portfolio_delta", 0.0)),
        portfolio_gamma=float(option_strategy_payload.get("portfolio_gamma", 0.0)),
        portfolio_theta=float(option_strategy_payload.get("portfolio_theta", 0.0)),
        portfolio_vega=float(option_strategy_payload.get("portfolio_vega", 0.0)),
        earnings_date=None,
        event_through_expiry=bool(option_strategy_payload.get("event_through_expiry", False)),
        strategy_pairing_method=str(option_strategy_payload.get("strategy_pairing_method", "single_leg")),
        assignment_plan=option_strategy_payload.get("assignment_plan"),
        margin_model_profile=str(option_strategy_payload.get("margin_model_profile", "estimated_fidelity_like_conservative_v1")),
        margin_model_version=str(option_strategy_payload.get("margin_model_version", "v1")),
        margin_requirement_source=str(option_strategy_payload.get("margin_requirement_source", "simulated_formula")),
        profit_target_pct=float(option_strategy_payload.get("profit_target_pct", 0.0)),
        max_loss_rule=str(option_strategy_payload.get("max_loss_rule", "")),
        roll_conditions=tuple(option_strategy_payload.get("roll_conditions", [])),
        close_conditions=tuple(option_strategy_payload.get("close_conditions", [])),
        metadata_json=dict(option_strategy_payload.get("metadata_json", {})),
        created_at=trade_date,
    )


def _fallback_option_strategy_payload(
    trading_decision: TradingDecisionRecord,
    *,
    expression_bucket_id: str,
) -> dict[str, Any] | None:
    payload = trading_decision.metadata_json.get("option_strategy_fallbacks", {}).get(expression_bucket_id)
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def _remaining_fallback_expression_bucket_ids(
    trading_decision: TradingDecisionRecord,
) -> list[str]:
    plan = trading_decision.context_snapshot_json.get("classification_context", {}).get("expression_fallback_plan") or []
    current_expression_id = trading_decision.expression_bucket_id
    matched = False
    remaining: list[str] = []
    for item in plan:
        expression_bucket_id = str(item.get("expression_bucket_id") or "")
        if not matched:
            if expression_bucket_id == current_expression_id:
                matched = True
            continue
        if expression_bucket_id:
            remaining.append(expression_bucket_id)
    return remaining


def _build_execution_fallback_option_trade_risk_request(
    trading_decision: TradingDecisionRecord,
) -> TradeRiskRequest:
    candidate_context = dict(trading_decision.context_snapshot_json.get("candidate_context") or {})
    risk_context = dict(trading_decision.context_snapshot_json.get("risk_context") or {})
    option_strategy_payload = dict(trading_decision.metadata_json.get("option_strategy") or {})
    candidate = SimpleNamespace(
        candidate_score_id=trading_decision.candidate_score_id,
        ticker=trading_decision.ticker,
        candidate_score=float(candidate_context.get("candidate_score", trading_decision.confidence)),
        decision_time=trading_decision.decision_time,
        direction="bullish" if trading_decision.decision != "enter_short" else "bearish",
        strategy_lifecycle_status=str(trading_decision.metadata_json.get("strategy_lifecycle_status") or "active"),
    )
    classification = SimpleNamespace(
        trade_classification_id=trading_decision.trade_classification_id,
        trade_identity=trading_decision.trade_identity,
    )
    per_contract_price = max(abs(float(option_strategy_payload.get("net_debit_or_credit") or 0.0)) * 100.0, 1.0)
    estimated_margin_requirement = option_strategy_payload.get("margin_requirement")
    estimated_buying_power_effect = option_strategy_payload.get("buying_power_effect")
    return TradeRiskRequest(
        candidate=candidate,
        classification=classification,
        instrument_type="option",
        target_weight=float(risk_context.get("approved_weight") or trading_decision.approved_weight or trading_decision.target_weight or 0.0),
        confidence=float(trading_decision.confidence),
        sector=None,
        beta_bucket=None,
        volatility_bucket="high" if option_strategy_payload.get("event_through_expiry") else "medium",
        liquidity_bucket="liquid",
        event_type=None,
        macro_sensitivity=None,
        price=per_contract_price,
        atr_pct=0.0,
        average_daily_dollar_volume=0.0,
        signal_freshness={},
        estimated_margin_requirement=float(estimated_margin_requirement) if estimated_margin_requirement is not None else None,
        estimated_buying_power_effect=float(estimated_buying_power_effect) if estimated_buying_power_effect is not None else None,
        estimated_initial_margin_requirement=float(estimated_margin_requirement) if estimated_margin_requirement is not None else None,
        estimated_maintenance_margin_requirement=float(estimated_buying_power_effect) if estimated_buying_power_effect is not None else None,
        assignment_notional=float(option_strategy_payload.get("assignment_notional", 0.0)),
        option_risk_metadata_complete=bool(option_strategy_payload.get("metadata_json", {}).get("legs")),
    )


def _build_execution_fallback_option_risk_input(
    option_decision: OptionStrategyDecisionRecord,
    *,
    contracts: int,
) -> OptionRiskInput:
    legs = []
    for payload in option_decision.metadata_json.get("legs", []):
        legs.append(
            OptionLegRiskInput(
                option_type=str(payload["option_type"]),
                side=str(payload["side"]),
                quantity=int(payload["quantity"]) * contracts,
                strike=float(payload["strike"]),
                expiry=datetime.fromisoformat(f"{payload['expiry']}T00:00:00").date(),
                delta=float(payload["delta"]),
                gamma=float(payload["gamma"]),
                theta=float(payload["theta"]),
                vega=float(payload["vega"]),
                premium=float(payload["chosen_price"]),
            )
        )
    return OptionRiskInput(
        ticker=option_decision.ticker,
        trade_identity=option_decision.trade_identity,
        option_strategy_type=option_decision.option_strategy_type,
        underlying_price=option_decision.underlying_price,
        sector=None,
        event_type=None,
        event_through_expiry=option_decision.event_through_expiry,
        margin_requirement=option_decision.margin_requirement * contracts,
        buying_power_effect=option_decision.buying_power_effect * contracts,
        max_loss=option_decision.max_loss * contracts,
        max_profit=option_decision.max_profit * contracts if option_decision.max_profit is not None else None,
        net_debit_or_credit=option_decision.net_debit_or_credit * contracts,
        legs=tuple(legs),
    )
