from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.brokers.paper_option import PaperOptionBroker
from src.trading.brokers.paper_stock import PaperOrderRequest, PaperStockBroker
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.risk import OptionRiskAssessment, RiskDecisionRecord
from src.trading.workflows.paper_execution import PaperExecutionWorkflow
from src.trading.workflows.trading_decision import TradingDecisionRecord


class _StubResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _CapturingClient:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []
        self.gets: list[dict[str, Any]] = []

    def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        self.posts.append({"url": url, "json": json, "headers": headers})
        return _StubResponse(
            {
                "id": "broker-order-1",
                "client_order_id": json["client_order_id"],
                "symbol": json["symbol"],
                "qty": json["qty"],
                "side": json["side"],
                "type": json["type"],
                "time_in_force": json["time_in_force"],
                "status": "accepted",
                "submitted_at": "2026-06-02T16:31:00+00:00",
            }
        )

    def get(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str]) -> _StubResponse:
        self.gets.append({"url": url, "params": params, "headers": headers})
        if url.endswith("/v2/orders:by_client_order_id"):
            client_order_id = (params or {})["client_order_id"]
            return _StubResponse(
                {
                    "id": "broker-order-1",
                    "client_order_id": client_order_id,
                    "symbol": "AAPL",
                    "qty": "0.01",
                    "filled_qty": "0.01",
                    "filled_avg_price": "227.15",
                    "side": "buy",
                    "type": "market",
                    "time_in_force": "day",
                    "status": "filled",
                    "submitted_at": "2026-06-02T16:31:00+00:00",
                    "filled_at": "2026-06-02T16:31:02+00:00",
                }
            )
        if url.endswith("/v2/account"):
            return _StubResponse(
                {
                    "cash": "999997.73",
                    "equity": "1000000.12",
                    "portfolio_value": "1000000.12",
                    "buying_power": "1999995.46",
                    "long_market_value": "2.27",
                    "initial_margin": "1.14",
                    "maintenance_margin": "0.68",
                    "last_equity": "1000000.00",
                }
            )
        if url.endswith("/v2/positions"):
            return _StubResponse(
                [
                    {
                        "symbol": "AAPL",
                        "qty": "0.01",
                        "avg_entry_price": "227.15",
                        "current_price": "227.27",
                        "market_value": "2.27",
                        "side": "long",
                    }
                ]
            )
        raise AssertionError(f"unexpected_get:{url}")


def _trading_decision(*, decision: str = "enter_long", manual_request_id: str | None = None) -> TradingDecisionRecord:
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    return TradingDecisionRecord(
        trading_decision_id="decision-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        risk_decision_id="risk-1",
        ticker="AAPL",
        decision=decision,
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        selection_source="manual_request" if manual_request_id else "scanner",
        manual_request_id=manual_request_id,
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


def _risk_decision(*, approved_quantity: float = 0.01, status: str = "approved") -> RiskDecisionRecord:
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    return RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="AAPL",
        status=status,
        reason_code="within_limits",
        approved_weight=0.000002,
        approved_notional=2.27,
        approved_quantity=approved_quantity,
        portfolio_risk_snapshot_id="portfolio-risk-1",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )


def test_paper_stock_broker_rejects_review_only_manual_request_without_hitting_broker():
    client = _CapturingClient()
    broker = PaperStockBroker(api_key="key", secret_key="secret", client=client)
    decision = _trading_decision(manual_request_id="manual-1")
    risk = _risk_decision()

    order = broker.submit_order(
        PaperOrderRequest.from_trading_decision(
            trading_decision=decision,
            risk_decision=risk,
            trade_date=decision.decision_time.date(),
            manual_request_mode="review_only",
        )
    )

    assert order.status == "rejected"
    assert order.rejection_reason == "manual_request_review_only"
    assert client.posts == []


