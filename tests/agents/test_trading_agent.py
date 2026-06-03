from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
import sys

from src.agents.prompt_registry import PromptRegistry
from src.agents.trading import TradingAgent, _default_agent_runner
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
        "strategy_id": "relative_strength_rotation_v1",
        "expression_bucket_id": "long_stock",
        "trade_identity": "tactical_stock_trade",
        "instrument_type": "stock",
        "selection_source": "scanner",
        "manual_request_id": None,
        "decision_time": now.isoformat(),
        "available_for_decision_at": now.isoformat(),
        "has_existing_position": False,
        "candidate_score": 0.81,
        "benchmark_context": {"primary_benchmark": "QQQ"},
        "confidence_basis": {"calibration_bucket": "bullish_relative_strength"},
        "risk_context": {"status": "approved", "approved_weight": 0.04},
        "source_availability": {"technical": "fresh", "fundamental": "fresh"},
        "historical_outcomes": [],
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
                "key_signals": ["sector_relative_strength"],
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
    assert result.metadata["retry_count"] == 1
    assert "previous validation error" in calls[1].lower()


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
