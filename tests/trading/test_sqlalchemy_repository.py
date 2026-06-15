from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from src.db.models.trading import (
    OptionStrategyLeg,
    PaperOptionExecution,
    PaperOptionOrder,
    RiskDecision,
    UniverseFilterConfig,
    UniverseSnapshot,
    UniverseSymbol,
)
from src.trading.data_sources.universe import UniverseAsset, UniverseFilterConfig as UniverseFilterConfigRecord
from src.trading.data_sources.universe import UniverseSnapshotResult, UniverseSymbolDecision
from src.trading.brokers.paper_option import PaperOptionExecutionRecord, PaperOptionOrderRecord, PaperOptionPosition
from src.trading.brokers.paper_stock import PaperExecutionRecord, PaperOrderRecord
from src.trading.risk.context import PortfolioRiskSnapshotRecord, PositionSizingDecisionRecord, RiskFactorExposureRecord
from src.trading.risk.hedges import RiskHedgeDecisionRecord
from src.trading.risk.options import OptionRiskSnapshotRecord
from src.trading.options.strategy import OptionStrategyDecisionRecord, OptionStrategyLegRecord
from src.trading.portfolio.state import PortfolioSnapshot, StockPosition
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository, _trading_decision_payload
from src.trading.workflows.paper_execution import PaperExecutionWorkflow
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.risk import HedgeActionRecord, PortfolioRiskIntentRecord, PositionRiskActionRecord, RiskDecisionRecord
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


def test_sqlalchemy_repository_persists_universe_snapshot_and_symbols():
    now = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    filter_id = uuid.uuid4()
    session.add(
        UniverseFilterConfig(
            universe_filter_config_id=filter_id,
            profile_name="default",
            version=1,
            is_active=True,
            min_price=5,
            min_avg_dollar_volume=25_000_000,
            included_sectors_json=[],
            excluded_sectors_json=[],
            included_industries_json=[],
            excluded_industries_json=[],
            exchanges_json=[],
            asset_types_json=["common_stock"],
            manual_include_json=["AAPL"],
            manual_exclude_json=[],
        )
    )
    snapshot = UniverseSnapshotResult(
        snapshot_id=str(uuid.uuid4()),
        snapshot_time=now,
        filter_config=UniverseFilterConfigRecord(profile_name="default", version=1, manual_include=("AAPL",)),
        included=(
            UniverseSymbolDecision(
                symbol="AAPL",
                status="included",
                exclusion_reason=None,
                asset=UniverseAsset(
                    symbol="AAPL",
                    company_name="Apple Inc.",
                    asset_type="common_stock",
                    exchange="NASDAQ",
                    sector="Technology",
                    industry="Consumer Electronics",
                    price=200.0,
                    avg_dollar_volume=100_000_000.0,
                ),
            ),
        ),
        excluded=(
            UniverseSymbolDecision(
                symbol="XYZ",
                status="excluded",
                exclusion_reason="below_min_price",
                asset=UniverseAsset(
                    symbol="XYZ",
                    company_name="Example Co.",
                    asset_type="common_stock",
                    exchange="NASDAQ",
                    sector="Technology",
                    industry="Software",
                    price=2.0,
                    avg_dollar_volume=10_000_000.0,
                ),
            ),
        ),
        metadata={"provider": "alpaca_live"},
    )

    repository.save_universe_snapshot(snapshot)

    persisted_snapshot = session.query(UniverseSnapshot).one_or_none()
    persisted_symbols = session.query(UniverseSymbol).all()
    assert persisted_snapshot is not None
    assert persisted_snapshot.provider == "alpaca_live"
    assert persisted_snapshot.universe_filter_config_id == filter_id
    assert len(persisted_symbols) == 2


def test_trading_decision_payload_includes_rationale_fields_for_reflection_consumers():
    now = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    row = SimpleNamespace(
        ticker="NVDA",
        decision="enter_long",
        strategy_id="relative_strength_rotation_v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        selection_source="scanner",
        confidence=Decimal("0.74"),
        target_weight=Decimal("0.04"),
        approved_weight=Decimal("0.04"),
        decision_time=now,
        key_drivers_json=["sector_relative_strength", "relative_volume"],
        counterarguments_json=["valuation is elevated versus peers"],
        invalidators_json=["QQQ closes below prior close"],
        metadata_json={"paper_trade_authorized": True},
    )

    payload = _trading_decision_payload(row)

    assert payload["key_drivers"] == ["sector_relative_strength", "relative_volume"]
    assert payload["counterarguments"] == ["valuation is elevated versus peers"]
    assert payload["invalidators"] == ["QQQ closes below prior close"]


