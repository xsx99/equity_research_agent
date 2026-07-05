from src.agents import strategy_evolution
from src.core import config as app_config


def test_requirements_do_not_pin_openai_client():
    requirements = app_config.REPO_ROOT.joinpath("requirements.txt").read_text(encoding="utf-8")

    assert "\nopenai==" not in f"\n{requirements}"


def test_llm_model_defaults_are_explicit_by_pipeline():
    assert app_config.GEMINI_FLASH_25_LITE_MODEL_NAME == "gemini-2.5-flash-lite"
    assert app_config.OPENROUTER_KIMI_K2_6_MODEL_NAME == "moonshotai/kimi-k2.6"
    assert app_config.RESEARCH_MODEL_NAME == app_config.GEMINI_FLASH_25_LITE_MODEL_NAME
    assert app_config.TRADING_MODEL_NAME == app_config.GEMINI_FLASH_25_LITE_MODEL_NAME
    assert app_config.REFLECTION_MODEL_NAME == app_config.OPENROUTER_KIMI_K2_6_MODEL_NAME
    assert app_config.STRATEGY_EVOLUTION_MODEL_NAME == app_config.OPENROUTER_KIMI_K2_6_MODEL_NAME


def test_strategy_evolution_uses_own_model_constant():
    assert strategy_evolution.DEFAULT_MODEL_NAME == app_config.STRATEGY_EVOLUTION_MODEL_NAME


def test_openrouter_models_use_direct_runner_instead_of_phi_model(monkeypatch):
    from src.agents.llm_models import build_phi_model

    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")

    try:
        build_phi_model("moonshotai/kimi-k2.6")
    except RuntimeError as exc:
        assert "direct OpenRouter runner" in str(exc)
    else:
        raise AssertionError("OpenRouter models must not build a Phi/OpenAIChat model")


def test_openrouter_chat_completion_posts_to_configured_base_url(monkeypatch):
    from src.agents.llm_models import run_openrouter_chat_completion

    requests = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "model": "moonshotai/kimi-k2.6-20260420",
                "choices": [
                    {
                        "message": {"content": '{"ok": true}'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                    "cost": 0.0002,
                },
            }

    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, headers, json):
            requests.append({"url": url, "headers": headers, "json": json, "timeout": self.timeout})
            return FakeResponse()

    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")

    result = run_openrouter_chat_completion(
        "Return JSON",
        "moonshotai/kimi-k2.6",
        http_client_cls=FakeClient,
        now_ms=lambda: 1000,
        monotonic_ms=lambda: 1123,
    )

    assert result == {
        "content": '{"ok": true}',
        "usage": {
            "provider": "openrouter",
            "model": "moonshotai/kimi-k2.6-20260420",
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
            "estimated_cost": 0.0002,
            "latency_ms": 123,
        },
    }
    assert requests == [
        {
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "headers": {
                "Authorization": "Bearer router-key",
                "Content-Type": "application/json",
            },
            "json": {
                "model": "moonshotai/kimi-k2.6",
                "messages": [{"role": "user", "content": "Return JSON"}],
                "temperature": 0,
            },
            "timeout": 120,
        }
    ]


def test_build_phi_model_configures_gemini(monkeypatch):
    from src.agents.llm_models import build_phi_model

    class FakeGemini:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    model = build_phi_model("gemini-2.5-flash-lite", gemini_cls=FakeGemini)

    assert model.kwargs == {"id": "gemini-2.5-flash-lite", "api_key": "google-key"}
