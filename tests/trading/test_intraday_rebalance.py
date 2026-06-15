from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.agents.prompt_registry import PromptRegistry
from src.trading.brokers.paper_stock import PaperStockBroker
from src.trading.intraday.rebalance import IntradayRebalancePipeline, IntradayRebalanceRequest
from src.trading.portfolio.state import PortfolioLedger
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.risk import HedgeActionRecord, PortfolioRiskIntentRecord, PositionRiskActionRecord


class _StubResponse:
    def __init__(self, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any] | list[dict[str, Any]]:
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
            return _StubResponse(
                {
                    "id": "broker-order-1",
                    "client_order_id": (params or {})["client_order_id"],
                    "symbol": "AAPL",
                    "qty": "5",
                    "filled_qty": "5",
                    "filled_avg_price": "125.0",
                    "side": "sell",
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
                    "cash": "100625.0",
                    "equity": "100625.0",
                    "portfolio_value": "100625.0",
                    "buying_power": "201250.0",
                    "long_market_value": "0.0",
                    "initial_margin": "0.0",
                    "maintenance_margin": "0.0",
                    "last_equity": "100000.0",
                }
            )
        if url.endswith("/v2/positions"):
            return _StubResponse([])
        raise AssertionError(f"unexpected_get:{url}")


def _write_prompt(tmp_path) -> PromptRegistry:
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


def _request(
    *,
    existing_position: bool,
    allow_open_new: bool,
    action: str = "exit",
    ticker: str = "AAPL",
    trade_identity: str = "tactical_stock_trade",
    instrument_type: str = "stock",
    strategy_id: str = "relative_strength_rotation_v1",
    expression_bucket_id: str = "long_stock",
    current_price: float = 125.0,
    signal_freshness: dict[str, Any] | None = None,
    alerts: tuple[dict[str, Any], ...] = (),
    metadata_json: dict[str, Any] | None = None,
) -> IntradayRebalanceRequest:
    now = datetime(2026, 6, 2, 15, 30, tzinfo=timezone.utc)
    return IntradayRebalanceRequest(
        ticker=ticker,
        baseline_signal_snapshot_id="baseline-1",
        intraday_signal_snapshot_id="intraday-1",
        previous_intraday_snapshot_id="intraday-0",
        selection_source="scanner",
        strategy_id=strategy_id,
        strategy_version="v1",
        expression_bucket_id=expression_bucket_id,
        expression_bucket_version="v1",
        trade_identity=trade_identity,
        instrument_type=instrument_type,
        decision_time=now,
        available_for_decision_at=now,
        current_price=current_price,
        atr_pct=0.02,
        average_daily_dollar_volume=50_000_000.0,
        existing_position=existing_position,
        current_position_quantity=5.0 if existing_position else 0.0,
        current_position_market_value=625.0 if existing_position else 0.0,
        candidate_score=0.82,
        target_weight=0.05,
        signal_freshness=signal_freshness or {"technical": "fresh", "events_news": "fresh"},
        delta_vs_baseline_json={"technical": {"last_price": 5.0}},
        delta_vs_previous_json={"technical": {"last_price": 2.0}},
        alerts=alerts,
        allow_open_new=allow_open_new,
        direct_company_negative_evidence=(action == "exit"),
        bearish_signal_sources=("events_news",) if action == "exit" else (),
        metadata_json=metadata_json or {},
    )


def test_intraday_rebalance_pipeline_falls_back_to_hold_after_validation_failure(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    ledger = PortfolioLedger(starting_cash_balance=100000.0)
    pipeline = IntradayRebalancePipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5-mini",
        agent_runner=lambda prompt, model: {"content": {"ticker": "AAPL", "action": "bad_value"}},
    )

    result = pipeline.run(
        rebalance_requests=(_request(existing_position=True, allow_open_new=False),),
        portfolio_context=ledger.build_portfolio_context(as_of=datetime(2026, 6, 2, 15, 30, tzinfo=timezone.utc)),
        risk_appetite="balanced",
    )

    assert result.decisions[0].action == "hold"
    assert result.decisions[0].status == "fallback"
    assert len(repository.llm_prompt_runs) == 1
    assert len(repository.intraday_rebalance_decisions) == 1