def test_sqlalchemy_repository_persists_pr4_risk_artifacts():
    now = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    portfolio_snapshot = PortfolioRiskSnapshotRecord(
        portfolio_risk_snapshot_id="risk-snapshot-1",
        decision_time=now,
        risk_appetite="balanced",
        resolver_version="v1",
        margin_model_profile="alpaca_paper_account",
        margin_model_version="broker",
        account_equity=100000.0,
        cash_balance=50000.0,
        buying_power=100000.0,
        excess_liquidity=50000.0,
        stock_margin_requirement=1000.0,
        option_margin_requirement=0.0,
        total_margin_requirement=1000.0,
        initial_margin_requirement=1000.0,
        maintenance_margin_requirement=500.0,
        margin_requirement_source="broker_reported",
        net_exposure=10000.0,
        gross_exposure=10000.0,
        beta_adjusted_net_exposure=9000.0,
        concentration_flags=["single_name_warning"],
        metadata_json={"macro_regime": "risk_on"},
    )
    exposures = (
        RiskFactorExposureRecord(
            factor_type="sector",
            factor_value="technology",
            gross_exposure=10000.0,
            net_exposure=10000.0,
            long_exposure=10000.0,
            short_exposure=0.0,
            position_count=1,
            metadata_json={},
        ),
    )
    sizing = PositionSizingDecisionRecord(
        position_sizing_decision_id="sizing-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        ticker="AAPL",
        risk_appetite="balanced",
        base_weight=0.05,
        volatility_adjusted_weight=0.04,
        liquidity_capped_weight=0.04,
        final_weight=0.04,
        final_notional=4000.0,
        applied_caps=["liquidity_cap"],
        binding_constraint="liquidity_cap",
        decision_time=now,
        metadata_json={},
    )
    risk_decision = RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="AAPL",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.04,
        approved_notional=4000.0,
        approved_quantity=20.0,
        portfolio_risk_snapshot_id="risk-snapshot-1",
        applied_rules=["liquidity_cap"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )

    repository.save_portfolio_risk_snapshot(portfolio_snapshot)
    repository.save_risk_factor_exposures(exposures)
    repository.save_position_sizing_decision(sizing)
    repository.save_risk_decision(risk_decision)

    assert session.flush_calls >= 4


