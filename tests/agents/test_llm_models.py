from src.agents import strategy_evolution
from src.core import config as app_config


def test_llm_model_defaults_are_explicit_by_pipeline():
    assert app_config.GEMINI_FLASH_25_LITE_MODEL_NAME == "gemini-2.5-flash-lite"
    assert app_config.OPENROUTER_KIMI_K2_6_MODEL_NAME == "moonshotai/kimi-k2.6"
    assert app_config.RESEARCH_MODEL_NAME == app_config.GEMINI_FLASH_25_LITE_MODEL_NAME
    assert app_config.TRADING_MODEL_NAME == app_config.GEMINI_FLASH_25_LITE_MODEL_NAME
    assert app_config.REFLECTION_MODEL_NAME == app_config.OPENROUTER_KIMI_K2_6_MODEL_NAME
    assert app_config.STRATEGY_EVOLUTION_MODEL_NAME == app_config.OPENROUTER_KIMI_K2_6_MODEL_NAME


def test_strategy_evolution_uses_own_model_constant():
    assert strategy_evolution.DEFAULT_MODEL_NAME == app_config.STRATEGY_EVOLUTION_MODEL_NAME


def test_build_phi_model_configures_openrouter_kimi(monkeypatch):
    from src.agents.llm_models import build_phi_model

    class FakeOpenAIChat:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")
    model = build_phi_model("moonshotai/kimi-k2.6", openai_chat_cls=FakeOpenAIChat)

    assert model.kwargs["id"] == "moonshotai/kimi-k2.6"
    assert model.kwargs["api_key"] == "router-key"
    assert model.kwargs["base_url"] == "https://openrouter.ai/api/v1"


def test_build_phi_model_configures_gemini(monkeypatch):
    from src.agents.llm_models import build_phi_model

    class FakeGemini:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    model = build_phi_model("gemini-2.5-flash-lite", gemini_cls=FakeGemini)

    assert model.kwargs == {"id": "gemini-2.5-flash-lite", "api_key": "google-key"}
