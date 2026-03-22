"""Unit tests for PromptRegistry, Prompt, and _coerce_json_object."""
from __future__ import annotations

import textwrap

import pytest

from src.prompts.registry import Prompt, PromptRegistry
from src.agents.research import (
    DEFAULT_MODEL_NAME,
    _coerce_json_object,
    _get_google_api_key,
    _should_use_gemini_backend,
    ResearchInputPayload,
    StructuredResearchOutput,
)
from src.core import config as app_config


# ---------------------------------------------------------------------------
# Prompt dataclass
# ---------------------------------------------------------------------------


def test_prompt_versioned_id():
    p = Prompt(id="research", version="v1", template="Hello $name")
    assert p.versioned_id == "research_v1"


def test_prompt_render_substitutes_variables():
    p = Prompt(id="research", version="v1", template="Ticker: $ticker, Date: $date")
    rendered = p.render(ticker="AAPL", date="2026-03-21")
    assert rendered == "Ticker: AAPL, Date: 2026-03-21"


def test_prompt_render_safe_substitute_leaves_unknown_vars():
    p = Prompt(id="research", version="v1", template="Hello $name, unknown: $other")
    rendered = p.render(name="World")
    assert "World" in rendered
    assert "$other" in rendered  # safe_substitute leaves unknown placeholders


def test_prompt_is_frozen():
    p = Prompt(id="research", version="v1", template="text")
    with pytest.raises(Exception):
        p.id = "changed"  # type: ignore[misc]


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


# ---------------------------------------------------------------------------
# PromptRegistry
# ---------------------------------------------------------------------------


def _fresh_registry() -> PromptRegistry:
    return PromptRegistry()


def test_register_and_get():
    reg = _fresh_registry()
    p = Prompt(id="research", version="v1", template="Hello $ticker")
    reg.register(p)
    fetched = reg.get("research", "v1")
    assert fetched is p


def test_get_missing_raises_file_not_found():
    reg = _fresh_registry()
    with pytest.raises(FileNotFoundError, match="Prompt definition not found"):
        reg.get("nonexistent", "v99")


