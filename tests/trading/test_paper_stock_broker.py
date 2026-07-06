from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.brokers.paper_option import (
    LocalPaperOptionBroker,
    PaperOptionBroker,
    PaperOptionPosition,
    PaperOptionOrderRequest,
)
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


class _DelayedFillClient(_CapturingClient):
    def __init__(self) -> None:
        super().__init__()
        self._order_poll_count = 0

    def get(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str]) -> _StubResponse:
        if url.endswith("/v2/orders:by_client_order_id"):
            self.gets.append({"url": url, "params": params, "headers": headers})
            self._order_poll_count += 1
            client_order_id = (params or {})["client_order_id"]
            status = "filled" if self._order_poll_count >= 6 else "partially_filled"
            return _StubResponse(
                {
                    "id": "broker-order-1",
                    "client_order_id": client_order_id,
                    "symbol": "AAPL",
                    "qty": "0.01",
                    "filled_qty": "0.01" if status == "filled" else "0.005",
                    "filled_avg_price": "227.15" if status == "filled" else "227.10",
                    "side": "buy",
                    "type": "market",
                    "time_in_force": "day",
                    "status": status,
                    "submitted_at": "2026-06-02T16:31:00+00:00",
                    "filled_at": "2026-06-02T16:31:07+00:00" if status == "filled" else None,
                }
            )
        return super().get(url, params=params, headers=headers)


class _RecordingOptionBroker:
    def __init__(self, *, now: datetime) -> None:
        self._delegate = LocalPaperOptionBroker(now=lambda: now)
        self.submitted_requests: list[PaperOptionOrderRequest] = []

    def submit_order(self, request: PaperOptionOrderRequest):
        self.submitted_requests.append(request)
        return self._delegate.submit_order(request)

    def find_execution_by_order_id(self, paper_option_order_id: str):
        return self._delegate.find_execution_by_order_id(paper_option_order_id)


