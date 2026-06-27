from __future__ import annotations

from datetime import datetime, timezone
from datetime import date

import httpx

from src.db.models.trading import ExecutionAttempt, TradingDecision
from src.agents.prompt_registry import PromptRegistry
from src.trading.brokers.paper_option import PaperOptionBroker, PaperOptionOrderRequest
from src.trading.brokers.paper_stock import PaperExecutionRecord, PaperOrderRecord
from src.trading.execution.attempts import (
    REASON_BROKER_UNAVAILABLE,
    REASON_BROKER_ERROR,
    REASON_NOT_AUTHORIZED,
    REASON_SUBMITTED,
    ExecutionAttemptRecord,
    skipped,
)
from src.trading.intraday.rebalance import IntradayRebalancePipeline, IntradayRebalanceRequest
from src.trading.portfolio.state import PortfolioLedger
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
from src.trading.risk import RiskDecisionRecord
from src.trading.runtime.support import build_execution_report
from src.trading.workflows.paper_execution import PaperExecutionWorkflow
from src.trading.workflows.trading_decision import TradingDecisionRecord


class _FakeQuery:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def filter_by(self, **kwargs: object) -> "_FakeQuery":
        filtered = [
            row
            for row in self._rows
            if all(getattr(row, key) == value for key, value in kwargs.items())
        ]
        return _FakeQuery(filtered)

    def one_or_none(self) -> object | None:
        if not self._rows:
            return None
        if len(self._rows) > 1:
            raise AssertionError("expected at most one row")
        return self._rows[0]

    def all(self) -> list[object]:
        return list(self._rows)


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


class _NeverCalledStockBroker:
    def submit_order(self, request: object) -> object:
        raise AssertionError("submit_order should not be called")

    def find_execution_by_order_id(self, paper_order_id: str) -> object | None:
        raise AssertionError("find_execution_by_order_id should not be called")


class _UnauthorizedOptionClient:
    def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]) -> object:
        request = httpx.Request("POST", url)
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)


class _FilledStockBroker:
    def __init__(self) -> None:
        now = datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc)
        self._order = PaperOrderRecord(
            paper_order_id="paper-order-1",
            broker_order_id="broker-order-1",
            client_order_id="2026-06-26:AAPL:relative_strength_rotation_v1:enter_long",
            trading_decision_id="decision-1",
            risk_decision_id="risk-1",
            ticker="AAPL",
            strategy_id="relative_strength_rotation_v1",
            action="enter_long",
            trade_date=date(2026, 6, 26),
            quantity=10.0,
            limit_price=125.0,
            status="filled",
            rejection_reason=None,
            created_at=now,
        )
        self._execution = PaperExecutionRecord(
            paper_execution_id="paper-execution-1",
            paper_order_id="paper-order-1",
            broker_order_id="broker-order-1",
            ticker="AAPL",
            quantity=10.0,
            fill_price=125.0,
            trade_date=date(2026, 6, 26),
            executed_at=now,
            net_cash_effect=-1250.0,
        )

    def submit_order(self, request: object) -> PaperOrderRecord:
        return self._order

    def find_execution_by_order_id(self, paper_order_id: str) -> PaperExecutionRecord | None:
        return self._execution if paper_order_id == self._order.paper_order_id else None

    def sync_account(self) -> dict[str, str]:
        return {
            "cash": "98750.0",
            "equity": "100000.0",
            "portfolio_value": "100000.0",
            "buying_power": "197500.0",
            "long_market_value": "1250.0",
            "initial_margin": "625.0",
            "maintenance_margin": "375.0",
            "last_equity": "100000.0",
        }

    def sync_positions(self) -> list[dict[str, str]]:
        return [
            {
                "symbol": "AAPL",
                "qty": "10",
                "avg_entry_price": "125.0",
                "current_price": "125.0",
                "market_value": "1250.0",
                "side": "long",
            }
        ]


def _trading_decision(*, paper_trade_authorized: bool = False) -> TradingDecisionRecord:
    now = datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc)
    return TradingDecisionRecord(
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
        confidence=0.71,
        target_weight=0.05,
        approved_weight=0.04,
        max_loss_pct=0.02,
        time_horizon="2w-3m",
        thesis="Relative strength setup remains intact.",
        prompt_template=object(),
        prompt_run=None,
        usage_events=[],
        decision_time=now,
        available_for_decision_at=now,
        paper_trade_authorized=paper_trade_authorized,
        metadata_json={"paper_trade_authorized": paper_trade_authorized},
    )