def test_get_loads_yaml_prompt_definition(tmp_path):
    prompt_file = tmp_path / "research_v1.yaml"
    prompt_file.write_text(
        textwrap.dedent(
            """
            id: research
            version: v1
            description: Research prompt for equity analysis
            body: |
              Hello $ticker
              Stay cautious.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    reg = PromptRegistry(templates_dir=tmp_path)
    prompt = reg.get("research", "v1")

    assert prompt.id == "research"
    assert prompt.version == "v1"
    assert prompt.description == "Research prompt for equity analysis"
    assert prompt.template == "Hello $ticker\nStay cautious.\n"


def test_get_raises_for_yaml_metadata_mismatch(tmp_path):
    prompt_file = tmp_path / "research_v1.yaml"
    prompt_file.write_text(
        textwrap.dedent(
            """
            id: risk
            version: v1
            body: |
              Hello
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    reg = PromptRegistry(templates_dir=tmp_path)
    with pytest.raises(ValueError, match="Prompt id mismatch"):
        reg.get("research", "v1")


def test_register_overwrites_existing():
    reg = _fresh_registry()
    p1 = Prompt(id="research", version="v1", template="v1 template")
    p2 = Prompt(id="research", version="v1", template="v1 updated")
    reg.register(p1)
    reg.register(p2)
    assert reg.get("research", "v1").template == "v1 updated"


def test_list_loaded_empty():
    reg = _fresh_registry()
    assert reg.list_loaded() == []


def test_list_loaded_after_register():
    reg = _fresh_registry()
    reg.register(Prompt(id="research", version="v1", template="t"))
    reg.register(Prompt(id="risk", version="v2", template="r"))
    loaded = reg.list_loaded()
    assert set(loaded) == {"research_v1", "risk_v2"}


def test_get_default_returns_singleton():
    # Reset the class-level singleton to test creation
    PromptRegistry._instance = None
    a = PromptRegistry.get_default()
    b = PromptRegistry.get_default()
    assert a is b
    PromptRegistry._instance = None  # clean up


# ---------------------------------------------------------------------------
# _coerce_json_object
# ---------------------------------------------------------------------------


def test_coerce_dict_passthrough():
    d = {"key": "val"}
    assert _coerce_json_object(d) is d


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
    text = 'Here is my analysis: {"decision": "neutral"} — that is all.'
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


# ---------------------------------------------------------------------------
# Pydantic schema validation
# ---------------------------------------------------------------------------


def _valid_input() -> dict:
    return {
        "ticker": "AAPL",
        "as_of": "2026-03-21T12:00:00Z",
        "price_snapshot": {"last_price": 210.0, "return_1d": 0.01, "return_5d": 0.03},
        "context": {"sector": "Technology", "earnings_in_days": 9},
        "news": [{"title": "Sample headline", "summary": "A summary."}],
    }


def test_research_input_payload_valid():
    payload = ResearchInputPayload.model_validate(_valid_input())
    assert payload.ticker == "AAPL"
    assert payload.price_snapshot.last_price == pytest.approx(210.0)
    assert len(payload.news) == 1


def test_research_input_payload_missing_ticker_raises():
    data = _valid_input()
    del data["ticker"]
    with pytest.raises(Exception):
        ResearchInputPayload.model_validate(data)


def test_research_input_payload_extra_fields_forbidden():
    data = _valid_input()
    data["unexpected_field"] = "oops"
    with pytest.raises(Exception):
        ResearchInputPayload.model_validate(data)


def test_research_input_payload_defaults_empty_news():
    data = _valid_input()
    del data["news"]
    payload = ResearchInputPayload.model_validate(data)
    assert payload.news == []


def test_structured_output_valid():
    out = StructuredResearchOutput.model_validate({
        "decision": "bullish",
        "confidence": 0.75,
        "time_horizon": "3d",
        "actionability": "watch",
        "thesis_summary": "Strong insider buying.",
        "key_drivers": ["Momentum"],
        "counterarguments": ["Valuation"],
        "invalidators": ["Break below support"],
    })
    assert out.decision == "bullish"
    assert out.confidence == pytest.approx(0.75)


def test_structured_output_confidence_above_one_raises():
    with pytest.raises(Exception):
        StructuredResearchOutput.model_validate({
            "decision": "bullish",
            "confidence": 1.5,
            "time_horizon": "3d",
            "actionability": "watch",
            "thesis_summary": "x",
            "key_drivers": [],
            "counterarguments": [],
            "invalidators": [],
        })


def test_structured_output_invalid_decision_raises():
    with pytest.raises(Exception):
        StructuredResearchOutput.model_validate({
            "decision": "very_bullish",  # not a valid literal
            "confidence": 0.5,
            "time_horizon": "3d",
            "actionability": "watch",
            "thesis_summary": "x",
            "key_drivers": [],
            "counterarguments": [],
            "invalidators": [],
        })


def test_structured_output_empty_thesis_raises():
    with pytest.raises(Exception):
        StructuredResearchOutput.model_validate({
            "decision": "neutral",
            "confidence": 0.5,
            "time_horizon": "1d",
            "actionability": "abstain",
            "thesis_summary": "",  # min_length=1
            "key_drivers": [],
            "counterarguments": [],
            "invalidators": [],
        })


def test_structured_output_extra_fields_forbidden():
    with pytest.raises(Exception):
        StructuredResearchOutput.model_validate({
            "decision": "neutral",
            "confidence": 0.5,
            "time_horizon": "1d",
            "actionability": "abstain",
            "thesis_summary": "ok",
            "key_drivers": [],
            "counterarguments": [],
            "invalidators": [],
            "surprise_field": "nope",
        })
