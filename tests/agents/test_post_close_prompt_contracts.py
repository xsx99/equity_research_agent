from src.agents.prompt_registry import PROMPTS_ROOT, PromptRegistry


def test_reflection_prompt_requires_horizon_aware_evidence_labels():
    template = PromptRegistry(root=PROMPTS_ROOT).load("reflection", "v1").template

    assert "single_day_noise" in template
    assert "interim_horizon_mark" in template
    assert "final_horizon_evidence" in template
    assert "Do not infer a durable strategy edge from one trade date" in template


def test_strategy_evolution_prompt_requires_multi_day_supporting_outcomes():
    template = PromptRegistry(root=PROMPTS_ROOT).load("strategy_evolution", "v1").template

    assert "supporting_outcome_ids" in template
    assert "at least 3 final outcome rows" in template
    assert "at least 3 distinct trade dates" in template
    assert "Return an empty proposals array" in template