def _option_strategy_legs(
    *,
    ticker: str,
    option_strategy_type: str,
    quantity: int,
    expiry: str,
) -> list[dict[str, Any]]:
    if option_strategy_type == "put_credit_spread":
        return [
            {
                "contract_symbol": f"{ticker}260717P00105000",
                "option_type": "put",
                "side": "buy",
                "quantity": quantity,
                "ratio_qty": quantity,
                "strike": 105.0,
                "expiry": expiry,
                "dte": 10,
                "delta": -0.18,
                "gamma": 0.03,
                "theta": -0.01,
                "vega": 0.08,
                "iv_rank": 0.62,
                "bid": 0.7,
                "ask": 0.9,
                "mid": 0.8,
                "chosen_price": 0.8,
            },
            {
                "contract_symbol": f"{ticker}260717P00110000",
                "option_type": "put",
                "side": "sell",
                "quantity": quantity,
                "ratio_qty": quantity,
                "strike": 110.0,
                "expiry": expiry,
                "dte": 10,
                "delta": -0.28,
                "gamma": 0.02,
                "theta": 0.01,
                "vega": -0.07,
                "iv_rank": 0.62,
                "bid": 1.4,
                "ask": 1.6,
                "mid": 1.5,
                "chosen_price": 1.5,
            },
        ]
    if option_strategy_type == "long_strangle":
        return [
            {
                "contract_symbol": f"{ticker}260612C00122000",
                "option_type": "call",
                "side": "buy",
                "quantity": quantity,
                "ratio_qty": quantity,
                "strike": 122.0,
                "expiry": expiry,
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
                "contract_symbol": f"{ticker}260612P00114000",
                "option_type": "put",
                "side": "buy",
                "quantity": quantity,
                "ratio_qty": quantity,
                "strike": 114.0,
                "expiry": expiry,
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
    option_type = "put" if option_strategy_type == "long_put" else "call"
    strike = 114.0 if option_type == "put" else 120.0
    strike_component = "00114000" if option_type == "put" else "00120000"
    return [
        {
            "contract_symbol": f"{ticker}260612{'P' if option_type == 'put' else 'C'}{strike_component}",
            "option_type": option_type,
            "side": "buy",
            "quantity": quantity,
            "ratio_qty": quantity,
            "strike": strike,
            "expiry": expiry,
            "dte": 10,
            "delta": -0.32 if option_type == "put" else 0.32,
            "gamma": 0.04,
            "theta": -0.03,
            "vega": 0.12,
            "iv_rank": 0.62,
            "bid": 2.1,
            "ask": 2.3,
            "mid": 2.2,
            "chosen_price": 2.2,
        }
    ]


def _broker_leg_refs(
    *,
    ticker: str,
    option_strategy_type: str,
    quantity: int,
    expiry: str,
    action: str = "open_option_strategy",
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for payload in _option_strategy_legs(
        ticker=ticker,
        option_strategy_type=option_strategy_type,
        quantity=quantity,
        expiry=expiry,
    ):
        side = str(payload["side"])
        if action == "open_option_strategy":
            position_intent = "buy_to_open" if side == "buy" else "sell_to_open"
        else:
            position_intent = "sell_to_close" if side == "buy" else "buy_to_close"
        refs.append(
            {
                "contract_symbol": payload["contract_symbol"],
                "ratio_qty": payload["ratio_qty"],
                "position_intent": position_intent,
            }
        )
    return refs


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
        paper_trade_authorized=True,
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


def _option_trading_decision(
    *,
    now: datetime,
    decision: str,
    option_strategy_type: str = "long_call",
    ticker: str = "NVDA",
    strategy_id: str = "strong_theme_catalyst_continuation_v1",
    expiry: str = "2026-06-12",
    quantity: int = 1,
    net_debit_or_credit: float = 2.2,
    max_loss: float = 220.0,
    margin_requirement: float = 220.0,
    buying_power_effect: float = 220.0,
    assignment_notional: float = 0.0,
) -> TradingDecisionRecord:
    return TradingDecisionRecord(
        trading_decision_id=f"{decision}-{ticker}-decision",
        candidate_score_id=f"{ticker}-candidate",
        trade_classification_id=f"{ticker}-classification",
        risk_decision_id=f"{ticker}-risk",
        ticker=ticker,
        decision=decision,
        strategy_id=strategy_id,
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
        thesis="Option lifecycle test.",
        invalidators=["event risk"],
        prompt_template=object(),
        prompt_run=object(),
        usage_events=[],
        decision_time=now,
        available_for_decision_at=now,
        paper_trade_authorized=True,
        metadata_json={
            "paper_trade_authorized": True,
            "option_strategy": {
                "option_strategy_decision_id": f"{decision}-{ticker}-option-strategy",
                "option_strategy_type": option_strategy_type,
                "status": "ready",
                "underlying_price": 118.0,
                "net_debit_or_credit": net_debit_or_credit,
                "max_loss": max_loss,
                "max_profit": None,
                "breakevens": [120.2],
                "margin_requirement": margin_requirement,
                "buying_power_effect": buying_power_effect,
                "assignment_notional": assignment_notional,
                "portfolio_delta": 0.32,
                "portfolio_gamma": 0.04,
                "portfolio_theta": -0.03,
                "portfolio_vega": 0.12,
                "event_through_expiry": True,
                "strategy_pairing_method": "single_leg",
                "assignment_plan": None,
                "metadata_json": {
                    "legs": _option_strategy_legs(
                        ticker=ticker,
                        option_strategy_type=option_strategy_type,
                        quantity=quantity,
                        expiry=expiry,
                    )
                },
            },
        },
    )


def _option_risk_decision(*, now: datetime, ticker: str = "NVDA", approved_quantity: float = 1.0) -> RiskDecisionRecord:
    return RiskDecisionRecord(
        risk_decision_id=f"{ticker}-risk",
        candidate_score_id=f"{ticker}-candidate",
        trade_classification_id=f"{ticker}-classification",
        position_sizing_decision_id=f"{ticker}-sizing",
        ticker=ticker,
        status="approved",
        reason_code="within_limits",
        approved_weight=0.02,
        approved_notional=2000.0,
        approved_quantity=approved_quantity,
        portfolio_risk_snapshot_id=f"{ticker}-portfolio-risk",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )


def _seed_open_option_position(
    repository: InMemoryTradingRepository,
    *,
    now: datetime,
    ticker: str = "NVDA",
    option_strategy_type: str = "long_call",
    quantity: int = 1,
) -> PaperOptionPosition:
    position = PaperOptionPosition(
        paper_option_position_id=f"{ticker.lower()}-open-position",
        option_strategy_decision_id=f"{ticker.lower()}-open-option-strategy",
        ticker=ticker,
        strategy_id="strong_theme_catalyst_continuation_v1",
        option_strategy_type=option_strategy_type,
        trade_identity="tactical_option_trade",
        quantity=quantity,
        opened_at=now,
        updated_at=now,
        status="open",
        expiry=now.date(),
        max_loss=220.0,
        margin_requirement=220.0,
        buying_power_effect=220.0,
        assignment_notional=0.0,
        metadata_json={
            "broker_leg_refs": _broker_leg_refs(
                ticker=ticker,
                option_strategy_type=option_strategy_type,
                quantity=quantity,
                expiry=now.date().isoformat(),
            ),
            "opening_broker_order_id": f"{ticker.lower()}-opening-order",
        },
    )
    repository.save_paper_option_position(position)
    return position


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


def test_paper_execution_workflow_executes_generated_risk_hedge_overlay():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=PaperOptionBroker(now=lambda: now),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )
    hedge_risk = RiskDecisionRecord(
        risk_decision_id="hedge-risk-1",
        candidate_score_id=None,
        trade_classification_id=None,
        position_sizing_decision_id=None,
        ticker="AAPL",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.02,
        approved_notional=2000.0,
        approved_quantity=1.0,
        portfolio_risk_snapshot_id="portfolio-risk-1",
        applied_rules=["portfolio_risk_intent"],
        generated_hedge_action={
            "action": "open_hedge",
            "risk_source": "macro",
            "severity": "high",
            "target_underlier": "QQQ",
            "target_exposure_type": "broad_market",
            "coverage_ratio": 0.5,
            "reason_code": "macro_high_overlay",
            "option_strategy_type": "long_put",
            "underlying_price": 500.0,
            "protected_notional": 10000.0,
        },
        decision_time=now,
        metadata_json={},
    )

    workflow.run(
        trading_decisions=(),
        risk_decisions=(hedge_risk,),
        trade_date=now,
    )

    assert len(repository.trading_decisions) == 1
    assert repository.trading_decisions[0].selection_source == "risk_manager"
    assert len(repository.option_strategy_decisions) == 1
    assert repository.option_strategy_decisions[0].trade_identity == "risk_hedge_overlay"
    assert repository.option_strategy_decisions[0].ticker == "QQQ"
    assert len(repository.paper_option_orders) == 1
    assert repository.paper_option_orders[0].trade_identity == "risk_hedge_overlay"
    assert len(repository.risk_hedge_decisions) == 1
    assert repository.risk_hedge_decisions[0].ticker == "QQQ"


def test_paper_execution_workflow_closes_existing_generated_risk_hedge_overlay_without_strategy_type_hint():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="existing-hedge-1",
            option_strategy_decision_id="existing-option-decision-1",
            ticker="QQQ",
            strategy_id="risk_manager_hedge_overlay_v1",
            option_strategy_type="long_call",
            trade_identity="risk_hedge_overlay",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=now.date(),
            max_loss=1000.0,
            margin_requirement=1000.0,
            buying_power_effect=1000.0,
            assignment_notional=0.0,
            metadata_json={
                "generated_hedge_action": {"option_strategy_type": "long_call"},
                "broker_leg_refs": _broker_leg_refs(
                    ticker="QQQ",
                    option_strategy_type="long_call",
                    quantity=1,
                    expiry=now.date().isoformat(),
                ),
            },
        )
    )
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=PaperOptionBroker(now=lambda: now),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )
    hedge_risk = RiskDecisionRecord(
        risk_decision_id="hedge-risk-close-1",
        candidate_score_id=None,
        trade_classification_id=None,
        position_sizing_decision_id=None,
        ticker="AAPL",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.0,
        approved_notional=0.0,
        approved_quantity=0.0,
        portfolio_risk_snapshot_id="portfolio-risk-1",
        applied_rules=["portfolio_risk_intent"],
        generated_hedge_action={
            "action": "close_hedge",
            "risk_source": "assignment",
            "severity": "watch",
            "target_underlier": "QQQ",
            "target_exposure_type": "assignment",
            "coverage_ratio": 1.0,
            "reason_code": "assignment_overlay_normalized",
            "protected_notional": 15000.0,
        },
        decision_time=now,
        metadata_json={},
    )

    workflow.run(
        trading_decisions=(),
        risk_decisions=(hedge_risk,),
        trade_date=now,
    )

    closed_positions = [position for position in repository.paper_option_positions if position.status == "closed"]
    assert len(closed_positions) == 1
    assert closed_positions[0].paper_option_position_id == "existing-hedge-1"
    assert closed_positions[0].option_strategy_type == "long_call"
    assert len(repository.risk_hedge_decisions) == 1
    assert repository.risk_hedge_decisions[0].option_strategy_type == "long_call"
    assert repository.risk_hedge_decisions[0].protected_notional == 15000.0


