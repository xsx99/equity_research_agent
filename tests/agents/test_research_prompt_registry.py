"""Unit tests for the shared agent prompt registry and research-agent helpers."""
from __future__ import annotations

import textwrap

import json

import pytest

from src.agents.prompt_registry import PromptRegistry
from src.agents.research import (
    DEFAULT_MODEL_NAME,
    ResearchAgent,
    ResearchInputPayload,
    StructuredResearchOutput,
    _coerce_json_object,
    _get_google_api_key,
    _should_use_gemini_backend,
)
from src.core import config as app_config
from src.tools import ToolContext, ToolRegistry


def test_prompt_registry_loads_research_prompt_metadata(tmp_path):
    prompt_dir = tmp_path / "prompts" / "research"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "research_v1.yaml"
    prompt_file.write_text(
        textwrap.dedent(
            """
            prompt_id: research
            prompt_version: v1
            pipeline_name: research
            output_schema_id: structured_research_output
            output_schema_version: v1
            template: |
              Ticker: {{ ticker }}
              Input JSON: {{ input_payload_json }}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    registry = PromptRegistry(root=tmp_path / "prompts")
    template = registry.load("research", "v1")

    assert template.prompt_id == "research"
    assert template.prompt_version == "v1"
    assert template.pipeline_name == "research"
    assert template.output_schema_id == "structured_research_output"
    assert template.output_schema_version == "v1"
    assert template.template_path == "research/research_v1.yaml"
    assert template.template_hash


def test_prompt_registry_renders_research_prompt(tmp_path):
    prompt_dir = tmp_path / "prompts" / "research"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "research_v1.yaml"
    prompt_file.write_text(
        textwrap.dedent(
            """
            prompt_id: research
            prompt_version: v1
            pipeline_name: research
            output_schema_id: structured_research_output
            output_schema_version: v1
            template: |
              Ticker: {{ ticker }}
              Input JSON: {{ input_payload_json }}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    registry = PromptRegistry(root=tmp_path / "prompts")
    rendered = registry.render(
        "research",
        "v1",
        {
            "ticker": "AAPL",
            "input_payload_json": '{"ticker": "AAPL"}',
        },
    )

    assert rendered.text == 'Ticker: AAPL\nInput JSON: {"ticker": "AAPL"}\n'
    assert rendered.rendered_prompt_hash


def test_default_model_name_is_gemini_flash_lite():
    assert DEFAULT_MODEL_NAME == "gemini-2.5-flash-lite"


def test_should_use_gemini_backend_for_gemini_models():
    assert _should_use_gemini_backend("gemini-2.5-flash-lite") is True


def test_should_not_use_gemini_backend_for_non_gemini_models():
    assert _should_use_gemini_backend("gpt-4.1-mini") is False


def test_get_google_api_key_prefers_google_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setattr(app_config, "GOOGLE_API_KEY", "config-key")
    assert _get_google_api_key() == "google-key"


def test_get_google_api_key_falls_back_to_config(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(app_config, "GOOGLE_API_KEY", "config-key")
    assert _get_google_api_key() == "config-key"


def test_coerce_dict_passthrough():
    payload = {"key": "val"}
    assert _coerce_json_object(payload) is payload


def test_coerce_json_string():
    result = _coerce_json_object('{"a": 1, "b": 2}')
    assert result == {"a": 1, "b": 2}


def test_coerce_bytes():
    result = _coerce_json_object(b'{"x": true}')
    assert result == {"x": True}


def test_coerce_strips_markdown_fences():
    text = '```json\n{"decision": "bullish"}\n```'
    result = _coerce_json_object(text)
    assert result["decision"] == "bullish"


def test_coerce_extracts_json_from_surrounding_text():
    text = 'Here is my analysis: {"decision": "neutral"} -- that is all.'
    result = _coerce_json_object(text)
    assert result["decision"] == "neutral"


def test_coerce_empty_string_raises():
    with pytest.raises(ValueError, match="empty_llm_response"):
        _coerce_json_object("")


def test_coerce_whitespace_only_raises():
    with pytest.raises(ValueError, match="empty_llm_response"):
        _coerce_json_object("   ")


def test_coerce_non_json_string_raises():
    with pytest.raises(ValueError, match="llm_response_is_not_valid_json_object"):
        _coerce_json_object("This is not JSON at all.")


def test_coerce_unsupported_type_raises():
    with pytest.raises(TypeError, match="unsupported_llm_response_type"):
        _coerce_json_object(12345)


def test_coerce_object_with_content_attr():
    class FakeResponse:
        content = '{"decision": "bearish"}'

    result = _coerce_json_object(FakeResponse())
    assert result["decision"] == "bearish"


def _valid_input() -> dict:
    return {
        "ticker": "AAPL",
        "as_of": "2026-03-21T12:00:00Z",
        "price_snapshot": {
            "last_price": 210.0,
            "return_1d": 0.01,
            "return_5d": 0.03,
            "return_since_market_open": 0.015,
        },
        "context": {"sector": "Technology", "earnings_in_days": 9},
        "news": [{"title": "Sample headline", "summary": "A summary."}],
        "global_context": {
            "as_of": "2026-03-21T11:58:00Z",
            "indicators": {
                "vix": {
                    "label": "CBOE Volatility Index",
                    "source": "FRED:VIXCLS",
                    "unit": "index",
                    "value": 18.2,
                    "observed_on": "2026-03-21",
                }
            },
            "official_updates": [],
            "trump_updates": [],
            "geopolitical_news": [],
        },
    }


def _valid_output() -> dict:
    return {
        "decision": "bullish",
        "confidence": 0.88,
        "time_horizon": "1d",
        "actionability": "actionable",
        "thesis_summary": "Macro and insider signals align.",
        "key_drivers": ["Global risk-on regime", "Insider buying"],
        "counterarguments": ["Valuation is elevated"],
        "invalidators": ["VIX spikes above 25"],
    }


def test_research_input_payload_accepts_valid_data():
    payload = ResearchInputPayload.model_validate(_valid_input())
    assert payload.ticker == "AAPL"
    assert payload.global_context.indicators["vix"].value == 18.2


def test_research_input_payload_requires_global_context():
    bad = _valid_input()
    bad.pop("global_context")
    payload = ResearchInputPayload.model_validate(bad)
    assert payload.global_context is not None
    assert payload.global_context.indicators == {}


def test_structured_output_accepts_valid_payload():
    output = StructuredResearchOutput.model_validate(_valid_output())
    assert output.decision == "bullish"
    assert output.confidence == 0.88


def test_structured_output_rejects_confidence_out_of_range():
    bad = _valid_output()
    bad["confidence"] = 1.5
    with pytest.raises(Exception):
        StructuredResearchOutput.model_validate(bad)


def test_research_agent_runs_with_shared_agent_prompt_registry(tmp_path):
    prompt_dir = tmp_path / "prompts" / "research"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "research_v1.yaml"
    prompt_file.write_text(
        textwrap.dedent(
            """
            prompt_id: research
            prompt_version: v1
            pipeline_name: research
            output_schema_id: structured_research_output
            output_schema_version: v1
            template: |
              Ticker: {{ ticker }}
              Input JSON: {{ input_payload_json }}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    registry = PromptRegistry(root=tmp_path / "prompts")

    def runner(prompt: str, model_name: str) -> str:
        assert "Ticker: AAPL" in prompt
        assert '"ticker": "AAPL"' in prompt
        return json.dumps(_valid_output())

    agent = ResearchAgent(
        tool_registry=ToolRegistry(),
        prompt_registry=registry,
        model_name="gemini-2.5-flash-lite",
        agent_runner=runner,
    )

    result = agent.run(_valid_input(), ToolContext())

    assert result.success is True
    assert result.output_data is not None
    assert result.output_data["decision"] == "bullish"