def test_paper_stock_broker_submits_alpaca_market_day_order_and_reads_fill_by_client_order_id():
    client = _CapturingClient()
    broker = PaperStockBroker(api_key="key", secret_key="secret", client=client)
    decision = _trading_decision()
    risk = _risk_decision()

    order = broker.submit_order(
        PaperOrderRequest.from_trading_decision(
            trading_decision=decision,
            risk_decision=risk,
            trade_date=decision.decision_time.date(),
            manual_request_mode=None,
        )
    )
    execution = broker.find_execution_by_order_id(order.paper_order_id)

    assert client.posts[0]["url"] == "https://paper-api.alpaca.markets/v2/orders"
    assert client.posts[0]["json"] == {
        "symbol": "AAPL",
        "qty": "0.01",
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
        "client_order_id": "2026-06-02:AAPL:relative_strength_rotation_v1:enter_long",
    }
    assert client.gets[0]["url"] == "https://paper-api.alpaca.markets/v2/orders:by_client_order_id"
    assert client.gets[0]["params"] == {
        "client_order_id": "2026-06-02:AAPL:relative_strength_rotation_v1:enter_long"
    }
    assert order.status == "filled"
    assert order.broker_order_id == "broker-order-1"
    assert execution is not None
    assert execution.fill_price == 227.15
    assert execution.quantity == 0.01


def test_paper_stock_broker_submits_sell_order_for_exit_action():
    client = _CapturingClient()
    broker = PaperStockBroker(api_key="key", secret_key="secret", client=client)
    decision = _trading_decision(decision="exit")
    risk = _risk_decision()

    order = broker.submit_order(
        PaperOrderRequest.from_trading_decision(
            trading_decision=decision,
            risk_decision=risk,
            trade_date=decision.decision_time.date(),
            manual_request_mode=None,
        )
    )

    assert client.posts[0]["json"]["side"] == "sell"
    assert order.status == "filled"


def test_paper_execution_workflow_persists_broker_sourced_order_account_and_positions():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    result = workflow.run(
        trading_decisions=(_trading_decision(),),
        risk_decisions=(_risk_decision(),),
        trade_date=now,
    )

    assert len(result.paper_orders) == 1
    assert len(repository.paper_orders) == 1
    assert len(repository.paper_executions) == 1
    assert repository.paper_positions[0].ticker == "AAPL"
    assert repository.paper_positions[0].quantity == 0.01
    assert result.portfolio_snapshots[-1].cash_balance == 999997.73
    assert result.portfolio_snapshots[-1].buying_power == 1999995.46


def test_paper_execution_workflow_persists_option_artifacts_and_overlay():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=PaperOptionBroker(now=lambda: now),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )
    option_decision = TradingDecisionRecord(
        trading_decision_id="option-decision-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        risk_decision_id="risk-1",
        ticker="NVDA",
        decision="open_option_strategy",
        strategy_id="earnings_drift_v1",
        strategy_version="v1",
        expression_bucket_id="defined_risk_income_spread",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        instrument_type="option",
        selection_source="scanner",
        manual_request_id=None,
        confidence=0.78,
        target_weight=0.02,
        approved_weight=0.02,
        max_loss_pct=0.02,
        time_horizon="1w-4w",
        thesis="Defined-risk income spread.",
        invalidators=["itm_near_expiry"],
        prompt_template=object(),
        prompt_run=object(),
        usage_events=[],
        decision_time=now,
        available_for_decision_at=now,
        metadata_json={
            "paper_trade_authorized": True,
            "option_strategy": {
                "option_strategy_decision_id": "option-strategy-1",
                "option_strategy_type": "put_credit_spread",
                "underlying_price": 118.0,
                "net_debit_or_credit": -1.5,
                "max_loss": 500.0,
                "max_profit": 150.0,
                "breakevens": [108.5],
                "margin_requirement": 500.0,
                "buying_power_effect": 500.0,
                "assignment_notional": 11000.0,
                "portfolio_delta": -0.11,
                "portfolio_gamma": 0.01,
                "portfolio_theta": 0.01,
                "portfolio_vega": -0.03,
                "event_through_expiry": True,
                "strategy_pairing_method": "vertical_by_expiry_and_width",
                "assignment_plan": "close_or_roll_before_expiry_if_itm",
            },
        },
    )
    risk = _risk_decision(approved_quantity=1)

    workflow.run(
        trading_decisions=(option_decision,),
        risk_decisions=(risk,),
        trade_date=now,
    )

    assert len(repository.option_strategy_decisions) == 1
    assert len(repository.paper_option_orders) == 1
    assert len(repository.paper_option_positions) == 1
    assert len(repository.option_risk_snapshots) == 1