def test_paper_execution_workflow_adjusts_existing_generated_risk_hedge_overlay_without_duplicate_open():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="existing-hedge-1",
            option_strategy_decision_id="existing-option-decision-1",
            ticker="QQQ",
            strategy_id="risk_manager_hedge_overlay_v1",
            option_strategy_type="long_call",
            trade_identity="risk_hedge_overlay",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=now.date(),
            max_loss=1000.0,
            margin_requirement=1000.0,
            buying_power_effect=1000.0,
            assignment_notional=0.0,
            metadata_json={
                "generated_hedge_action": {"option_strategy_type": "long_call"},
                "broker_leg_refs": _broker_leg_refs(
                    ticker="QQQ",
                    option_strategy_type="long_call",
                    quantity=1,
                    expiry=now.date().isoformat(),
                ),
            },
        )
    )
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=PaperOptionBroker(now=lambda: now),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )
    hedge_risk = RiskDecisionRecord(
        risk_decision_id="hedge-risk-adjust-1",
        candidate_score_id=None,
        trade_classification_id=None,
        position_sizing_decision_id=None,
        ticker="AAPL",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.0,
        approved_notional=0.0,
        approved_quantity=0.0,
        portfolio_risk_snapshot_id="portfolio-risk-1",
        applied_rules=["portfolio_risk_intent"],
        generated_hedge_action={
            "action": "adjust_hedge",
            "risk_source": "macro",
            "severity": "high",
            "target_underlier": "QQQ",
            "target_exposure_type": "broad_market",
            "coverage_ratio": 0.75,
            "reason_code": "macro_high_overlay",
            "underlying_price": 500.0,
            "protected_notional": 120000.0,
        },
        decision_time=now,
        metadata_json={},
    )

    workflow.run(
        trading_decisions=(),
        risk_decisions=(hedge_risk,),
        trade_date=now,
    )

    open_positions = [position for position in repository.paper_option_positions if position.status == "open"]
    assert len(open_positions) == 1
    assert open_positions[0].paper_option_position_id == "existing-hedge-1"
    assert open_positions[0].option_strategy_type == "long_call"
    assert open_positions[0].quantity == 2
    assert len(repository.risk_hedge_decisions) == 1
    assert repository.risk_hedge_decisions[0].option_strategy_type == "long_call"
    assert repository.risk_hedge_decisions[0].protected_notional == 120000.0


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


