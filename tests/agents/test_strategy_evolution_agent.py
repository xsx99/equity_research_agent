from src.agents.strategy_evolution import _default_agent_runner
from src.agents.strategy_evolution_schemas import StrategyEvolutionOutput


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


def test_strategy_evolution_output_accepts_supporting_outcome_ids():
    output = StrategyEvolutionOutput.model_validate(
        {
            "proposals": [
                {
                    "proposed_strategy_id": "post_gap_vwap_reclaim_v1",
                    "display_name": "Post-Gap VWAP Reclaim",
                    "source_reflection_ids": ["reflection-1"],
                    "supporting_outcome_ids": ["outcome-1", "outcome-2", "outcome-3"],
                    "core_thesis": "Gap fades that reclaim VWAP can continue.",
                    "typical_horizon": "intraday-3d",
                    "required_signals": ["opening_gap_pct", "vwap_reclaim", "relative_volume"],
                    "optional_signals": [],
                    "scoring_rules": {},
                    "risk_tags": ["gap_risk"],
                    "macro_blocked_regimes": [],
                    "invalidators": ["loses VWAP"],
                    "evidence_summary": "Three final rows across three dates beat QQQ.",
                }
            ],
            "schema_version": "v1",
            "generated_at": "2026-06-02T22:00:00+00:00",
        }
    )

    assert output.proposals[0].supporting_outcome_ids == ["outcome-1", "outcome-2", "outcome-3"]
