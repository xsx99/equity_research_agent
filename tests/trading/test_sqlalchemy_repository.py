from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from src.trading.paper_stock_broker import PaperExecutionRecord, PaperOrderRecord
from src.trading.portfolio.state import PortfolioSnapshot, StockPosition
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
from src.trading.workflows.paper_execution import PaperExecutionWorkflow
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.risk import RiskDecisionRecord
from src.trading.workflows.trading_decision import TradingDecisionRecord


class _FakeQuery:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def filter_by(self, **kwargs: Any) -> "_FakeQuery":
        filtered = [
            row
            for row in self._rows
            if all(getattr(row, key) == value for key, value in kwargs.items())
        ]
        return _FakeQuery(filtered)

    def all(self) -> list[object]:
        return list(self._rows)

    def one_or_none(self) -> object | None:
        if not self._rows:
            return None
        if len(self._rows) > 1:
            raise AssertionError("expected at most one row")
        return self._rows[0]


class _FakeSession:
    def __init__(self) -> None:
        self.rows_by_type: dict[type, list[object]] = {}
        self.flush_calls = 0

    def add(self, row: object) -> None:
        self.rows_by_type.setdefault(type(row), []).append(row)

    def query(self, model: type) -> _FakeQuery:
        return _FakeQuery(self.rows_by_type.get(model, []))

    def flush(self) -> None:
        self.flush_calls += 1


def test_sqlalchemy_repository_persists_pr6_order_execution_snapshot_and_positions():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    order = PaperOrderRecord(
        paper_order_id="order-1",
        broker_order_id="broker-order-1",
        client_order_id="2026-06-02:AAPL:relative_strength_rotation_v1:enter_long",
        trading_decision_id="decision-1",
        risk_decision_id="risk-1",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        action="enter_long",
        trade_date=date(2026, 6, 2),
        quantity=0.01,
        limit_price=227.15,
        status="filled",
        rejection_reason=None,
        created_at=now,
    )
    execution = PaperExecutionRecord(
        paper_execution_id="execution-1",
        paper_order_id="order-1",
        broker_order_id="broker-order-1",
        ticker="AAPL",
        quantity=0.01,
        fill_price=227.15,
        trade_date=date(2026, 6, 2),
        executed_at=now,
        net_cash_effect=-2.2715,
    )
    snapshot = PortfolioSnapshot(
        as_of=now,
        cash_balance=999997.73,
        account_equity=1000000.12,
        net_liquidation_value=1000000.12,
        buying_power=1999995.46,
        excess_liquidity=999999.44,
        stock_market_value=2.27,
        option_market_value=0.0,
        stock_margin_requirement=1.14,
        option_margin_requirement=0.0,
        total_margin_requirement=1.14,
        initial_margin_requirement=1.14,
        maintenance_margin_requirement=0.68,
        margin_model_profile="alpaca_paper_account",
        margin_model_version="broker",
        margin_requirement_source="broker_reported",
        day_pnl=0.12,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        metadata_json={"broker": "alpaca"},
    )
    positions = (
        StockPosition(
            ticker="AAPL",
            quantity=0.01,
            average_cost=227.15,
            market_price=227.27,
            market_value=2.27,
            trade_identity="tactical_stock_trade",
            strategy_id="relative_strength_rotation_v1",
            opened_at=now,
            updated_at=now,
            direction="long",
        ),
    )

    repository.save_paper_order(order)
    repository.save_paper_order(order)
    repository.save_paper_execution(execution)
    repository.replace_paper_positions(positions)
    repository.save_portfolio_snapshot(snapshot)

    open_positions = repository.load_paper_positions()

    assert repository.has_paper_execution("execution-1") is True
    assert len(open_positions) == 1
    assert open_positions[0].ticker == "AAPL"
    assert open_positions[0].strategy_id == "relative_strength_rotation_v1"
    assert session.flush_calls >= 4


def test_sqlalchemy_repository_closes_missing_positions_on_replace():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    repository.replace_paper_positions(
        (
            StockPosition(
                ticker="AAPL",
                quantity=0.01,
                average_cost=227.15,
                market_price=227.27,
                market_value=2.27,
                trade_identity="tactical_stock_trade",
                strategy_id="relative_strength_rotation_v1",
                opened_at=now,
                updated_at=now,
                direction="long",
            ),
        )
    )
    repository.replace_paper_positions(())

    assert repository.load_paper_positions() == ()


class _BrokerStub:
    def submit_order(self, request: Any) -> Any:
        return type(
            "Order",
            (),
            {
                "paper_order_id": "paper-order-1",
                "broker_order_id": "broker-order-1",
                "client_order_id": "2026-06-02:AAPL:relative_strength_rotation_v1:enter_long",
                "trading_decision_id": request.trading_decision_id,
                "risk_decision_id": request.risk_decision_id,
                "ticker": request.ticker,
                "strategy_id": request.strategy_id,
                "action": request.action,
                "trade_date": request.trade_date,
                "quantity": request.quantity,
                "limit_price": None,
                "status": "filled",
                "rejection_reason": None,
                "created_at": datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
            },
        )()

    def find_execution_by_order_id(self, paper_order_id: str) -> Any:
        return PaperExecutionRecord(
            paper_execution_id="execution-1",
            paper_order_id=paper_order_id,
            broker_order_id="broker-order-1",
            ticker="AAPL",
            quantity=0.01,
            fill_price=227.15,
            trade_date=date(2026, 6, 2),
            executed_at=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
            net_cash_effect=-2.2715,
        )

    def sync_account(self) -> dict[str, Any]:
        return {
            "cash": "999997.73",
            "equity": "1000000.12",
            "portfolio_value": "1000000.12",
            "buying_power": "1999995.46",
            "long_market_value": "2.27",
            "initial_margin": "1.14",
            "maintenance_margin": "0.68",
            "last_equity": "1000000.00",
        }

    def sync_positions(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "avg_entry_price": "227.15",
                "current_price": "227.27",
                "market_value": "2.27",
                "side": "long",
            }
        ]


def test_paper_execution_workflow_persists_into_sqlalchemy_repository():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=_BrokerStub(),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    trading_decision = TradingDecisionRecord(
        trading_decision_id="decision-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        risk_decision_id="risk-1",
        ticker="AAPL",
        decision="enter_long",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        selection_source="scanner",
        manual_request_id=None,
        confidence=0.78,
        target_weight=0.05,
        approved_weight=0.04,
        max_loss_pct=0.02,
        time_horizon="2w-3m",
        thesis="Relative strength remains intact.",
        invalidators=["trend break"],
        prompt_template=object(),
        prompt_run=object(),
        usage_events=[],
        decision_time=now,
        available_for_decision_at=now,
        metadata_json={"paper_trade_authorized": True},
    )
    risk_decision = RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="AAPL",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.000002,
        approved_notional=2.27,
        approved_quantity=0.01,
        portfolio_risk_snapshot_id="portfolio-risk-1",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )

    result = workflow.run(
        trading_decisions=(trading_decision,),
        risk_decisions=(risk_decision,),
        trade_date=now,
    )

    assert len(result.paper_orders) == 1
    assert repository.has_paper_execution("execution-1") is True
    assert repository.load_paper_positions()[0].ticker == "AAPL"