def test_paper_execution_workflow_reconciles_delayed_stock_fill_before_returning_no_fill():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    client = _DelayedFillClient()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=client),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    result = workflow.run(
        trading_decisions=(_trading_decision(),),
        risk_decisions=(_risk_decision(),),
        trade_date=now,
    )

    assert result.paper_orders[0].status == "filled"
    assert repository.paper_orders[0].status == "filled"
    assert len(repository.paper_executions) == 1
    assert repository.paper_positions[0].ticker == "AAPL"
    assert repository.paper_positions[0].strategy_id == "relative_strength_rotation_v1"
    attempts = repository.list_execution_attempts()
    assert len(attempts) == 1
    assert attempts[0].outcome == "submitted"


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
        paper_trade_authorized=True,
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
                "metadata_json": {
                    "legs": _option_strategy_legs(
                        ticker="NVDA",
                        option_strategy_type="put_credit_spread",
                        quantity=1,
                        expiry="2026-07-17",
                    )
                },
            },
        },
    )
    risk = _risk_decision(approved_quantity=1)

    result = workflow.run(
        trading_decisions=(option_decision,),
        risk_decisions=(risk,),
        trade_date=now,
    )

    assert len(result.paper_option_orders) == 1
    assert len(repository.option_strategy_decisions) == 1
    assert len(repository.paper_option_orders) == 1
    assert len(repository.paper_option_positions) == 1
    assert len(repository.option_risk_snapshots) == 1


