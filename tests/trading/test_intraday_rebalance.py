from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.agents.prompt_registry import PromptRegistry
from src.trading.brokers.paper_stock import PaperStockBroker
from src.trading.intraday.rebalance import IntradayRebalancePipeline, IntradayRebalanceRequest
from src.trading.portfolio.state import PortfolioLedger
from src.trading.repositories.in_memory import InMemoryTradingRepository


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


def _request(*, existing_position: bool, allow_open_new: bool, action: str = "exit") -> IntradayRebalanceRequest:
    now = datetime(2026, 6, 2, 15, 30, tzinfo=timezone.utc)
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
        existing_position=existing_position,
        current_position_quantity=5.0 if existing_position else 0.0,
        current_position_market_value=625.0 if existing_position else 0.0,
        candidate_score=0.82,
        target_weight=0.05,
        signal_freshness={"technical": "fresh", "events_news": "fresh"},
        delta_vs_baseline_json={"technical": {"last_price": 5.0}},
        delta_vs_previous_json={"technical": {"last_price": 2.0}},
        alerts=(),
        allow_open_new=allow_open_new,
        direct_company_negative_evidence=(action == "exit"),
        bearish_signal_sources=("events_news",) if action == "exit" else (),
        metadata_json={},
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