def test_sqlalchemy_repository_persists_lookahead_risk_audit_fields_in_metadata():
    now = datetime(2026, 6, 13, 12, 45, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    risk_decision = RiskDecisionRecord(
        risk_decision_id="risk-lookahead-1",
        candidate_score_id=None,
        trade_classification_id=None,
        position_sizing_decision_id=None,
        ticker="NVDA",
        status="approved",
        reason_code="own_event_force_reduce",
        approved_weight=0.02,
        approved_notional=2000.0,
        approved_quantity=10.0,
        portfolio_risk_snapshot_id=None,
        applied_rules=["portfolio_risk_intent"],
        generated_hedge_action={"reason_code": "macro_high_overlay"},
        decision_time=now,
        binding_constraint="own_event_force_reduce",
        lookahead_risk_source="own_event",
        metadata_json={},
    )

    repository.save_risk_decision(risk_decision)

    stored = session.rows_by_type[RiskDecision][0]

    assert stored.metadata_json["binding_constraint"] == "own_event_force_reduce"
    assert stored.metadata_json["lookahead_risk_source"] == "own_event"
    assert stored.generated_hedge_action_json["reason_code"] == "macro_high_overlay"


def test_sqlalchemy_repository_round_trips_portfolio_risk_intent():
    now = datetime(2026, 6, 13, 12, 45, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    portfolio_snapshot = PortfolioRiskSnapshotRecord(
        portfolio_risk_snapshot_id="risk-snapshot-1",
        decision_time=now,
        risk_appetite="balanced",
        resolver_version="v1",
        margin_model_profile="alpaca_paper_account",
        margin_model_version="broker",
        account_equity=100000.0,
        cash_balance=50000.0,
        buying_power=100000.0,
        excess_liquidity=50000.0,
        stock_margin_requirement=1000.0,
        option_margin_requirement=0.0,
        total_margin_requirement=1000.0,
        initial_margin_requirement=1000.0,
        maintenance_margin_requirement=500.0,
        margin_requirement_source="broker_reported",
        net_exposure=10000.0,
        gross_exposure=10000.0,
        beta_adjusted_net_exposure=9000.0,
        concentration_flags=["single_name_warning"],
        metadata_json={"macro_regime": "risk_on"},
    )
    intent = PortfolioRiskIntentRecord.create(
        portfolio_risk_snapshot_id="risk-snapshot-1",
        decision_time=now,
        risk_window="1-5d",
        aggregate_risk_state="mixed_risk",
        position_actions=(
            PositionRiskActionRecord(
                ticker="NVDA",
                trade_identity="tactical_stock_trade",
                action="block_open",
                risk_source="own_event",
                severity="high",
                max_allowed_weight_override=None,
                reason_code="own_event_block",
                metadata_json={"days_until_event": 2},
            ),
        ),
        hedge_actions=(
            HedgeActionRecord(
                action="open_hedge",
                risk_source="macro",
                severity="watch",
                target_underlier="QQQ",
                target_exposure_type="broad_market",
                coverage_ratio=0.25,
                reason_code="macro_watch_overlay",
                metadata_json={},
            ),
        ),
        binding_constraints=("own_event_block", "macro_watch_overlay"),
        metadata_json={"source": "planner"},
    )

    repository.save_portfolio_risk_snapshot(portfolio_snapshot)
    repository.save_portfolio_risk_intent(intent)
    loaded = repository.load_portfolio_risk_intents(trade_date=now.date())

    assert len(loaded) == 1
    assert loaded[0].portfolio_risk_snapshot_id == str(uuid.uuid5(uuid.NAMESPACE_URL, "risk-snapshot-1"))
    assert loaded[0].position_actions[0].action == "block_open"
    assert loaded[0].hedge_actions[0].target_underlier == "QQQ"


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


def test_sqlalchemy_repository_persists_pr7_option_artifacts():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    repository.save_option_strategy_decision(
        OptionStrategyDecisionRecord(
            option_strategy_decision_id="option-decision-1",
            trading_decision_id="decision-1",
            ticker="NVDA",
            trade_identity="tactical_option_trade",
            decision_action="open_option_strategy",
            option_strategy_type="put_credit_spread",
            status="ready",
            rejection_reason=None,
            strategy_id="earnings_drift_v1",
            strategy_version="v1",
            expression_bucket_id="defined_risk_income_spread",
            expression_bucket_version="v1",
            underlying_price=118.0,
            expiry=date(2026, 7, 17),
            net_debit_or_credit=-1.5,
            max_loss=500.0,
            max_profit=150.0,
            breakevens=(108.5,),
            margin_requirement=500.0,
            buying_power_effect=500.0,
            assignment_notional=11_000.0,
            portfolio_delta=-0.11,
            portfolio_gamma=0.01,
            portfolio_theta=0.01,
            portfolio_vega=-0.03,
            earnings_date=date(2026, 6, 20),
            event_through_expiry=True,
            strategy_pairing_method="vertical_by_expiry_and_width",
            assignment_plan="close_or_roll_before_expiry_if_itm",
            margin_model_profile="estimated_fidelity_like_conservative_v1",
            margin_model_version="v1",
            margin_requirement_source="simulated_formula",
            profit_target_pct=0.5,
            max_loss_rule="close_at_2x_credit",
            roll_conditions=("7_dte_if_otm",),
            close_conditions=("take_profit_50pct",),
            metadata_json={},
            created_at=now,
        )
    )
    repository.save_option_strategy_legs(
        (
            OptionStrategyLegRecord(
                option_strategy_leg_id="leg-1",
                option_strategy_decision_id="option-decision-1",
                ticker="NVDA",
                contract_symbol="NVDA260717P00110000",
                option_type="put",
                side="sell",
                quantity=1,
                ratio_qty=1,
                strike=110.0,
                expiry=date(2026, 7, 17),
                dte=45,
                delta=-0.28,
                gamma=0.02,
                theta=0.01,
                vega=-0.07,
                iv_rank=0.61,
                bid=1.4,
                ask=1.6,
                mid=1.5,
                chosen_price=1.5,
                created_at=now,
                implied_volatility=0.34,
            ),
        )
    )
    repository.save_paper_option_order(
        PaperOptionOrderRecord(
            paper_option_order_id="option-order-1",
            trading_decision_id="decision-1",
            risk_decision_id="risk-1",
            option_strategy_decision_id="option-decision-1",
            broker_order_id="alpaca-option-order-1",
            client_order_id="2026-06-02:NVDA:earnings_drift_v1:open_option_strategy",
            order_class="mleg",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="put_credit_spread",
            action="open_option_strategy",
            trade_identity="tactical_option_trade",
            trade_date=date(2026, 6, 2),
            quantity=1,
            limit_price=-1.5,
            status="filled",
            rejection_reason=None,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            created_at=now,
        )
    )
    repository.save_paper_option_execution(
        PaperOptionExecutionRecord(
            paper_option_execution_id="option-execution-1",
            paper_option_order_id="option-order-1",
            broker_order_id="alpaca-option-order-1",
            ticker="NVDA",
            quantity=1,
            fill_price=-1.5,
            trade_date=date(2026, 6, 2),
            executed_at=now,
            net_cash_effect=150.0,
        )
    )
    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="option-position-1",
            option_strategy_decision_id="option-decision-1",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="put_credit_spread",
            trade_identity="tactical_option_trade",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=date(2026, 7, 17),
            max_loss=500.0,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            assignment_notional=11_000.0,
            metadata_json={},
        )
    )
    repository.save_option_risk_snapshot(
        OptionRiskSnapshotRecord(
            option_risk_snapshot_id="risk-snapshot-1",
            ticker="NVDA",
            trade_identity="tactical_option_trade",
            option_strategy_type="put_credit_spread",
            underlying_price=118.0,
            portfolio_delta=-0.11,
            portfolio_gamma=0.01,
            portfolio_theta=0.01,
            portfolio_vega=-0.03,
            net_debit_or_credit=-1.5,
            max_loss=500.0,
            max_profit=150.0,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            assignment_notional=11_000.0,
            worst_case_assignment_notional=11_000.0,
            margin_model_profile="estimated_fidelity_like_conservative_v1",
            margin_model_version="v1",
            margin_requirement_source="simulated_formula",
            risk_status="approved",
            reason_code="within_limits",
            created_at=now,
            metadata_json={},
        )
    )
    repository.save_risk_hedge_decision(
        RiskHedgeDecisionRecord.create(
            risk_decision_id="risk-1",
            ticker="QQQ",
            action="open_option_strategy",
            option_strategy_type="long_put",
            rationale="risk_manager_generated_overlay",
            hedge_cost=250.0,
            protected_notional=20_000.0,
        )
    )

    assert repository.has_paper_option_execution("option-execution-1") is True
    assert repository.load_paper_option_positions()[0].ticker == "NVDA"
    persisted_leg = session.query(OptionStrategyLeg).one_or_none()
    assert persisted_leg is not None
    assert persisted_leg.contract_symbol == "NVDA260717P00110000"
    assert persisted_leg.ratio_qty == 1
    assert persisted_leg.implied_volatility == Decimal("0.34")
    persisted_order = session.query(PaperOptionOrder).one_or_none()
    assert persisted_order is not None
    assert persisted_order.client_order_id == "2026-06-02:NVDA:earnings_drift_v1:open_option_strategy"
    assert persisted_order.broker_order_id == "alpaca-option-order-1"
    assert persisted_order.order_class == "mleg"
    persisted_execution = session.query(PaperOptionExecution).one_or_none()
    assert persisted_execution is not None
    assert persisted_execution.broker_order_id == "alpaca-option-order-1"


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


