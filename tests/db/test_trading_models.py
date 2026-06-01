from pathlib import Path

from src.db.models.trading import (
    LlmParseStatus,
    LlmPromptLifecycleStatus,
    LlmPromptRun,
    LlmPromptTemplate,
    LlmUsageEvent,
    LlmUsageStatus,
    StrategyDefinition,
    StrategyLifecycleStatus,
    StrategySource,
)


def test_strategy_definition_defaults():
    row = StrategyDefinition(
        strategy_id="gap_and_go_v1",
        version="v1",
        display_name="Gap-and-Go",
        strategy_layer="tactical_pattern",
        typical_horizon="intraday-3d",
        allowed_common_stock_direction="long_only",
        config_json={"required_signals": ["opening_gap_pct"]},
        lifecycle_status="active",
        source="seed",
        is_active=True,
    )
    assert row.strategy_id == "gap_and_go_v1"
    assert row.lifecycle_status == "active"
    assert row.allowed_common_stock_direction == "long_only"
    assert row.source == "seed"
    assert row.is_active is True


def test_new_status_enums_expose_choices():
    assert StrategyLifecycleStatus.choices() == (
        "candidate",
        "shadow",
        "experimental",
        "active",
        "retired",
    )
    assert StrategySource.choices() == ("seed", "reflection_learning", "manual")
    assert LlmPromptLifecycleStatus.choices() == ("active", "retired")
    assert LlmParseStatus.choices() == ("succeeded", "failed")
    assert LlmUsageStatus.choices() == ("succeeded", "failed")


def test_llm_models_can_be_instantiated():
    template = LlmPromptTemplate(
        prompt_id="trading_decision",
        prompt_version="v1",
        pipeline_name="trading",
        template_path="src/agents/prompts/trading/trading_decision_v1.yaml",
        template_hash="abc123",
        output_schema_id="trading_decision",
        output_schema_version="v1",
        lifecycle_status="active",
    )
    run = LlmPromptRun(
        prompt_template=template,
        pipeline_name="trading",
        rendered_prompt_hash="rendered123",
        input_context_json={"ticker": "NVDA"},
        raw_output_text="{}",
        parsed_output_json={},
        parse_status="succeeded",
        validation_errors_json=[],
        error_message=None,
    )
    usage = LlmUsageEvent(
        prompt_run=run,
        provider="google",
        model="gemini-2.5-flash",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost=0.01,
        latency_ms=1200,
        retry_count=0,
        status="succeeded",
    )

    assert template.prompt_id == "trading_decision"
    assert run.prompt_template is template
    assert usage.prompt_run is run


def test_trading_migration_contains_pr_1a_tables():
    migration_path = Path("alembic/versions/005_trading_minimal_foundation_tables.py")
    text = migration_path.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "004"' in text
    assert '"strategy_definitions"' in text
    assert '"llm_prompt_templates"' in text
    assert '"llm_prompt_runs"' in text
    assert '"llm_usage_events"' in text
