"""SQLAlchemy-backed persistence for trading artifacts."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from src.db.models.trading import (
    OptionRiskSnapshot,
    OptionStrategyDecision,
    OptionStrategyLeg,
    PaperExecution,
    PaperOptionExecution,
    PaperOptionOrder,
    PaperOptionPosition as PaperOptionPositionModel,
    PaperOrder,
    PaperPosition,
    PortfolioSnapshot as PortfolioSnapshotModel,
    RiskHedgeDecision,
)
from src.trading.brokers.paper_option import (
    PaperOptionExecutionRecord,
    PaperOptionOrderRecord,
    PaperOptionPosition,
)
from src.trading.brokers.paper_stock import PaperExecutionRecord, PaperOrderRecord
from src.trading.options.hedge import RiskHedgeDecisionRecord
from src.trading.options.risk import OptionRiskSnapshotRecord
from src.trading.options.strategy import OptionStrategyDecisionRecord, OptionStrategyLegRecord
from src.trading.portfolio.state import PortfolioSnapshot, StockPosition


class SQLAlchemyTradingRepository:
    """Persist PR6 paper-broker artifacts into SQLAlchemy ORM models."""

    def __init__(self, session: Any) -> None:
        self.session = session

    def save_paper_order(self, order: PaperOrderRecord) -> None:
        row = self.session.query(PaperOrder).filter_by(client_order_id=order.client_order_id).one_or_none()
        if row is None:
            row = PaperOrder(
                paper_order_id=_to_uuid(order.paper_order_id),
                client_order_id=order.client_order_id,
            )
            self.session.add(row)
        row.broker_order_id = order.broker_order_id
        row.trading_decision_id = _to_uuid_or_none(order.trading_decision_id)
        row.risk_decision_id = _to_uuid_or_none(order.risk_decision_id)
        row.ticker = order.ticker
        row.strategy_id = order.strategy_id
        row.action = order.action
        row.trade_date = order.trade_date
        row.quantity = Decimal(str(order.quantity))
        row.order_price = _decimal_or_none(order.limit_price)
        row.status = order.status
        row.rejection_reason = order.rejection_reason
        row.created_at = order.created_at
        self.session.flush()

    def save_paper_execution(self, execution: PaperExecutionRecord) -> None:
        row = self.session.query(PaperExecution).filter_by(
            paper_execution_id=_to_uuid(execution.paper_execution_id)
        ).one_or_none()
        if row is None:
            row = PaperExecution(
                paper_execution_id=_to_uuid(execution.paper_execution_id),
            )
            self.session.add(row)
        row.paper_order_id = _to_uuid(execution.paper_order_id)
        row.broker_order_id = execution.broker_order_id
        row.ticker = execution.ticker
        row.quantity = Decimal(str(execution.quantity))
        row.fill_price = Decimal(str(execution.fill_price))
        row.trade_date = execution.trade_date
        row.executed_at = execution.executed_at
        row.net_cash_effect = Decimal(str(execution.net_cash_effect))
        self.session.flush()

    def save_option_strategy_decision(self, decision: OptionStrategyDecisionRecord) -> None:
        row = self.session.query(OptionStrategyDecision).filter_by(
            option_strategy_decision_id=_to_uuid(decision.option_strategy_decision_id)
        ).one_or_none()
        if row is None:
            row = OptionStrategyDecision(option_strategy_decision_id=_to_uuid(decision.option_strategy_decision_id))
            self.session.add(row)
        row.trading_decision_id = _to_uuid_or_none(decision.trading_decision_id)
        row.ticker = decision.ticker
        row.trade_identity = decision.trade_identity
        row.decision_action = decision.decision_action
        row.option_strategy_type = decision.option_strategy_type
        row.status = decision.status
        row.rejection_reason = decision.rejection_reason
        row.strategy_id = decision.strategy_id
        row.strategy_version = decision.strategy_version
        row.expression_bucket_id = decision.expression_bucket_id
        row.expression_bucket_version = decision.expression_bucket_version
        row.underlying_price = Decimal(str(decision.underlying_price))
        row.expiry = decision.expiry
        row.net_debit_or_credit = Decimal(str(decision.net_debit_or_credit))
        row.max_loss = Decimal(str(decision.max_loss))
        row.max_profit = _decimal_or_none(decision.max_profit)
        row.breakevens_json = list(decision.breakevens)
        row.margin_requirement = Decimal(str(decision.margin_requirement))
        row.buying_power_effect = Decimal(str(decision.buying_power_effect))
        row.assignment_notional = Decimal(str(decision.assignment_notional))
        row.portfolio_delta = Decimal(str(decision.portfolio_delta))
        row.portfolio_gamma = Decimal(str(decision.portfolio_gamma))
        row.portfolio_theta = Decimal(str(decision.portfolio_theta))
        row.portfolio_vega = Decimal(str(decision.portfolio_vega))
        row.earnings_date = decision.earnings_date
        row.event_through_expiry = decision.event_through_expiry
        row.strategy_pairing_method = decision.strategy_pairing_method
        row.assignment_plan = decision.assignment_plan
        row.margin_model_profile = decision.margin_model_profile
        row.margin_model_version = decision.margin_model_version
        row.margin_requirement_source = decision.margin_requirement_source
        row.profit_target_pct = Decimal(str(decision.profit_target_pct))
        row.max_loss_rule = decision.max_loss_rule
        row.roll_conditions_json = list(decision.roll_conditions)
        row.close_conditions_json = list(decision.close_conditions)
        row.metadata_json = dict(decision.metadata_json)
        row.created_at = decision.created_at
        self.session.flush()

    def save_option_strategy_legs(
        self,
        legs: list[OptionStrategyLegRecord] | tuple[OptionStrategyLegRecord, ...],
    ) -> None:
        for leg in legs:
            row = self.session.query(OptionStrategyLeg).filter_by(
                option_strategy_leg_id=_to_uuid(leg.option_strategy_leg_id)
            ).one_or_none()
            if row is None:
                row = OptionStrategyLeg(option_strategy_leg_id=_to_uuid(leg.option_strategy_leg_id))
                self.session.add(row)
            row.option_strategy_decision_id = _to_uuid(leg.option_strategy_decision_id)
            row.ticker = leg.ticker
            row.option_type = leg.option_type
            row.side = leg.side
            row.quantity = int(leg.quantity)
            row.strike = Decimal(str(leg.strike))
            row.expiry = leg.expiry
            row.dte = int(leg.dte)
            row.delta = Decimal(str(leg.delta))
            row.gamma = Decimal(str(leg.gamma))
            row.theta = Decimal(str(leg.theta))
            row.vega = Decimal(str(leg.vega))
            row.iv_rank = _decimal_or_none(leg.iv_rank)
            row.bid = Decimal(str(leg.bid))
            row.ask = Decimal(str(leg.ask))
            row.mid = Decimal(str(leg.mid))
            row.chosen_price = Decimal(str(leg.chosen_price))
            row.created_at = leg.created_at
        self.session.flush()

    def save_option_risk_snapshot(self, snapshot: OptionRiskSnapshotRecord) -> None:
        row = OptionRiskSnapshot(
            option_risk_snapshot_id=_to_uuid(snapshot.option_risk_snapshot_id),
            ticker=snapshot.ticker,
            trade_identity=snapshot.trade_identity,
            option_strategy_type=snapshot.option_strategy_type,
            underlying_price=Decimal(str(snapshot.underlying_price)),
            portfolio_delta=Decimal(str(snapshot.portfolio_delta)),
            portfolio_gamma=Decimal(str(snapshot.portfolio_gamma)),
            portfolio_theta=Decimal(str(snapshot.portfolio_theta)),
            portfolio_vega=Decimal(str(snapshot.portfolio_vega)),
            net_debit_or_credit=Decimal(str(snapshot.net_debit_or_credit)),
            max_loss=Decimal(str(snapshot.max_loss)),
            max_profit=_decimal_or_none(snapshot.max_profit),
            margin_requirement=Decimal(str(snapshot.margin_requirement)),
            buying_power_effect=Decimal(str(snapshot.buying_power_effect)),
            assignment_notional=Decimal(str(snapshot.assignment_notional)),
            worst_case_assignment_notional=Decimal(str(snapshot.worst_case_assignment_notional)),
            margin_model_profile=snapshot.margin_model_profile,
            margin_model_version=snapshot.margin_model_version,
            margin_requirement_source=snapshot.margin_requirement_source,
            risk_status=snapshot.risk_status,
            reason_code=snapshot.reason_code,
            metadata_json=dict(snapshot.metadata_json),
            created_at=snapshot.created_at,
        )
        self.session.add(row)
        self.session.flush()

    def save_risk_hedge_decision(self, decision: RiskHedgeDecisionRecord) -> None:
        row = RiskHedgeDecision(
            risk_hedge_decision_id=_to_uuid(decision.risk_hedge_decision_id),
            risk_decision_id=_to_uuid_or_none(decision.risk_decision_id),
            ticker=decision.ticker,
            trade_identity=decision.trade_identity,
            action=decision.action,
            option_strategy_type=decision.option_strategy_type,
            rationale=decision.rationale,
            hedge_cost=Decimal(str(decision.hedge_cost)),
            protected_notional=Decimal(str(decision.protected_notional)),
            metadata_json=dict(decision.metadata_json),
            created_at=decision.created_at,
        )
        self.session.add(row)
        self.session.flush()

    def has_paper_execution(self, paper_execution_id: str) -> bool:
        return self.session.query(PaperExecution).filter_by(
            paper_execution_id=_to_uuid(paper_execution_id)
        ).one_or_none() is not None

    def save_paper_option_order(self, order: PaperOptionOrderRecord) -> None:
        row = self.session.query(PaperOptionOrder).filter_by(
            paper_option_order_id=_to_uuid(order.paper_option_order_id)
        ).one_or_none()
        if row is None:
            row = PaperOptionOrder(paper_option_order_id=_to_uuid(order.paper_option_order_id))
            self.session.add(row)
        row.trading_decision_id = _to_uuid_or_none(order.trading_decision_id)
        row.risk_decision_id = _to_uuid_or_none(order.risk_decision_id)
        row.option_strategy_decision_id = _to_uuid_or_none(order.option_strategy_decision_id)
        row.ticker = order.ticker
        row.strategy_id = order.strategy_id
        row.option_strategy_type = order.option_strategy_type
        row.action = order.action
        row.trade_identity = order.trade_identity
        row.trade_date = order.trade_date
        row.quantity = int(order.quantity)
        row.limit_price = Decimal(str(order.limit_price))
        row.status = order.status
        row.rejection_reason = order.rejection_reason
        row.margin_requirement = Decimal(str(order.margin_requirement))
        row.buying_power_effect = Decimal(str(order.buying_power_effect))
        row.created_at = order.created_at
        self.session.flush()

    def save_paper_option_execution(self, execution: PaperOptionExecutionRecord) -> None:
        row = self.session.query(PaperOptionExecution).filter_by(
            paper_option_execution_id=_to_uuid(execution.paper_option_execution_id)
        ).one_or_none()
        if row is None:
            row = PaperOptionExecution(paper_option_execution_id=_to_uuid(execution.paper_option_execution_id))
            self.session.add(row)
        row.paper_option_order_id = _to_uuid(execution.paper_option_order_id)
        row.ticker = execution.ticker
        row.quantity = int(execution.quantity)
        row.fill_price = Decimal(str(execution.fill_price))
        row.trade_date = execution.trade_date
        row.executed_at = execution.executed_at
        row.net_cash_effect = Decimal(str(execution.net_cash_effect))
        self.session.flush()

    def has_paper_option_execution(self, paper_option_execution_id: str) -> bool:
        return self.session.query(PaperOptionExecution).filter_by(
            paper_option_execution_id=_to_uuid(paper_option_execution_id)
        ).one_or_none() is not None

    def load_paper_positions(self) -> tuple[StockPosition, ...]:
        rows = self.session.query(PaperPosition).filter_by(status="open").all()
        positions = [
            StockPosition(
                ticker=row.ticker,
                quantity=float(row.quantity),
                average_cost=float(row.average_cost),
                market_price=float(row.market_price),
                market_value=float(row.market_value),
                trade_identity=row.trade_identity,
                strategy_id=row.strategy_id,
                opened_at=row.opened_at,
                updated_at=row.updated_at,
                direction=row.direction,
            )
            for row in rows
        ]
        return tuple(sorted(positions, key=lambda item: item.ticker))

    def replace_paper_positions(self, positions: tuple[StockPosition, ...] | list[StockPosition]) -> None:
        latest_by_ticker = {position.ticker: position for position in positions}
        existing_rows = self.session.query(PaperPosition).all()
        open_rows_by_ticker = {row.ticker: row for row in existing_rows if row.status == "open"}

        for ticker, position in latest_by_ticker.items():
            row = open_rows_by_ticker.get(ticker)
            if row is None:
                row = PaperPosition(
                    paper_position_id=uuid.uuid4(),
                    ticker=ticker,
                )
                self.session.add(row)
            row.strategy_id = position.strategy_id
            row.trade_identity = position.trade_identity
            row.direction = position.direction
            row.quantity = Decimal(str(position.quantity))
            row.average_cost = Decimal(str(position.average_cost))
            row.market_price = Decimal(str(position.market_price))
            row.market_value = Decimal(str(position.market_value))
            row.opened_at = position.opened_at
            row.updated_at = position.updated_at
            row.closed_at = None
            row.status = "open"

        for row in existing_rows:
            if row.status != "open":
                continue
            if row.ticker in latest_by_ticker:
                continue
            row.status = "closed"
            row.closed_at = row.updated_at
            row.updated_at = row.updated_at

        self.session.flush()

    def save_paper_option_position(self, position: PaperOptionPosition) -> None:
        row = self.session.query(PaperOptionPositionModel).filter_by(
            paper_option_position_id=_to_uuid(position.paper_option_position_id)
        ).one_or_none()
        if row is None:
            row = PaperOptionPositionModel(paper_option_position_id=_to_uuid(position.paper_option_position_id))
            self.session.add(row)
        row.option_strategy_decision_id = _to_uuid_or_none(position.option_strategy_decision_id)
        row.ticker = position.ticker
        row.strategy_id = position.strategy_id
        row.option_strategy_type = position.option_strategy_type
        row.trade_identity = position.trade_identity
        row.quantity = int(position.quantity)
        row.opened_at = position.opened_at
        row.updated_at = position.updated_at
        row.status = position.status
        row.expiry = position.expiry
        row.max_loss = Decimal(str(position.max_loss))
        row.margin_requirement = Decimal(str(position.margin_requirement))
        row.buying_power_effect = Decimal(str(position.buying_power_effect))
        row.assignment_notional = Decimal(str(position.assignment_notional))
        row.metadata_json = dict(position.metadata_json)
        self.session.flush()

    def load_paper_option_positions(self) -> tuple[PaperOptionPosition, ...]:
        rows = self.session.query(PaperOptionPositionModel).filter_by(status="open").all()
        positions = [
            PaperOptionPosition(
                paper_option_position_id=str(row.paper_option_position_id),
                option_strategy_decision_id=str(row.option_strategy_decision_id),
                ticker=row.ticker,
                strategy_id=row.strategy_id,
                option_strategy_type=row.option_strategy_type,
                trade_identity=row.trade_identity,
                quantity=int(row.quantity),
                opened_at=row.opened_at,
                updated_at=row.updated_at,
                status=row.status,
                expiry=row.expiry,
                max_loss=float(row.max_loss),
                margin_requirement=float(row.margin_requirement),
                buying_power_effect=float(row.buying_power_effect),
                assignment_notional=float(row.assignment_notional),
                metadata_json=dict(row.metadata_json or {}),
            )
            for row in rows
        ]
        return tuple(positions)

    def save_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        row = PortfolioSnapshotModel(
            portfolio_snapshot_id=uuid.uuid4(),
            snapshot_time=snapshot.as_of,
            cash_balance=Decimal(str(snapshot.cash_balance)),
            account_equity=Decimal(str(snapshot.account_equity)),
            net_liquidation_value=Decimal(str(snapshot.net_liquidation_value)),
            buying_power=Decimal(str(snapshot.buying_power)),
            excess_liquidity=Decimal(str(snapshot.excess_liquidity)),
            stock_market_value=Decimal(str(snapshot.stock_market_value)),
            option_market_value=Decimal(str(snapshot.option_market_value)),
            stock_margin_requirement=Decimal(str(snapshot.stock_margin_requirement)),
            option_margin_requirement=Decimal(str(snapshot.option_margin_requirement)),
            total_margin_requirement=Decimal(str(snapshot.total_margin_requirement)),
            initial_margin_requirement=Decimal(str(snapshot.initial_margin_requirement)),
            maintenance_margin_requirement=Decimal(str(snapshot.maintenance_margin_requirement)),
            margin_model_profile=snapshot.margin_model_profile,
            margin_model_version=snapshot.margin_model_version,
            margin_requirement_source=snapshot.margin_requirement_source,
            day_pnl=Decimal(str(snapshot.day_pnl)),
            realized_pnl=Decimal(str(snapshot.realized_pnl)),
            unrealized_pnl=Decimal(str(snapshot.unrealized_pnl)),
            metadata_json=dict(snapshot.metadata_json),
        )
        self.session.add(row)
        self.session.flush()


SqlAlchemyTradingRepository = SQLAlchemyTradingRepository


def _to_uuid(value: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, str(value))


def _to_uuid_or_none(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    return _to_uuid(value)


def _decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
