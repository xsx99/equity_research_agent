from src.agents.strategy_evolution import _default_agent_runner


def test_default_strategy_evolution_agent_runner_delegates_to_trading_runner(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_runner(prompt: str, model_name: str):
        calls.append((prompt, model_name))
        return {"content": '{"ok": true}'}

    monkeypatch.setattr(
        "src.agents.strategy_evolution._trading_default_agent_runner",
        fake_runner,
        raising=False,
    )

    response = _default_agent_runner("strategy evolution prompt", "gpt-5-mini")

    assert response == {"content": '{"ok": true}'}
    assert calls == [("strategy evolution prompt", "gpt-5-mini")]