def test_intraday_rebalance_pipeline_blocks_open_new_without_permission(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    ledger = PortfolioLedger(starting_cash_balance=100000.0)
    pipeline = IntradayRebalancePipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5-mini",
        agent_runner=lambda prompt, model: {
            "content": {
                "ticker": "AAPL",
                "action": "open_new",
                "thesis": "Fresh catalyst confirmed intraday.",
                "confidence": 0.77,
                "target_weight": 0.05,
                "max_loss_pct": 0.02,
                "urgency": "high",
                "rationale": ["fresh_news"],
                "risk_checks": ["liquidity_ok"],
                "schema_version": "v1",
                "generated_at": "2026-06-02T15:30:00+00:00",
            }
        },
    )

    result = pipeline.run(
        rebalance_requests=(_request(existing_position=False, allow_open_new=False, action="open_new"),),
        portfolio_context=ledger.build_portfolio_context(as_of=datetime(2026, 6, 2, 15, 30, tzinfo=timezone.utc)),
        risk_appetite="balanced",
    )

    assert result.decisions[0].action == "hold"
    assert result.decisions[0].status == "blocked"
    assert result.decisions[0].reason_code == "open_new_disabled"


def test_intraday_rebalance_pipeline_executes_exit_for_existing_position(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    now = datetime(2026, 6, 2, 15, 30, tzinfo=timezone.utc)
    ledger = PortfolioLedger(starting_cash_balance=100000.0)
    ledger.record_stock_execution(
        ticker="AAPL",
        quantity=5.0,
        fill_price=125.0,
        trade_date=now.date(),
        strategy_id="relative_strength_rotation_v1",
        trade_identity="tactical_stock_trade",
        executed_at=now,
    )
    repository.replace_paper_positions(tuple(ledger.positions.values()))
    broker = PaperStockBroker(api_key="key", secret_key="secret", client=_CapturingClient(), now=lambda: now)
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
                "generated_at": "2026-06-02T15:30:00+00:00",
            }
        },
        broker=broker,
    )

    result = pipeline.run(
        rebalance_requests=(_request(existing_position=True, allow_open_new=False),),
        portfolio_context=ledger.build_portfolio_context(as_of=now),
        risk_appetite="balanced",
        trade_date=now,
        execute_approved=True,
    )

    assert result.decisions[0].action == "exit"
    assert result.decisions[0].status == "approved"
    assert len(repository.paper_orders) == 1
    assert repository.paper_orders[0].action == "exit"


def test_intraday_rebalance_pipeline_forces_reduce_from_portfolio_risk_intent(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    now = datetime(2026, 6, 2, 15, 30, tzinfo=timezone.utc)
    ledger = PortfolioLedger(starting_cash_balance=100000.0)
    ledger.record_stock_execution(
        ticker="AAPL",
        quantity=5.0,
        fill_price=125.0,
        trade_date=now.date(),
        strategy_id="relative_strength_rotation_v1",
        trade_identity="tactical_stock_trade",
        executed_at=now,
    )
    intent = PortfolioRiskIntentRecord.create(
        decision_time=now,
        risk_window="1-5d",
        aggregate_risk_state="mixed_risk",
        position_actions=(
            PositionRiskActionRecord(
                ticker="AAPL",
                trade_identity="tactical_stock_trade",
                action="force_reduce",
                risk_source="own_event",
                severity="high",
                max_allowed_weight_override=None,
                reason_code="own_event_force_reduce",
                metadata_json={},
            ),
        ),
        metadata_json={},
    )
    pipeline = IntradayRebalancePipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5-mini",
        agent_runner=lambda prompt, model: {
            "content": {
                "ticker": "AAPL",
                "action": "hold",
                "thesis": "Hold unless external risk overrides.",
                "confidence": 0.40,
                "target_weight": 0.05,
                "max_loss_pct": 0.02,
                "urgency": "medium",
                "rationale": ["waiting"],
                "risk_checks": ["liquidity_ok"],
                "schema_version": "v1",
                "generated_at": "2026-06-02T15:30:00+00:00",
            }
        },
    )

    result = pipeline.run(
        rebalance_requests=(_request(existing_position=True, allow_open_new=False),),
        portfolio_context=ledger.build_portfolio_context(as_of=now),
        risk_appetite="balanced",
        portfolio_risk_intent=intent,
    )

    assert result.decisions[0].action == "reduce"
    assert result.decisions[0].status == "approved"
    assert result.decisions[0].reason_code == "own_event_force_reduce"
    assert result.decisions[0].approved_quantity == 5.0