def test_paper_execution_workflow_falls_back_to_stock_when_option_expression_is_rejected():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=PaperOptionBroker(now=lambda: now),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )
    option_decision = TradingDecisionRecord(
        trading_decision_id="option-decision-2",
        candidate_score_id="candidate-2",
        trade_classification_id="classification-2",
        risk_decision_id="risk-1",
        ticker="NVDA",
        decision="open_option_strategy",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        instrument_type="option",
        selection_source="scanner",
        manual_request_id=None,
        confidence=0.78,
        target_weight=0.02,
        approved_weight=0.02,
        max_loss_pct=0.02,
        time_horizon="1w-4w",
        thesis="Option expression first, stock fallback if option plan fails.",
        invalidators=["price confirmation fails"],
        prompt_template=object(),
        prompt_run=object(),
        usage_events=[],
        decision_time=now,
        available_for_decision_at=now,
        context_snapshot_json={
            "candidate_context": {
                "strategy_run_id": "run-2",
                "direction": "bullish",
            },
            "classification_context": {
                "expression_fallback_plan": [
                    {
                        "expression_bucket_id": "defined_risk_directional_option",
                        "expression_bucket_version": "v1",
                        "trade_identity": "tactical_option_trade",
                        "instrument_type": "option",
                        "decision_action": "open_option_strategy",
                        "rank": 0,
                        "is_selected": True,
                    },
                    {
                        "expression_bucket_id": "long_stock",
                        "expression_bucket_version": "v1",
                        "trade_identity": "tactical_stock_trade",
                        "instrument_type": "stock",
                        "decision_action": "enter_long",
                        "rank": 1,
                        "is_selected": False,
                    },
                ]
            }
        },
        metadata_json={
            "paper_trade_authorized": True,
            "option_strategy": {
                "option_strategy_decision_id": "option-strategy-2",
                "option_strategy_type": "long_call",
                "status": "rejected",
                "rejection_reason": "missing_option_chain",
                "underlying_price": 118.0,
                "net_debit_or_credit": 2.2,
                "max_loss": 220.0,
                "max_profit": None,
                "breakevens": [120.2],
                "margin_requirement": 220.0,
                "buying_power_effect": 220.0,
                "assignment_notional": 0.0,
                "portfolio_delta": 0.32,
                "portfolio_gamma": 0.04,
                "portfolio_theta": -0.03,
                "portfolio_vega": 0.12,
                "event_through_expiry": True,
                "strategy_pairing_method": "single_leg",
                "assignment_plan": None,
            },
        },
    )
    risk = _risk_decision(approved_quantity=1)

    result = workflow.run(
        trading_decisions=(option_decision,),
        risk_decisions=(risk,),
        trade_date=now,
    )

    assert len(result.paper_orders) == 1
    assert len(repository.paper_orders) == 1
    assert repository.paper_orders[0].ticker == "NVDA"
    assert len(repository.paper_option_orders) == 0
    assert len(repository.option_strategy_decisions) == 1
    assert repository.option_strategy_decisions[0].status == "rejected"
    assert len(repository.trade_classifications) == 1
    assert repository.trade_classifications[0].trade_identity == "tactical_stock_trade"
    assert repository.trade_classifications[0].expression_bucket_id == "long_stock"
    assert len(repository.trading_decisions) == 1
    assert repository.trading_decisions[0].trade_identity == "tactical_stock_trade"
    assert repository.trading_decisions[0].instrument_type == "stock"
    assert repository.paper_orders[0].trading_decision_id == repository.trading_decisions[0].trading_decision_id