def test_paper_execution_workflow_submits_mleg_open_request_for_credit_spread():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    option_broker = _RecordingOptionBroker(now=now)
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=option_broker,
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    workflow.run(
        trading_decisions=(
            _option_trading_decision(
                now=now,
                decision="open_option_strategy",
                ticker="NVDA",
                option_strategy_type="put_credit_spread",
                expiry="2026-07-17",
                net_debit_or_credit=-1.5,
                max_loss=500.0,
                margin_requirement=500.0,
                buying_power_effect=500.0,
                assignment_notional=11000.0,
            ),
        ),
        risk_decisions=(_option_risk_decision(now=now, ticker="NVDA"),),
        trade_date=now,
    )

    request = option_broker.submitted_requests[0]

    assert request.order_class == "mleg"
    assert [leg.position_intent for leg in request.legs] == ["buy_to_open", "sell_to_open"]
    assert [leg.contract_symbol for leg in request.legs] == [
        "NVDA260717P00105000",
        "NVDA260717P00110000",
    ]
    assert repository.paper_option_positions[0].metadata_json["broker_leg_refs"][0]["contract_symbol"] == "NVDA260717P00105000"


def test_paper_execution_workflow_submits_simple_close_request_from_existing_broker_leg_refs():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    existing = _seed_open_option_position(repository, now=now)
    option_broker = _RecordingOptionBroker(now=now)
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=option_broker,
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    workflow.run(
        trading_decisions=(
            _option_trading_decision(
                now=now,
                decision="close_option_strategy",
                ticker=existing.ticker,
                option_strategy_type=existing.option_strategy_type,
            ),
        ),
        risk_decisions=(_option_risk_decision(now=now, ticker=existing.ticker),),
        trade_date=now,
    )

    request = option_broker.submitted_requests[0]

    assert request.order_class == "simple"
    assert request.contract_symbol == "NVDA260612C00120000"
    assert request.position_intent == "sell_to_close"


def test_paper_execution_workflow_rolls_option_strategy_with_close_and_open_legs():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    existing = _seed_open_option_position(repository, now=now)
    option_broker = _RecordingOptionBroker(now=now)
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=option_broker,
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    workflow.run(
        trading_decisions=(
            _option_trading_decision(
                now=now,
                decision="roll_option_strategy",
                ticker=existing.ticker,
                option_strategy_type=existing.option_strategy_type,
                expiry="2026-07-17",
                max_loss=280.0,
                margin_requirement=280.0,
                buying_power_effect=280.0,
            ),
        ),
        risk_decisions=(_option_risk_decision(now=now, ticker=existing.ticker),),
        trade_date=now,
    )

    request = option_broker.submitted_requests[0]
    replacement = next(
        position for position in repository.paper_option_positions if position.paper_option_position_id != existing.paper_option_position_id
    )

    assert request.order_class == "mleg"
    assert [leg.position_intent for leg in request.legs] == ["sell_to_close", "buy_to_open"]
    assert replacement.metadata_json["broker_leg_refs"][0]["position_intent"] == "buy_to_open"