def test_intraday_rebalance_attaches_sector_cluster_generated_hedge_payload(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    now = datetime(2026, 6, 2, 15, 30, tzinfo=timezone.utc)
    ledger = PortfolioLedger(starting_cash_balance=100000.0)
    ledger.record_stock_execution(
        ticker="AAPL",
        quantity=5.0,
        fill_price=125.0,
        trade_date=now.date(),
        strategy_id="relative_strength_rotation_v1",
        trade_identity="tactical_stock_trade",
        executed_at=now,
    )
    intent = PortfolioRiskIntentRecord.create(
        decision_time=now,
        risk_window="1-5d",
        aggregate_risk_state="event_cluster_risk",
        hedge_actions=(
            HedgeActionRecord(
                action="open_hedge",
                risk_source="sector_event_cluster",
                severity="high",
                target_underlier="SMH",
                target_exposure_type="sector",
                coverage_ratio=0.5,
                reason_code="sector_event_cluster_overlay",
                metadata_json={"sector": "Semiconductors"},
            ),
        ),
    )
    pipeline = IntradayRebalancePipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5-mini",
        agent_runner=lambda prompt, model: {
            "content": {
                "ticker": "AAPL",
                "action": "reduce",
                "thesis": "Trim while the cluster alert is active.",
                "confidence": 0.79,
                "target_weight": 0.0,
                "max_loss_pct": 0.02,
                "urgency": "high",
                "rationale": ["cluster_risk"],
                "risk_checks": ["liquidity_ok"],
                "schema_version": "v1",
                "generated_at": "2026-06-02T15:30:00+00:00",
            }
        },
    )

    result = pipeline.run(
        rebalance_requests=(_request(existing_position=True, allow_open_new=False),),
        portfolio_context=ledger.build_portfolio_context(as_of=now),
        risk_appetite="balanced",
        portfolio_risk_intent=intent,
    )

    assert result.decisions[0].risk_decision_id is not None
    assert repository.risk_decisions[0].generated_hedge_action["risk_source"] == "sector_event_cluster"


def test_intraday_rebalance_attaches_close_generated_hedge_payload(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    now = datetime(2026, 6, 2, 15, 30, tzinfo=timezone.utc)
    ledger = PortfolioLedger(starting_cash_balance=100000.0)
    ledger.record_stock_execution(
        ticker="AAPL",
        quantity=5.0,
        fill_price=125.0,
        trade_date=now.date(),
        strategy_id="relative_strength_rotation_v1",
        trade_identity="tactical_stock_trade",
        executed_at=now,
    )
    intent = PortfolioRiskIntentRecord.create(
        decision_time=now,
        risk_window="1-5d",
        aggregate_risk_state="risk_normalized",
        hedge_actions=(
            HedgeActionRecord(
                action="close_hedge",
                risk_source="risk_normalized",
                severity="watch",
                target_underlier="QQQ",
                target_exposure_type="assignment",
                coverage_ratio=1.0,
                reason_code="risk_overlay_normalized",
                metadata_json={"option_strategy_type": "long_call"},
            ),
        ),
    )
    pipeline = IntradayRebalancePipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5-mini",
        agent_runner=lambda prompt, model: {
            "content": {
                "ticker": "AAPL",
                "action": "reduce",
                "thesis": "Risk normalized, keep trimming the cash equity.",
                "confidence": 0.79,
                "target_weight": 0.0,
                "max_loss_pct": 0.02,
                "urgency": "high",
                "rationale": ["risk_normalized"],
                "risk_checks": ["liquidity_ok"],
                "schema_version": "v1",
                "generated_at": "2026-06-02T15:30:00+00:00",
            }
        },
    )

    result = pipeline.run(
        rebalance_requests=(_request(existing_position=True, allow_open_new=False),),
        portfolio_context=ledger.build_portfolio_context(as_of=now),
        risk_appetite="balanced",
        portfolio_risk_intent=intent,
    )

    assert result.decisions[0].risk_decision_id is not None
    assert repository.risk_decisions[0].generated_hedge_action["action"] == "close_hedge"
    assert repository.risk_decisions[0].generated_hedge_action["target_exposure_type"] == "assignment"


