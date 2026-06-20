from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from scripts import run_trading_live_preopen_order_smoke
from src.db.models.trading import ManualTickerRequest
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord
from src.trading.workflows.strategy_scoring import StrategyPipelineResult


def test_smoke_agent_runner_emits_enter_long_for_eligible_approved_stock():
    payload = {
        "ticker": "NVDA",
        "signal_snapshot": {
            "signal_snapshot_id": "snapshot-1",
            "snapshot_type": "pre_open",
            "decision_time": "2026-06-03T12:45:00+00:00",
            "available_for_decision_at": "2026-06-03T12:45:00+00:00",
            "signal_json": {},
            "source_freshness_json": {},
            "missing_signals_json": [],
            "stale_signals_json": [],
            "evidence_items": [],
        },
        "candidate_context": {
            "candidate_score": 0.7,
            "strategy_run_id": "run-1",
            "strategy_id": "relative_strength_rotation_v1",
            "strategy_version": "v1",
            "direction": "bullish",
            "selection_source": "manual_request",
            "selection_reason": "smoke test",
            "benchmark_context": {"primary_benchmark": "QQQ"},
            "core_signal_evidence": {},
            "historical_outcomes": [],
        },
        "classification_context": {
            "expression_bucket_id": "long_stock",
            "trade_identity": "tactical_stock_trade",
            "classification_result_status": "actionable_trade",
            "instrument_type": "stock",
            "selected_strategy_context": {},
            "expression_fallback_plan": [],
        },
        "risk_context": {"status": "approved", "approved_weight": 0.03},
        "manual_request_context": {
            "manual_request_id": "request-1",
            "manual_request_mode": "paper_trade_eligible",
        },
    }

    response = run_trading_live_preopen_order_smoke._smoke_agent_runner(
        f"Ticker: NVDA\nInput JSON:\n{json.dumps(payload)}",
        "gpt-5-mini",
    )

    assert response["content"]["decision"] == "enter_long"
    assert response["content"]["target_weight"] == 0.03
    assert response["content"]["counterarguments"] == ["smoke_only"]


def test_smoke_agent_runner_emits_open_option_strategy_for_eligible_approved_option():
    payload = {
        "ticker": "QQQ",
        "signal_snapshot": {
            "signal_snapshot_id": "snapshot-1",
            "snapshot_type": "pre_open",
            "decision_time": "2026-06-03T12:45:00+00:00",
            "available_for_decision_at": "2026-06-03T12:45:00+00:00",
            "signal_json": {},
            "source_freshness_json": {},
            "missing_signals_json": [],
            "stale_signals_json": [],
            "evidence_items": [],
        },
        "candidate_context": {
            "candidate_score": 0.64,
            "strategy_run_id": "run-1",
            "strategy_id": "macro_overlay_v1",
            "strategy_version": "v1",
            "direction": "bearish",
            "selection_source": "manual_request",
            "selection_reason": "smoke test",
            "benchmark_context": {"primary_benchmark": "SPY"},
            "core_signal_evidence": {},
            "historical_outcomes": [],
        },
        "classification_context": {
            "expression_bucket_id": "defined_risk_directional_option",
            "trade_identity": "tactical_option_trade",
            "classification_result_status": "actionable_trade",
            "instrument_type": "stock",
            "selected_strategy_context": {"selected_expression_bucket_id": "defined_risk_directional_option"},
            "expression_fallback_plan": [
                {
                    "expression_bucket_id": "defined_risk_directional_option",
                    "expression_bucket_version": "v1",
                    "trade_identity": "tactical_option_trade",
                    "instrument_type": "option",
                    "decision_action": "open_option_strategy",
                    "rank": 0,
                    "is_selected": True,
                }
            ],
        },
        "risk_context": {"status": "approved", "approved_weight": 0.02},
        "manual_request_context": {
            "manual_request_id": "request-1",
            "manual_request_mode": "paper_trade_eligible",
        },
    }

    response = run_trading_live_preopen_order_smoke._smoke_agent_runner(
        f"Ticker: QQQ\nInput JSON:\n{json.dumps(payload)}",
        "gpt-5-mini",
    )

    assert response["content"]["decision"] == "open_option_strategy"
    assert response["content"]["instrument_type"] == "option"
    assert response["content"]["target_weight"] == 0.02


def test_extract_input_payload_ignores_prompt_text_after_json():
    payload = {"ticker": "NVDA", "candidate_context": {"strategy_id": "relative_strength_rotation_v1"}}

    parsed = run_trading_live_preopen_order_smoke._extract_input_payload(
        "Header\nInput JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Return only one corrected JSON object with no markdown."
    )

    assert parsed == payload


def test_smoke_strategy_pipeline_forces_actionable_trade_for_target_ticker():
    now = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        signal_snapshot_id="snapshot-1",
        ticker="NVDA",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=[],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="manual_request",
        manual_request_id="request-1",
        candidate_score=0.8,
        selection_reason="needs smoke override",
        rejection_reason="no_clean_entry",
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
    )
    existing = TradeClassificationRecord(
        trade_classification_id="classification-1",
        candidate_score_id="candidate-1",
        strategy_run_id="run-1",
        ticker="NVDA",
        selected_strategy_id="relative_strength_rotation_v1",
        selected_strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="watch_only",
        watch_type="ordinary_watch",
        direction="bullish",
        intended_horizon="2w-3m",
        exit_policy="close_or_invalidator",
        result_status="ordinary_watch",
        classification_reason="not actionable",
        selected_strategy_context_json={},
        decision_time=now,
    )

    class _Wrapped:
        def run(self, *, snapshots, decision_time):
            del snapshots, decision_time
            return StrategyPipelineResult(
                strategy_run=SimpleNamespace(strategy_run_id="run-1"),
                candidates=(candidate,),
                selected_trades=(),
                watch_candidates=(),
                classifications=(existing,),
            )

    result = run_trading_live_preopen_order_smoke._SmokeStrategyPipeline(
        wrapped=_Wrapped(),
        target_ticker="NVDA",
        target_instrument="stock",
    ).run(
        snapshots=(),
        decision_time=now,
    )

    assert len(result.classifications) == 1
    assert result.classifications[0].trade_identity == "tactical_stock_trade"
    assert result.classifications[0].result_status == "actionable_trade"


