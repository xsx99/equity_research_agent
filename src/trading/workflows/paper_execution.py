"""PR06 Alpaca-backed paper stock execution workflow."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.trading.brokers.paper_option import PaperOptionBroker, PaperOptionOrderRequest, PaperOptionPosition
from src.trading.brokers.paper_stock import PaperOrderRequest, PaperOrderRecord, PaperStockBroker
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.options.hedge import RiskHedgeDecisionRecord
from src.trading.options.risk import OptionRiskSnapshotRecord
from src.trading.options.strategy import OptionStrategyDecisionRecord, OptionsStrategyLayer
from src.trading.portfolio.state import PortfolioSnapshot
from src.trading.risk import RiskDecisionRecord
from src.trading.workflows.portfolio_sync import BrokerPortfolioSyncWorkflow
from src.trading.workflows.trading_decision import TradingDecisionRecord


@dataclass(frozen=True)
class PaperExecutionWorkflowResult:
    """Persisted artifacts produced by the PR06 stock paper broker path."""

    paper_orders: tuple[PaperOrderRecord, ...]
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
    ) -> None:
        self.repository = repository
        self.broker = broker
        self.option_broker = option_broker
        self.manual_request_service = manual_request_service
        self.portfolio_sync = BrokerPortfolioSyncWorkflow(repository=repository, broker=broker)
        self.options_strategy_layer = OptionsStrategyLayer()

    def run(
        self,
        *,
        trading_decisions: tuple[TradingDecisionRecord, ...],
        risk_decisions: tuple[RiskDecisionRecord, ...],
        trade_date: datetime,
    ) -> PaperExecutionWorkflowResult:
        risk_by_id = {decision.risk_decision_id: decision for decision in risk_decisions}
        orders: list[PaperOrderRecord] = []
        snapshots: list[PortfolioSnapshot] = []
        for trading_decision in trading_decisions:
            if trading_decision.instrument_type == "option":
                self._handle_option_decision(
                    trading_decision=trading_decision,
                    risk_decision=risk_by_id.get(trading_decision.risk_decision_id),
                    trade_date=trade_date,
                )
                continue
            if trading_decision.instrument_type != "stock":
                continue
            if trading_decision.decision not in {"enter_long", "reduce", "exit", "enter_short"}:
                continue
            if not bool(trading_decision.metadata_json.get("paper_trade_authorized", False)) and trading_decision.manual_request_id is None:
                continue
            risk_decision = risk_by_id.get(trading_decision.risk_decision_id)
            if risk_decision is None:
                continue
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
                continue
            if self.repository.has_paper_execution(execution.paper_execution_id):
                continue
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
        return PaperExecutionWorkflowResult(
            paper_orders=tuple(orders),
            portfolio_snapshots=tuple(snapshots),
        )

    def _handle_option_decision(
        self,
        *,
        trading_decision: TradingDecisionRecord,
        risk_decision: RiskDecisionRecord | None,
        trade_date: datetime,
    ) -> None:
        if self.option_broker is None or risk_decision is None:
            return
        option_strategy_payload = trading_decision.metadata_json.get("option_strategy")
        if not isinstance(option_strategy_payload, dict):
            return
        option_decision = OptionStrategyDecisionRecord(
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
        self.repository.save_option_strategy_decision(option_decision)
        self.repository.save_option_strategy_legs(self.options_strategy_layer.build_legs(option_decision))
        order = self.option_broker.submit_order(
            PaperOptionOrderRequest(
                trading_decision_id=trading_decision.trading_decision_id,
                risk_decision_id=risk_decision.risk_decision_id,
                option_strategy_decision_id=option_decision.option_strategy_decision_id,
                ticker=trading_decision.ticker,
                strategy_id=trading_decision.strategy_id,
                option_strategy_type=option_decision.option_strategy_type,
                action=trading_decision.decision,
                trade_date=trade_date.date(),
                quantity=max(1, int(round(risk_decision.approved_quantity or 1))),
                limit_price=option_decision.net_debit_or_credit,
                max_loss=option_decision.max_loss,
                margin_requirement=option_decision.margin_requirement,
                buying_power_effect=option_decision.buying_power_effect,
                trade_identity=trading_decision.trade_identity,
            )
        )
        self.repository.save_paper_option_order(order)
        execution = self.option_broker.find_execution_by_order_id(order.paper_option_order_id)
        if execution is not None and not self.repository.has_paper_option_execution(execution.paper_option_execution_id):
            self.repository.save_paper_option_execution(execution)
            self.repository.save_paper_option_position(
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
                    metadata_json=option_decision.metadata_json,
                )
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
                        risk_decision_id=risk_decision.risk_decision_id,
                        ticker=trading_decision.ticker,
                        action=trading_decision.decision,
                        option_strategy_type=option_decision.option_strategy_type,
                        rationale="risk_manager_generated_overlay",
                        hedge_cost=abs(execution.net_cash_effect),
                        protected_notional=max(
                            option_decision.assignment_notional,
                            option_decision.buying_power_effect,
                        ),
                        metadata_json=option_decision.metadata_json,
                    )
                )

    def _manual_request_mode(self, request_id: str | None) -> str | None:
        if request_id is None or self.manual_request_service is None:
            return None
        for request in self.manual_request_service.load_active():
            if request.request_id == request_id:
                return request.mode
        return None