def _risk_decision(*, status: str = "approved") -> RiskDecisionRecord:
    now = datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc)
    return RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="AAPL",
        status=status,
        reason_code="within_limits" if status == "approved" else "blocked",
        approved_weight=0.04,
        approved_notional=4000.0,
        approved_quantity=10.0,
        portfolio_risk_snapshot_id="portfolio-risk-1",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )


def _option_order_request() -> PaperOptionOrderRequest:
    return PaperOptionOrderRequest(
        trading_decision_id="decision-1",
        risk_decision_id="risk-1",
        option_strategy_decision_id="option-decision-1",
        ticker="AAPL",
        strategy_id="strong_theme_catalyst_continuation_v1",
        option_strategy_type="long_call",
        action="open_option_strategy",
        trade_date=date(2026, 6, 26),
        quantity=1,
        limit_price=2.2,
        max_loss=220.0,
        margin_requirement=220.0,
        buying_power_effect=220.0,
        trade_identity="tactical_option_trade",
        contract_symbol="AAPL260718C00200000",
        position_intent="buy_to_open",
    )


def _option_trading_decision() -> TradingDecisionRecord:
    now = datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc)
    return TradingDecisionRecord(
        trading_decision_id="option-decision-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        risk_decision_id="risk-1",
        ticker="AAPL",
        decision="open_option_strategy",
        strategy_id="strong_theme_catalyst_continuation_v1",
        strategy_version="v1",
        expression_bucket_id="defined_risk_directional_option",
        expression_bucket_version="v1",
        trade_identity="tactical_option_trade",
        instrument_type="option",
        selection_source="scanner",
        manual_request_id=None,
        confidence=0.71,
        target_weight=0.02,
        approved_weight=0.02,
        max_loss_pct=0.02,
        time_horizon="1w-4w",
        thesis="Call breakout continuation.",
        prompt_template=object(),
        prompt_run=None,
        usage_events=[],
        decision_time=now,
        available_for_decision_at=now,
        paper_trade_authorized=True,
        metadata_json={
            "paper_trade_authorized": True,
            "option_strategy": {
                "option_strategy_decision_id": "option-strategy-1",
                "option_strategy_type": "long_call",
                "status": "ready",
                "underlying_price": 200.0,
                "net_debit_or_credit": 2.2,
                "max_loss": 220.0,
                "max_profit": None,
                "breakevens": [202.2],
                "margin_requirement": 220.0,
                "buying_power_effect": 220.0,
                "assignment_notional": 0.0,
                "portfolio_delta": 0.32,
                "portfolio_gamma": 0.04,
                "portfolio_theta": -0.03,
                "portfolio_vega": 0.12,
                "event_through_expiry": False,
                "strategy_pairing_method": "single_leg",
                "assignment_plan": None,
                "margin_model_profile": "estimated_fidelity_like_conservative_v1",
                "margin_model_version": "v1",
                "margin_requirement_source": "simulated_formula",
                "profit_target_pct": 0.65,
                "max_loss_rule": "premium_at_risk",
                "roll_conditions": [],
                "close_conditions": [],
                "metadata_json": {
                    "legs": [
                        {
                            "contract_symbol": "AAPL260718C00200000",
                            "option_type": "call",
                            "side": "buy",
                            "quantity": 1,
                            "ratio_qty": 1,
                            "strike": 200.0,
                            "expiry": "2026-07-18",
                            "dte": 22,
                            "delta": 0.32,
                            "gamma": 0.04,
                            "theta": -0.03,
                            "vega": 0.12,
                            "iv_rank": 0.55,
                            "bid": 2.1,
                            "ask": 2.3,
                            "mid": 2.2,
                            "chosen_price": 2.2,
                        }
                    ]
                },
            },
        },
    )


def _write_intraday_prompt(tmp_path) -> PromptRegistry:
    prompt_dir = tmp_path / "prompts" / "trading"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "intraday_rebalance_v1.yaml"
    prompt_file.write_text(
        "prompt_id: intraday_rebalance\n"
        "prompt_version: v1\n"
        "pipeline_name: intraday_rebalance\n"
        "output_schema_id: intraday_rebalance\n"
        "output_schema_version: v1\n"
        "template: |\n"
        "  Decide what to do intraday for {{ ticker }}.\n"
        "  Input JSON: {{ input_payload_json }}\n",
        encoding="utf-8",
    )
    return PromptRegistry(root=tmp_path / "prompts")