def test_paper_execution_workflow_reapproves_stock_fallback_before_submitting_order():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    captured_requests: list[dict[str, Any]] = []

    class _ConfigResolver:
        def resolve(self, **kwargs):
            return object()

    class _PositionSizer:
        def size_position(self, request, portfolio_context, config):
            del portfolio_context, config
            captured_requests.append(
                {
                    "instrument_type": request.instrument_type,
                    "trade_identity": request.classification.trade_identity,
                    "price": request.price,
                }
            )
            return type(
                "Sizing",
                (),
                {
                    "position_sizing_decision_id": "fallback-sizing-1",
                    "candidate_score_id": request.candidate.candidate_score_id,
                    "trade_classification_id": request.classification.trade_classification_id,
                    "ticker": request.candidate.ticker,
                    "risk_appetite": "balanced",
                    "base_weight": 0.03,
                    "volatility_adjusted_weight": 0.03,
                    "liquidity_capped_weight": 0.03,
                    "final_weight": 0.03,
                    "final_notional": 3000.0,
                    "applied_caps": [],
                    "binding_constraint": None,
                    "decision_time": now,
                    "metadata_json": {},
                },
            )()

    class _RiskManager:
        def evaluate(self, request, sizing, portfolio_context, config):
            del sizing, portfolio_context, config
            return RiskDecisionRecord(
                risk_decision_id="fallback-risk-1",
                candidate_score_id=request.candidate.candidate_score_id,
                trade_classification_id=request.classification.trade_classification_id,
                position_sizing_decision_id="fallback-sizing-1",
                ticker="NVDA",
                status="approved",
                reason_code="fallback_within_limits",
                approved_weight=0.03,
                approved_notional=3000.0,
                approved_quantity=3.0,
                portfolio_risk_snapshot_id="portfolio-risk-fallback-1",
                applied_rules=["fallback_stock_reapproval"],
                generated_hedge_action=None,
                decision_time=now,
                metadata_json={},
            )

    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=PaperOptionBroker(now=lambda: now),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
        config_resolver=_ConfigResolver(),
        position_sizer=_PositionSizer(),
        risk_manager=_RiskManager(),
    )
    option_decision = TradingDecisionRecord(
        trading_decision_id="option-decision-3",
        candidate_score_id="candidate-2",
        trade_classification_id="classification-2",
        risk_decision_id="risk-1",
        ticker="NVDA",
        decision="open_option_strategy",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        instrument_type="option",
        selection_source="scanner",
        manual_request_id=None,
        confidence=0.78,
        target_weight=0.02,
        approved_weight=0.02,
        max_loss_pct=0.02,
        time_horizon="1w-4w",
        thesis="Option expression first, stock fallback if option plan fails.",
        invalidators=["price confirmation fails"],
        prompt_template=object(),
        prompt_run=object(),
        usage_events=[],
        decision_time=now,
        available_for_decision_at=now,
        context_snapshot_json={
            "candidate_context": {"candidate_score": 0.78},
            "classification_context": {
                "expression_fallback_plan": [
                    {
                        "expression_bucket_id": "defined_risk_directional_option",
                        "expression_bucket_version": "v1",
                        "trade_identity": "tactical_option_trade",
                        "instrument_type": "option",
                        "decision_action": "open_option_strategy",
                        "rank": 0,
                        "is_selected": True,
                    },
                    {
                        "expression_bucket_id": "long_stock",
                        "expression_bucket_version": "v1",
                        "trade_identity": "tactical_stock_trade",
                        "instrument_type": "stock",
                        "decision_action": "enter_long",
                        "rank": 1,
                        "is_selected": False,
                    },
                ]
            },
            "risk_context": {"approved_weight": 0.02},
        },
        metadata_json={
            "paper_trade_authorized": True,
            "option_strategy": {
                "option_strategy_decision_id": "option-strategy-3",
                "option_strategy_type": "long_call",
                "status": "rejected",
                "rejection_reason": "missing_option_chain",
                "underlying_price": 118.0,
                "net_debit_or_credit": 2.2,
                "max_loss": 220.0,
                "max_profit": None,
                "breakevens": [120.2],
                "margin_requirement": 220.0,
                "buying_power_effect": 220.0,
                "assignment_notional": 0.0,
                "portfolio_delta": 0.32,
                "portfolio_gamma": 0.04,
                "portfolio_theta": -0.03,
                "portfolio_vega": 0.12,
                "event_through_expiry": True,
                "strategy_pairing_method": "single_leg",
                "assignment_plan": None,
            },
        },
    )
    risk = _risk_decision(approved_quantity=1)

    workflow.run(
        trading_decisions=(option_decision,),
        risk_decisions=(risk,),
        trade_date=now,
    )

    assert captured_requests == [
        {
            "instrument_type": "stock",
            "trade_identity": "tactical_stock_trade",
            "price": 118.0,
        }
    ]
    assert len(repository.paper_orders) == 1
    assert repository.paper_orders[0].quantity == 3.0
    assert len(repository.risk_decisions) == 1
    assert repository.risk_decisions[0].risk_decision_id == "fallback-risk-1"


