from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from scripts import run_trading_live_preopen_order_smoke
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
        lambda *, ticker, execute_paper_orders: {
            "status": "passed",
            "ticker": ticker,
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
        execute_paper_orders=False,
        order=None,
    )

    assert status == "passed"
