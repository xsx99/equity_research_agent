from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
import sys

from src.agents.prompt_registry import PromptRegistry
from src.agents.trading import TradingAgent, _coerce_json_object, _default_agent_runner
from src.tools.context import ToolContext


def _write_prompt(tmp_path):
    prompt_dir = tmp_path / "prompts" / "trading"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "trading_decision_v1.yaml"
    prompt_file.write_text(
        "prompt_id: trading_decision\n"
        "prompt_version: v1\n"
        "pipeline_name: trading\n"
        "output_schema_id: trading_decision\n"
        "output_schema_version: v1\n"
        "template: |\n"
        "  Decide what to do for {{ ticker }}.\n"
        "  Input JSON: {{ input_payload_json }}\n",
        encoding="utf-8",
    )
    return PromptRegistry(root=tmp_path / "prompts")


def _payload():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return {
        "ticker": "NVDA",
        "decision_time": now.isoformat(),
        "available_for_decision_at": now.isoformat(),
        "has_existing_position": False,
            "signal_snapshot": {
                "signal_snapshot_id": "snapshot-1",
                "snapshot_type": "pre_open",
                "decision_time": now.isoformat(),
                "available_for_decision_at": now.isoformat(),
            "signal_json": {
                "technical": {"rs_vs_spy_1d": 0.02, "relative_volume": 1.6},
                "fundamental": {"quality_score": 0.92},
                "events_news": {"catalyst_quality_score": 0.88},
            },
                "source_freshness_json": {"technical": "fresh", "fundamental": "fresh", "events_news": "fresh"},
                "missing_signals_json": [],
                "stale_signals_json": [],
                "evidence_items": [
                    {
                        "source": "alpaca_live",
                        "source_table": "event_news_items",
                        "source_record_id": "d8e368ec-7912-538e-bb54-740481024fc0",
                        "source_text": "NVIDIA raises guidance after AI demand accelerates",
                        "available_time": now.isoformat(),
                    }
                ],
            },
        "candidate_context": {
            "candidate_score": 0.81,
            "strategy_id": "relative_strength_rotation_v1",
            "strategy_version": "v1",
            "selection_source": "scanner",
            "selection_reason": "relative strength confirmed",
            "benchmark_context": {"primary_benchmark": "QQQ"},
            "core_signal_evidence": {"technical.rs_vs_spy_1d": 0.02},
            "historical_outcomes": [],
        },
        "classification_context": {
            "expression_bucket_id": "long_stock",
            "trade_identity": "tactical_stock_trade",
            "classification_result_status": "actionable_trade",
            "selected_strategy_context": {"candidate_score": 0.81},
        },
        "risk_context": {"status": "approved", "approved_weight": 0.04, "reason_code": "within_limits"},
        "manual_request_context": {"manual_request_id": None, "manual_request_mode": None},
    }


def test_trading_agent_retries_once_and_returns_validated_output(tmp_path):
    registry = _write_prompt(tmp_path)
    calls: list[str] = []

    def runner(prompt: str, model_name: str):
        calls.append(prompt)
        if len(calls) == 1:
            return {
                "content": "not-json",
                "usage": {
                    "provider": "openai",
                    "model": model_name,
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "total_tokens": 13,
                    "estimated_cost": 0.001,
                    "latency_ms": 50,
                },
            }
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "enter_long",
                "strategy_id": "relative_strength_rotation_v1",
                "expression_bucket_id": "long_stock",
                "trade_identity": "tactical_stock_trade",
                "instrument_type": "stock",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.74,
                "confidence_basis": {"calibration_bucket": "bullish_relative_strength"},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.04,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": "market_open",
                "exit_plan": "close_or_invalidator",
                "thesis": "Relative strength remains intact.",
                "key_drivers": ["sector_relative_strength"],
                "counterarguments": ["valuation is elevated versus peers"],
                "risk_checks": ["liquidity_ok"],
                "invalidators": ["QQQ closes below prior close"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    agent = TradingAgent(
        tool_registry=None,
        prompt_registry=registry,
        model_name="gpt-5-mini",
        agent_runner=runner,
    )

    result = agent.run(_payload(), ToolContext())

    assert result.success is True
    assert result.output_data["decision"] == "enter_long"
    assert result.output_data["key_drivers"] == ["sector_relative_strength"]
    assert result.output_data["counterarguments"] == ["valuation is elevated versus peers"]
    assert result.metadata["retry_count"] == 1
    assert "previous validation error" in calls[1].lower()
    assert '"signal_snapshot"' in calls[0]
    assert "NVIDIA raises guidance after AI demand accelerates" in calls[0]
    assert '"source_record_refs_json"' not in calls[0]


def test_trading_agent_returns_safe_fallback_after_retry_failure(tmp_path):
    registry = _write_prompt(tmp_path)

    def runner(prompt: str, model_name: str):
        return {
            "content": "still-not-json",
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 10,
                "completion_tokens": 3,
                "total_tokens": 13,
                "estimated_cost": 0.001,
                "latency_ms": 50,
            },
        }

    agent = TradingAgent(
        tool_registry=None,
        prompt_registry=registry,
        model_name="gpt-5-mini",
        agent_runner=runner,
    )

    result = agent.run(_payload(), ToolContext())

    assert result.success is False
    assert result.output_data["decision"] == "no_trade"
    assert result.output_data["fallback_action"] == "no_trade"
    assert result.metadata["retry_count"] == 1