def test_paper_execution_workflow_reapproves_option_fallback_before_submitting_option_order():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    captured_requests: list[dict[str, Any]] = []
    captured_option_risk_inputs: list[dict[str, Any]] = []

    class _ConfigResolver:
        def resolve(self, **kwargs):
            return object()

    class _PositionSizer:
        def size_position(self, request, portfolio_context, config):
            del portfolio_context, config
            captured_requests.append(
                {
                    "instrument_type": request.instrument_type,
                    "trade_identity": request.classification.trade_identity,
                    "price": request.price,
                    "estimated_margin_requirement": request.estimated_margin_requirement,
                }
            )
            return type(
                "Sizing",
                (),
                {
                    "position_sizing_decision_id": "fallback-option-sizing-1",
                    "candidate_score_id": request.candidate.candidate_score_id,
                    "trade_classification_id": request.classification.trade_classification_id,
                    "ticker": request.candidate.ticker,
                    "risk_appetite": "balanced",
                    "base_weight": 0.02,
                    "volatility_adjusted_weight": 0.02,
                    "liquidity_capped_weight": 0.02,
                    "final_weight": 0.02,
                    "final_notional": 2000.0,
                    "applied_caps": [],
                    "binding_constraint": None,
                    "decision_time": now,
                    "metadata_json": {},
                },
            )()

    class _RiskManager:
        def evaluate(self, request, sizing, portfolio_context, config):
            del sizing, portfolio_context, config
            return RiskDecisionRecord(
                risk_decision_id="fallback-option-risk-1",
                candidate_score_id=request.candidate.candidate_score_id,
                trade_classification_id=request.classification.trade_classification_id,
                position_sizing_decision_id="fallback-option-sizing-1",
                ticker="NVDA",
                status="approved",
                reason_code="fallback_option_within_limits",
                approved_weight=0.02,
                approved_notional=2000.0,
                approved_quantity=2.0,
                portfolio_risk_snapshot_id="portfolio-risk-fallback-option-1",
                applied_rules=["fallback_option_reapproval"],
                generated_hedge_action=None,
                decision_time=now,
                metadata_json={},
            )

    class _OptionRiskManager:
        def evaluate_assignment_risk(self, option_risk, *, portfolio_context, config):
            del portfolio_context, config
            captured_option_risk_inputs.append(
                {
                    "option_strategy_type": option_risk.option_strategy_type,
                    "leg_quantities": [leg.quantity for leg in option_risk.legs],
                    "margin_requirement": option_risk.margin_requirement,
                }
            )
            return OptionRiskAssessment(
                status="approved",
                reason_code="within_limits",
                worst_case_assignment_notional=0.0,
                portfolio_delta=0.12,
                portfolio_gamma=0.05,
                portfolio_theta=-0.02,
                portfolio_vega=0.21,
            )

    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=PaperOptionBroker(now=lambda: now),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
        config_resolver=_ConfigResolver(),
        position_sizer=_PositionSizer(),
        risk_manager=_RiskManager(),
        option_risk_manager=_OptionRiskManager(),
    )
    option_decision = TradingDecisionRecord(
        trading_decision_id="option-decision-4",
        candidate_score_id="candidate-4",
        trade_classification_id="classification-4",
        risk_decision_id="risk-1",
        ticker="NVDA",
        decision="open_option_strategy",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        instrument_type="option",
        selection_source="scanner",
        manual_request_id=None,
        confidence=0.78,
        target_weight=0.02,
        approved_weight=0.02,
        max_loss_pct=0.02,
        time_horizon="1w-4w",
        thesis="Primary option fails, fallback option should reapprove and execute.",
        invalidators=["price confirmation fails"],
        prompt_template=object(),
        prompt_run=object(),
        usage_events=[],
        decision_time=now,
        available_for_decision_at=now,
        context_snapshot_json={
            "candidate_context": {
                "candidate_score": 0.78,
                "strategy_run_id": "run-4",
                "direction": "bullish",
            },
            "classification_context": {
                "expression_fallback_plan": [
                    {
                        "expression_bucket_id": "defined_risk_directional_option",
                        "expression_bucket_version": "v1",
                        "trade_identity": "tactical_option_trade",
                        "instrument_type": "option",
                        "decision_action": "open_option_strategy",
                        "rank": 0,
                        "is_selected": True,
                    },
                    {
                        "expression_bucket_id": "volatility_event_option",
                        "expression_bucket_version": "v1",
                        "trade_identity": "tactical_option_trade",
                        "instrument_type": "option",
                        "decision_action": "open_option_strategy",
                        "rank": 1,
                        "is_selected": False,
                    },
                    {
                        "expression_bucket_id": "long_stock",
                        "expression_bucket_version": "v1",
                        "trade_identity": "tactical_stock_trade",
                        "instrument_type": "stock",
                        "decision_action": "enter_long",
                        "rank": 2,
                        "is_selected": False,
                    },
                ]
            },
            "risk_context": {"approved_weight": 0.02},
        },
        metadata_json={
            "paper_trade_authorized": True,
            "option_strategy": {
                "option_strategy_decision_id": "option-strategy-4a",
                "option_strategy_type": "long_call",
                "status": "rejected",
                "rejection_reason": "missing_option_chain",
                "underlying_price": 118.0,
                "net_debit_or_credit": 2.2,
                "max_loss": 220.0,
                "max_profit": None,
                "breakevens": [120.2],
                "margin_requirement": 220.0,
                "buying_power_effect": 220.0,
                "assignment_notional": 0.0,
                "portfolio_delta": 0.32,
                "portfolio_gamma": 0.04,
                "portfolio_theta": -0.03,
                "portfolio_vega": 0.12,
                "event_through_expiry": True,
                "strategy_pairing_method": "single_leg",
                "assignment_plan": None,
            },
            "option_strategy_fallbacks": {
                "volatility_event_option": {
                    "option_strategy_decision_id": "option-strategy-4b",
                    "option_strategy_type": "long_strangle",
                    "status": "ready",
                    "underlying_price": 118.0,
                    "net_debit_or_credit": 3.0,
                    "max_loss": 300.0,
                    "max_profit": None,
                    "breakevens": [114.0, 122.0],
                    "margin_requirement": 300.0,
                    "buying_power_effect": 300.0,
                    "assignment_notional": 0.0,
                    "portfolio_delta": 0.12,
                    "portfolio_gamma": 0.05,
                    "portfolio_theta": -0.02,
                    "portfolio_vega": 0.21,
                    "event_through_expiry": True,
                    "strategy_pairing_method": "single_leg",
                    "assignment_plan": None,
                    "metadata_json": {
                        "legs": [
                            {
                                "option_type": "call",
                                "side": "buy",
                                "quantity": 1,
                                "strike": 122.0,
                                "expiry": "2026-06-12",
                                "dte": 10,
                                "delta": 0.26,
                                "gamma": 0.03,
                                "theta": -0.01,
                                "vega": 0.11,
                                "iv_rank": 0.62,
                                "bid": 1.4,
                                "ask": 1.6,
                                "mid": 1.5,
                                "chosen_price": 1.5,
                            },
                            {
                                "option_type": "put",
                                "side": "buy",
                                "quantity": 1,
                                "strike": 114.0,
                                "expiry": "2026-06-12",
                                "dte": 10,
                                "delta": -0.14,
                                "gamma": 0.02,
                                "theta": -0.01,
                                "vega": 0.1,
                                "iv_rank": 0.62,
                                "bid": 1.4,
                                "ask": 1.6,
                                "mid": 1.5,
                                "chosen_price": 1.5,
                            },
                        ]
                    },
                }
            },
        },
    )
    risk = _risk_decision(approved_quantity=1)

    workflow.run(
        trading_decisions=(option_decision,),
        risk_decisions=(risk,),
        trade_date=now,
    )

    assert captured_requests == [
        {
            "instrument_type": "option",
            "trade_identity": "tactical_option_trade",
            "price": 300.0,
            "estimated_margin_requirement": 300.0,
        }
    ]
    assert captured_option_risk_inputs == [
        {
            "option_strategy_type": "long_strangle",
            "leg_quantities": [2, 2],
            "margin_requirement": 600.0,
        }
    ]
    assert len(repository.option_strategy_decisions) == 2
    assert repository.option_strategy_decisions[0].status == "rejected"
    assert repository.option_strategy_decisions[1].option_strategy_type == "long_strangle"
    assert len(repository.paper_option_orders) == 1
    assert repository.paper_option_orders[0].option_strategy_type == "long_strangle"
    assert repository.paper_option_orders[0].quantity == 2
    assert len(repository.paper_orders) == 0
    assert len(repository.risk_decisions) == 1
    assert repository.risk_decisions[0].risk_decision_id == "fallback-option-risk-1"
    assert len(repository.trade_classifications) == 1
    assert repository.trade_classifications[0].expression_bucket_id == "volatility_event_option"
    assert len(repository.trading_decisions) == 1
    assert repository.trading_decisions[0].expression_bucket_id == "volatility_event_option"
    assert repository.paper_option_orders[0].trading_decision_id == repository.trading_decisions[0].trading_decision_id