def test_paper_execution_workflow_closes_existing_option_position():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    existing = _seed_open_option_position(repository, now=now)
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=PaperOptionBroker(now=lambda: now),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    workflow.run(
        trading_decisions=(
            _option_trading_decision(
                now=now,
                decision="close_option_strategy",
                ticker=existing.ticker,
                option_strategy_type=existing.option_strategy_type,
            ),
        ),
        risk_decisions=(_option_risk_decision(now=now, ticker=existing.ticker),),
        trade_date=now,
    )

    assert len(repository.paper_option_orders) == 1
    assert repository.paper_option_orders[0].action == "close_option_strategy"
    assert any(
        position.paper_option_position_id == existing.paper_option_position_id and position.status == "closed"
        for position in repository.paper_option_positions
    )


def test_paper_execution_workflow_rolls_option_strategy_by_closing_then_opening():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    existing = _seed_open_option_position(repository, now=now)
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=PaperOptionBroker(now=lambda: now),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    workflow.run(
        trading_decisions=(
            _option_trading_decision(
                now=now,
                decision="roll_option_strategy",
                ticker=existing.ticker,
                option_strategy_type=existing.option_strategy_type,
                expiry="2026-07-17",
                max_loss=280.0,
                margin_requirement=280.0,
                buying_power_effect=280.0,
            ),
        ),
        risk_decisions=(_option_risk_decision(now=now, ticker=existing.ticker),),
        trade_date=now,
    )

    assert len(repository.paper_option_orders) == 1
    assert repository.paper_option_orders[0].action == "roll_option_strategy"
    assert any(
        position.paper_option_position_id == existing.paper_option_position_id and position.status == "closed"
        for position in repository.paper_option_positions
    )
    assert any(
        position.paper_option_position_id != existing.paper_option_position_id and position.status == "open"
        for position in repository.paper_option_positions
    )


def test_paper_execution_workflow_adjusts_existing_option_strategy_in_place():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    existing = _seed_open_option_position(repository, now=now, quantity=1)
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=PaperOptionBroker(now=lambda: now),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    workflow.run(
        trading_decisions=(
            _option_trading_decision(
                now=now,
                decision="adjust_option_strategy",
                ticker=existing.ticker,
                option_strategy_type=existing.option_strategy_type,
                quantity=2,
                max_loss=440.0,
                margin_requirement=440.0,
                buying_power_effect=440.0,
            ),
        ),
        risk_decisions=(_option_risk_decision(now=now, ticker=existing.ticker, approved_quantity=2.0),),
        trade_date=now,
    )

    assert len(repository.paper_option_orders) == 1
    assert repository.paper_option_orders[0].action == "adjust_option_strategy"
    adjusted = next(
        position
        for position in repository.paper_option_positions
        if position.paper_option_position_id == existing.paper_option_position_id
    )
    assert adjusted.status == "open"
    assert adjusted.quantity == 2
    assert adjusted.metadata_json["lifecycle_action"] == "adjust_option_strategy"


def test_paper_execution_workflow_persists_avoid_event_option_without_filled_order():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient()),
        option_broker=PaperOptionBroker(now=lambda: now),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    workflow.run(
        trading_decisions=(
            _option_trading_decision(
                now=now,
                decision="avoid_event_option",
            ),
        ),
        risk_decisions=(_option_risk_decision(now=now),),
        trade_date=now,
    )

    assert len(repository.option_strategy_decisions) == 1
    assert len(repository.paper_option_orders) == 1
    assert repository.paper_option_orders[0].action == "avoid_event_option"
    assert repository.paper_option_orders[0].status == "rejected"
    assert len(repository.paper_option_positions) == 0


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
        paper_trade_authorized=True,
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
        paper_trade_authorized=True,
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
        paper_trade_authorized=True,
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