def test_trading_agent_normalizes_common_model_output_shape_mismatches(tmp_path):
    registry = _write_prompt(tmp_path)

    def runner(prompt: str, model_name: str):
        return {
            "content": {
                "ticker": "NVDA",
                "decision": "enter_long",
                "strategy_id": "relative_strength_rotation_v1",
                "expression_bucket_id": "long_stock",
                "trade_identity": "tactical_stock_trade",
                "instrument_type": "stock",
                "selection_source": "scanner",
                "manual_request_id": None,
                "confidence": 0.74,
                "confidence_basis": {"calibration_bucket": "bullish_relative_strength"},
                "benchmark_context": {"primary_benchmark": "QQQ"},
                "target_weight": 0.04,
                "max_loss_pct": 0.02,
                "time_horizon": "2w-3m",
                "entry_plan": {"type": "limit_order", "price": None},
                "exit_plan": {"type": "stop_loss", "price": None},
                "reason": "Relative strength remains intact.",
                "key_signals": ["sector_relative_strength"],
                "counterarguments": ["valuation is elevated versus peers"],
                "risk_checks": ["liquidity_ok"],
                "invalidators": ["QQQ closes below prior close"],
                "learning_factors_used": [],
                "schema_version": "v1",
                "generated_at": "2026-06-01T12:00:00+00:00",
            },
            "usage": {
                "provider": "openai",
                "model": model_name,
                "prompt_tokens": 12,
                "completion_tokens": 20,
                "total_tokens": 32,
                "estimated_cost": 0.002,
                "latency_ms": 75,
            },
        }

    agent = TradingAgent(
        tool_registry=None,
        prompt_registry=registry,
        model_name="gpt-5-mini",
        agent_runner=runner,
    )

    result = agent.run(_payload(), ToolContext())

    assert result.success is True
    assert result.output_data["decision"] == "enter_long"
    assert result.output_data["key_drivers"] == ["sector_relative_strength"]
    assert result.output_data["thesis"] == "Relative strength remains intact."
    assert result.output_data["entry_plan"] == '{"price":null,"type":"limit_order"}'
    assert result.output_data["exit_plan"] == '{"price":null,"type":"stop_loss"}'


def test_trading_json_parser_tolerates_model_escaped_single_quote():
    result = _coerce_json_object('{"ticker": "DELL", "thesis": "DELL\\\'s momentum remains intact."}')

    assert result == {"ticker": "DELL", "thesis": "DELL's momentum remains intact."}


def test_default_trading_agent_runner_uses_phi_agent(monkeypatch):
    class _FakeAgent:
        def __init__(self, *, model, markdown):
            assert model == "fake-model"
            assert markdown is False

        def run(self, prompt):
            assert prompt == "trade prompt"
            return SimpleNamespace(content='{"decision":"no_trade"}')

    monkeypatch.setattr("src.agents.trading._build_phi_model", lambda model_name: "fake-model")
    monkeypatch.setitem(sys.modules, "phi", ModuleType("phi"))
    phi_agent_module = ModuleType("phi.agent")
    phi_agent_module.Agent = _FakeAgent
    monkeypatch.setitem(sys.modules, "phi.agent", phi_agent_module)

    response = _default_agent_runner("trade prompt", "gpt-5-mini")

    assert response == '{"decision":"no_trade"}'


def test_default_trading_agent_runner_uses_direct_openrouter_runner(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_openrouter_runner(prompt: str, model_name: str):
        calls.append((prompt, model_name))
        return {"content": '{"ok": true}'}

    monkeypatch.setattr(
        "src.agents.trading.run_openrouter_chat_completion",
        fake_openrouter_runner,
    )

    response = _default_agent_runner("reflect prompt", "moonshotai/kimi-k2.6")

    assert response == {"content": '{"ok": true}'}
    assert calls == [("reflect prompt", "moonshotai/kimi-k2.6")]