def test_intraday_rebalance_blocks_option_add_when_option_data_is_stale(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    ledger = PortfolioLedger(starting_cash_balance=100000.0)
    pipeline = IntradayRebalancePipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5-mini",
        agent_runner=lambda prompt, model: {
            "content": {
                "ticker": "QQQ",
                "action": "adjust_option_strategy",
                "thesis": "Resize the hedge intraday.",
                "confidence": 0.7,
                "target_weight": 0.0,
                "max_loss_pct": 0.02,
                "urgency": "high",
                "rationale": ["option_mark_changed"],
                "risk_checks": ["structure_ok"],
                "schema_version": "v1",
                "generated_at": "2026-06-02T15:30:00+00:00",
            }
        },
    )

    result = pipeline.run(
        rebalance_requests=(
            _request(
                existing_position=True,
                allow_open_new=False,
                ticker="QQQ",
                trade_identity="risk_hedge_overlay",
                instrument_type="option",
                strategy_id="risk_manager_hedge_overlay_v1",
                expression_bucket_id="defined_risk_directional_option",
                current_price=320.0,
                signal_freshness={"technical": "fresh", "option_chain": "stale"},
                metadata_json={"option_mark_price": 320.0},
            ),
        ),
        portfolio_context=ledger.build_portfolio_context(as_of=datetime(2026, 6, 2, 15, 30, tzinfo=timezone.utc)),
        risk_appetite="balanced",
    )

    assert result.decisions[0].action == "hold"
    assert result.decisions[0].status == "blocked"
    assert result.decisions[0].reason_code == "stale_option_data"


def test_intraday_rebalance_can_emit_roll_option_strategy_for_event_risk(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    ledger = PortfolioLedger(starting_cash_balance=100000.0)
    pipeline = IntradayRebalancePipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5-mini",
        agent_runner=lambda prompt, model: {
            "content": {
                "ticker": "NVDA",
                "action": "roll_option_strategy",
                "thesis": "Roll before the event reaches expiry.",
                "confidence": 0.83,
                "target_weight": 0.0,
                "max_loss_pct": 0.03,
                "urgency": "high",
                "rationale": ["event_risk"],
                "risk_checks": ["roll_preferred"],
                "schema_version": "v1",
                "generated_at": "2026-06-02T15:30:00+00:00",
            }
        },
    )

    result = pipeline.run(
        rebalance_requests=(
            _request(
                existing_position=True,
                allow_open_new=False,
                ticker="NVDA",
                trade_identity="tactical_option_trade",
                instrument_type="option",
                strategy_id="strong_theme_catalyst_continuation_v1",
                expression_bucket_id="defined_risk_income_spread",
                current_price=540.0,
                signal_freshness={"technical": "fresh", "option_chain": "fresh"},
                metadata_json={"event_through_expiry": True, "option_mark_price": 540.0},
            ),
        ),
        portfolio_context=ledger.build_portfolio_context(as_of=datetime(2026, 6, 2, 15, 30, tzinfo=timezone.utc)),
        risk_appetite="balanced",
    )

    assert result.decisions[0].action == "hold"
    assert result.decisions[0].status == "blocked"
    assert result.decisions[0].reason_code == "event_risk_blocked"
