from datetime import date, datetime, timezone
from pathlib import Path

from src.db.models.trading import (
    LlmParseStatus,
    LlmPromptLifecycleStatus,
    LlmPromptRun,
    LlmPromptTemplate,
    LlmUsageEvent,
    LlmUsageStatus,
    PeerBasket,
    PortfolioIntent,
    PortfolioIntentLifecycleStatus,
    PortfolioIntentType,
    StrategyDefinition,
    StrategyLifecycleStatus,
    StrategySource,
    ThemeLifecycleStatus,
    ThemeTaxonomy,
    TickerRelationship,
    TickerRelationshipType,
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
    assert PortfolioIntentLifecycleStatus.choices() == ("active", "paused", "retired")
    assert PortfolioIntentType.choices() == (
        "core_growth",
        "core_index",
        "core_theme",
        "core_cash_like",
    )
    assert TickerRelationshipType.choices() == (
        "peer",
        "customer",
        "supplier",
        "competitor",
        "sector_leader",
        "etf_component",
        "theme_leader",
        "theme_constituent",
    )
    assert ThemeLifecycleStatus.choices() == ("active", "retired")


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


def test_pr_1b_models_can_be_instantiated():
    intent = PortfolioIntent(
        ticker="GOOGL",
        intent_type="core_growth",
        target_weight=0.08,
        max_weight=0.12,
        add_rules_json=["add_on_pullback"],
        trim_rules_json=["trim_above_max_weight"],
        thesis_invalidators_json=["cloud_growth_breaks_down"],
        allowed_tactical_interactions_json=["pause_adds", "trim_for_risk"],
        lifecycle_status="active",
    )
    relationship = TickerRelationship(
        source_ticker="NVDA",
        target_ticker="MU",
        relationship_type="theme_leader",
        theme_id="ai_infra",
        confidence=0.8,
        strength_score=0.7,
        valid_from=datetime(2026, 6, 1, tzinfo=timezone.utc),
        valid_until=None,
        source_refs_json=[{"source": "manual_theme_map_v1"}],
        allowed_uses_json=["readthrough", "peer_basket"],
    )
    basket = PeerBasket(
        basket_key="nvda_ai_infra",
        version="v1",
        trade_date=date(2026, 6, 1),
        members_json=["LITE", "MU"],
        construction_method="relationship_graph_v1",
        source_refs_json=["manual_theme_map_v1"],
    )
    theme = ThemeTaxonomy(
        theme_id="ai_infra",
        display_name="AI Infrastructure",
        parent_theme_id=None,
        description="Compute and networking beneficiaries.",
        lifecycle_status="active",
    )

    assert intent.ticker == "GOOGL"
    assert relationship.target_ticker == "MU"
    assert basket.members_json == ["LITE", "MU"]
    assert theme.lifecycle_status == "active"


def test_trading_migration_contains_pr_1a_tables():
    migration_path = Path("alembic/versions/005_trading_minimal_foundation_tables.py")
    text = migration_path.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "004"' in text
    assert '"strategy_definitions"' in text
    assert '"llm_prompt_templates"' in text
    assert '"llm_prompt_runs"' in text
    assert '"llm_usage_events"' in text


def test_trading_migration_contains_pr_1b_tables_and_constraints():
    migration_path = Path("alembic/versions/006_portfolio_intents_relationship_graph.py")
    text = migration_path.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "005"' in text
    assert '"portfolio_intents"' in text
    assert '"ticker_relationships"' in text
    assert '"peer_baskets"' in text
    assert '"theme_taxonomy"' in text
    assert "ck_portfolio_intents_lifecycle_status" in text
    assert "ck_ticker_relationships_relationship_type" in text
    assert "ck_ticker_relationships_confidence" in text
    assert "ck_ticker_relationships_strength_score" in text
    assert "ck_theme_taxonomy_lifecycle_status" in text