def test_load_intraday_request_contexts_includes_option_execution_metadata():
    now = datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    repository.save_trading_decision(
        TradingDecisionRecord(
            trading_decision_id="qqq-option-decision",
            candidate_score_id="qqq-candidate",
            trade_classification_id="qqq-classification",
            risk_decision_id="qqq-risk",
            ticker="QQQ",
            decision="open_option_strategy",
            strategy_id="risk_manager_hedge_overlay_v1",
            strategy_version="v1",
            expression_bucket_id="defined_risk_directional_option",
            expression_bucket_version="v1",
            trade_identity="risk_hedge_overlay",
            instrument_type="option",
            selection_source="risk_manager",
            manual_request_id=None,
            confidence=0.55,
            target_weight=0.0,
            approved_weight=0.0,
            max_loss_pct=0.02,
            time_horizon="1w-4w",
            thesis="Macro hedge remains active.",
            invalidators=["macro risk normalized"],
            prompt_template=object(),
            prompt_run=object(),
            usage_events=[],
            decision_time=now,
            available_for_decision_at=now,
            metadata_json={
                "paper_trade_authorized": True,
                "option_strategy": {
                    "option_strategy_type": "long_put",
                    "underlying_price": 500.0,
                    "net_debit_or_credit": 3.2,
                },
            },
        )
    )
    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="qqq-open-position",
            option_strategy_decision_id="qqq-option-strategy",
            ticker="QQQ",
            strategy_id="risk_manager_hedge_overlay_v1",
            option_strategy_type="long_put",
            trade_identity="risk_hedge_overlay",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=now.date(),
            max_loss=320.0,
            margin_requirement=320.0,
            buying_power_effect=320.0,
            assignment_notional=50000.0,
            metadata_json={"protected_notional": 25000.0},
        )
    )

    expected_position_id = repository.load_paper_option_positions()[0].paper_option_position_id

    context = repository.load_intraday_request_contexts(
        tickers=("QQQ",),
        trade_date=now.date(),
    )["QQQ"]

    assert context.instrument_type == "option"
    assert context.trade_identity == "risk_hedge_overlay"
    assert context.metadata_json["option_strategy"]["option_strategy_type"] == "long_put"
    assert context.metadata_json["option_strategy_type"] == "long_put"
    assert context.metadata_json["paper_option_position_id"] == expected_position_id