def test_main_prints_json_report(monkeypatch, capsys):
    monkeypatch.setattr(
        run_trading_live_preopen_order_smoke,
        "run_smoke",
        lambda *, ticker, instrument, execute_paper_orders: {
            "status": "passed",
            "ticker": ticker,
            "instrument": instrument,
            "runtime": {"execution": {"mode": "execute" if execute_paper_orders else "dry_run"}},
        },
    )

    exit_code = run_trading_live_preopen_order_smoke.main(["--ticker", "NVDA", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ticker"] == "NVDA"


def test_resolve_smoke_status_treats_dry_run_decision_generation_as_passed():
    runtime = {
        "summary": {
            "risk_decision_count": 1,
            "trading_decision_count": 1,
        },
        "execution": {
            "mode": "dry_run",
            "orders_submitted": 0,
        },
    }

    status = run_trading_live_preopen_order_smoke._resolve_smoke_status(
        runtime=runtime,
        instrument="stock",
        execute_paper_orders=False,
        order=None,
        option_order=None,
    )

    assert status == "passed"


def test_resolve_smoke_status_treats_option_execution_as_passed():
    runtime = {
        "summary": {
            "risk_decision_count": 1,
            "trading_decision_count": 1,
        },
        "execution": {
            "mode": "execute",
            "orders_submitted": 0,
            "option_orders_submitted": 1,
        },
    }

    status = run_trading_live_preopen_order_smoke._resolve_smoke_status(
        runtime=runtime,
        instrument="option",
        execute_paper_orders=True,
        order=None,
        option_order=object(),
    )

    assert status == "passed"


def test_paper_option_json_includes_broker_identifiers():
    order_payload = run_trading_live_preopen_order_smoke._paper_option_order_json(
        SimpleNamespace(
            paper_option_order_id="option-order-1",
            broker_order_id="alpaca-option-order-1",
            client_order_id="client-option-order-1",
            ticker="QQQ",
            status="filled",
            quantity=1,
            option_strategy_type="long_call",
            rejection_reason=None,
        )
    )
    execution_payload = run_trading_live_preopen_order_smoke._paper_option_execution_json(
        SimpleNamespace(
            paper_option_execution_id="option-exec-1",
            broker_order_id="alpaca-option-order-1",
            ticker="QQQ",
            quantity=1,
            fill_price=2.15,
            executed_at=datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc),
        )
    )

    assert order_payload["broker_order_id"] == "alpaca-option-order-1"
    assert order_payload["client_order_id"] == "client-option-order-1"
    assert execution_payload["broker_order_id"] == "alpaca-option-order-1"


def test_build_smoke_trading_decision_pipeline_preserves_source_repository(monkeypatch):
    captured: dict[str, object] = {}

    class _Pipeline:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(run_trading_live_preopen_order_smoke, "TradingDecisionPipeline", _Pipeline)
    monkeypatch.setattr(run_trading_live_preopen_order_smoke.PromptRegistry, "get_default", staticmethod(lambda: "prompt-registry"))
    monkeypatch.setattr(run_trading_live_preopen_order_smoke.app_config, "TRADING_MODEL_NAME", "gpt-5-mini")

    pipeline = run_trading_live_preopen_order_smoke._build_smoke_trading_decision_pipeline(
        repository="trading-repo",
        source_repository="source-repo",
        manual_request_service="manual-service",
    )

    assert pipeline.__class__ is _Pipeline
    assert captured["repository"] == "trading-repo"
    assert captured["source_repository"] == "source-repo"
    assert captured["manual_request_service"] == "manual-service"


def test_ensure_manual_request_scope_reuses_existing_active_ticker_request():
    existing_id = uuid.uuid4()

    class _Query:
        def __init__(self, row):
            self.row = row

        def filter_by(self, **kwargs):
            assert kwargs == {"ticker": "NVDA", "status": "active"}
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def first(self):
            return self.row

    class _Session:
        def __init__(self, row):
            self.row = row
            self.added = []

        def query(self, model):
            assert model is ManualTickerRequest
            return _Query(self.row)

        def add(self, row):
            self.added.append(row)

        def flush(self):
            raise AssertionError("flush should not run when reusing an active manual request")

    session = _Session(
        SimpleNamespace(
            manual_ticker_request_id=existing_id,
            mode="paper_trade_eligible",
        )
    )

    scope = run_trading_live_preopen_order_smoke._ensure_manual_request_scope(
        session=session,
        ticker="NVDA",
        reason="codex live preopen order smoke:stock:NVDA",
        now=datetime(2026, 6, 20, 3, 18, tzinfo=timezone.utc),
    )

    assert scope.request_id == existing_id
    assert scope.owned is False
    assert session.added == []
