"""SQLAlchemy-backed persistence for trading artifacts."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from src.db.models.trading import PaperExecution, PaperOrder, PaperPosition, PortfolioSnapshot as PortfolioSnapshotModel
from src.trading.paper_stock_broker import PaperExecutionRecord, PaperOrderRecord
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

    def has_paper_execution(self, paper_execution_id: str) -> bool:
        return self.session.query(PaperExecution).filter_by(
            paper_execution_id=_to_uuid(paper_execution_id)
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