def _intraday_request() -> IntradayRebalanceRequest:
    now = datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc)
    return IntradayRebalanceRequest(
        ticker="AAPL",
        baseline_signal_snapshot_id="baseline-1",
        intraday_signal_snapshot_id="intraday-1",
        previous_intraday_snapshot_id="intraday-0",
        selection_source="scanner",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        decision_time=now,
        available_for_decision_at=now,
        current_price=125.0,
        atr_pct=0.02,
        average_daily_dollar_volume=50_000_000.0,
        existing_position=True,
        current_position_quantity=5.0,
        current_position_market_value=625.0,
        candidate_score=0.82,
        target_weight=0.05,
        signal_freshness={"technical": "fresh", "events_news": "fresh"},
        delta_vs_baseline_json={"technical": {"last_price": 5.0}},
        delta_vs_previous_json={"technical": {"last_price": 2.0}},
        alerts=(),
        allow_open_new=False,
        direct_company_negative_evidence=True,
        bearish_signal_sources=("events_news",),
        manual_request_id=None,
        manual_request_mode=None,
        metadata_json={},
    )


def test_in_memory_repository_saves_and_lists_execution_attempts():
    repository = InMemoryTradingRepository()
    attempt = skipped(
        trading_decision=_trading_decision(paper_trade_authorized=False),
        phase="preopen",
        reason_code=REASON_NOT_AUTHORIZED,
        detail="paper trading was not authorized",
    )

    repository.save_execution_attempt(attempt)

    assert repository.list_execution_attempts() == (attempt,)


def test_sqlalchemy_repository_persists_execution_attempts():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    attempt = ExecutionAttemptRecord.create(
        trading_decision_id="decision-1",
        risk_decision_id="risk-1",
        paper_order_id=None,
        paper_option_order_id=None,
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        phase="preopen",
        action="enter_long",
        outcome="skipped",
        reason_code=REASON_NOT_AUTHORIZED,
        detail="paper trading was not authorized",
        metadata_json={"source": "unit_test"},
    )

    repository.save_execution_attempt(attempt)

    row = session.query(ExecutionAttempt).one_or_none()
    assert row is not None
    assert str(row.execution_attempt_id) == attempt.execution_attempt_id
    assert row.phase == "preopen"
    assert row.outcome == "skipped"
    assert row.reason_code == REASON_NOT_AUTHORIZED
    assert row.detail == "paper trading was not authorized"
    assert row.metadata_json == {"source": "unit_test"}
    assert session.flush_calls == 1


def test_sqlalchemy_repository_persists_paper_trade_authorized_from_typed_field():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    decision = _trading_decision(paper_trade_authorized=False)
    decision = TradingDecisionRecord(
        **{
            **decision.__dict__,
            "metadata_json": {"paper_trade_authorized": True},
        }
    )

    repository.save_trading_decision(decision)

    row = session.query(TradingDecision).one_or_none()
    assert row is not None
    assert row.paper_trade_authorized is False


def test_paper_execution_workflow_records_not_authorized_attempt_from_typed_field():
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=_NeverCalledStockBroker(),
    )
    decision = _trading_decision(paper_trade_authorized=False)
    decision = TradingDecisionRecord(
        **{
            **decision.__dict__,
            "metadata_json": {"paper_trade_authorized": True},
        }
    )

    result = workflow.run(
        trading_decisions=(decision,),
        risk_decisions=(_risk_decision(),),
        trade_date=decision.decision_time,
    )

    assert result.paper_orders == ()
    attempts = repository.list_execution_attempts()
    assert len(attempts) == 1
    assert attempts[0].outcome == "skipped"
    assert attempts[0].reason_code == REASON_NOT_AUTHORIZED
    assert attempts[0].phase == "preopen"


def test_paper_execution_workflow_records_submitted_attempt_for_filled_stock_order():
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=_FilledStockBroker(),
    )

    result = workflow.run(
        trading_decisions=(_trading_decision(paper_trade_authorized=True),),
        risk_decisions=(_risk_decision(),),
        trade_date=datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc),
    )

    assert len(result.paper_orders) == 1
    attempts = repository.list_execution_attempts()
    assert len(attempts) == 1
    assert attempts[0].outcome == "submitted"
    assert attempts[0].reason_code == REASON_SUBMITTED


