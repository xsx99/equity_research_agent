from src.agents.prompt_registry import PromptRegistry


def test_prompt_registry_requires_versioned_prompt_metadata(tmp_path):
    prompt_dir = tmp_path / "prompts" / "trading"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "trading_decision_v1.yaml"
    prompt_file.write_text(
        "prompt_id: trading_decision\n"
        "prompt_version: v1\n"
        "pipeline_name: trading\n"
        "output_schema_id: trading_decision\n"
        "output_schema_version: v1\n"
        "template: 'Ticker: {{ ticker }}'\n",
        encoding="utf-8",
    )

    registry = PromptRegistry(root=tmp_path / "prompts")
    template = registry.load("trading_decision", "v1")

    assert template.prompt_id == "trading_decision"
    assert template.prompt_version == "v1"
    assert template.output_schema_version == "v1"
    assert template.template_hash


def test_prompt_registry_renders_and_hashes_prompt(tmp_path):
    prompt_dir = tmp_path / "prompts" / "trading"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "trading_decision_v1.yaml"
    prompt_file.write_text(
        "prompt_id: trading_decision\n"
        "prompt_version: v1\n"
        "pipeline_name: trading\n"
        "output_schema_id: trading_decision\n"
        "output_schema_version: v1\n"
        "template: 'Ticker: {{ ticker }}'\n",
        encoding="utf-8",
    )

    registry = PromptRegistry(root=tmp_path / "prompts")
    rendered = registry.render("trading_decision", "v1", {"ticker": "NVDA"})

    assert rendered.text == "Ticker: NVDA"
    assert rendered.rendered_prompt_hash