def test_build_execution_report_includes_skipped_failed_and_reason_breakdown():
    report = build_execution_report(
        mode="execute",
        orders_submitted=0,
        option_orders_submitted=0,
        orders_skipped=2,
        orders_failed=1,
        skip_reasons={"not_authorized": 1, "risk_rejected": 1},
    )

    assert report == {
        "mode": "execute",
        "orders_submitted": 0,
        "option_orders_submitted": 0,
        "orders_skipped": 2,
        "orders_failed": 1,
        "skip_reasons": {"not_authorized": 1, "risk_rejected": 1},
    }


def test_paper_option_broker_falls_back_to_local_mode_when_only_base_url_is_configured():
    broker = PaperOptionBroker(
        trading_base_url="https://paper-api.alpaca.markets",
        now=lambda: datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc),
    )

    order = broker.submit_order(_option_order_request())

    assert order.status == "filled"
    assert order.rejection_reason is None


def test_paper_option_broker_returns_rejected_order_on_forced_live_http_error():
    broker = PaperOptionBroker(
        api_key="key",
        secret_key="secret",
        client=_UnauthorizedOptionClient(),
        now=lambda: datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc),
    )

    order = broker.submit_order(_option_order_request())

    assert order.status == "rejected"
    assert order.rejection_reason == "broker_error"


def test_intraday_rebalance_records_broker_unavailable_skip_and_summary(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_intraday_prompt(tmp_path)
    ledger = PortfolioLedger(starting_cash_balance=100000.0)
    pipeline = IntradayRebalancePipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5-mini",
        agent_runner=lambda prompt, model: {
            "content": {
                "ticker": "AAPL",
                "action": "exit",
                "thesis": "Direct negative catalyst invalidated the thesis.",
                "confidence": 0.84,
                "target_weight": 0.0,
                "max_loss_pct": 0.02,
                "urgency": "critical",
                "rationale": ["negative_catalyst"],
                "risk_checks": ["liquidity_ok"],
                "schema_version": "v1",
                "generated_at": "2026-06-26T15:30:00+00:00",
            }
        },
        broker=None,
    )

    result = pipeline.run(
        rebalance_requests=(_intraday_request(),),
        portfolio_context=ledger.build_portfolio_context(as_of=datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc)),
        risk_appetite="balanced",
        trade_date=datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc),
        execute_approved=True,
    )

    attempts = repository.list_execution_attempts()
    assert len(attempts) == 1
    assert attempts[0].phase == "intraday"
    assert attempts[0].reason_code == REASON_BROKER_UNAVAILABLE
    assert attempts[0].outcome == "skipped"
    assert result.execution_summary == {
        "orders_submitted": 0,
        "option_orders_submitted": 0,
        "orders_skipped": 1,
        "skip_reasons": {"broker_unavailable": 1},
    }


def test_paper_execution_workflow_records_option_broker_unavailable_attempt():
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=_NeverCalledStockBroker(),
        option_broker=None,
    )

    result = workflow.run(
        trading_decisions=(_option_trading_decision(),),
        risk_decisions=(_risk_decision(),),
        trade_date=datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc),
    )

    assert result.paper_option_orders == ()
    attempts = repository.list_execution_attempts()
    assert len(attempts) == 1
    assert attempts[0].reason_code == REASON_BROKER_UNAVAILABLE
    assert attempts[0].outcome == "skipped"


def test_paper_execution_workflow_records_failed_option_attempt_on_broker_error():
    repository = InMemoryTradingRepository()
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=_NeverCalledStockBroker(),
        option_broker=PaperOptionBroker(
            api_key="key",
            secret_key="secret",
            client=_UnauthorizedOptionClient(),
            now=lambda: datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc),
        ),
    )

    result = workflow.run(
        trading_decisions=(_option_trading_decision(),),
        risk_decisions=(_risk_decision(),),
        trade_date=datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc),
    )

    assert len(result.paper_option_orders) == 1
    attempts = repository.list_execution_attempts()
    assert len(attempts) == 1
    assert attempts[0].reason_code == REASON_BROKER_ERROR
    assert attempts[0].outcome == "failed"
