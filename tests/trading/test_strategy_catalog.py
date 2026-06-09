from src.trading.strategies.definitions import (
    INITIAL_EXPRESSION_DEFINITIONS,
    INITIAL_STRATEGY_DEFINITIONS,
    get_initial_expression_definitions,
    get_initial_strategy_definitions,
    load_all_trading_definitions,
)


def test_initial_catalog_contains_expected_strategies():
    strategy_ids = {item.strategy_id for item in INITIAL_STRATEGY_DEFINITIONS}
    strategy_layer_ids = {item.strategy_id for item in INITIAL_STRATEGY_DEFINITIONS}
    expression_bucket_ids = {item.strategy_id for item in INITIAL_EXPRESSION_DEFINITIONS}
    assert len(strategy_ids) == 19
    assert len(strategy_layer_ids) == 19
    assert len(expression_bucket_ids) == 5
    assert "catalyst_breakout_v1" in strategy_ids
    assert "gap_and_go_v1" in strategy_ids
    assert "short_squeeze_breakout_v1" in strategy_ids
    assert "strong_theme_catalyst_continuation_v1" in strategy_layer_ids
    assert "strong_theme_no_clear_near_term_entry_v1" in strategy_layer_ids
    assert "valuation_repair_quality_software_v1" in strategy_layer_ids
    assert "core_accumulation_on_pullback_v1" in strategy_layer_ids
    assert "long_stock" in expression_bucket_ids
    assert "defined_risk_directional_option" in expression_bucket_ids
    assert "defined_risk_income_spread" in expression_bucket_ids
    assert "volatility_event_option" in expression_bucket_ids
    assert "core_stock_accumulation" in expression_bucket_ids
    assert "strong_theme_catalyst_long_stock" not in strategy_ids
    assert "strong_theme_no_clear_near_term_sell_put" not in strategy_ids
    assert "valuation_repair_quality_software_sell_put" not in strategy_ids


def test_strategy_definitions_have_required_fields():
    for item in INITIAL_STRATEGY_DEFINITIONS + INITIAL_EXPRESSION_DEFINITIONS:
        assert item.display_name
        if item.strategy_layer == "tactical_pattern":
            assert item.strategy_id.endswith("_v1")
        assert item.typical_horizon
        assert item.core_thesis
        assert item.required_signals
        assert item.risk_tags
        assert item.invalidators
        assert item.strategy_layer in {"tactical_pattern", "expression_bucket"}


def test_seed_rows_are_json_serializable():
    rows = get_initial_strategy_definitions()
    assert rows
    assert all("strategy_id" in row for row in rows)
    assert all(row["version"] == "v1" for row in rows)
    assert all(row["lifecycle_status"] == "active" for row in rows)
    assert all(row["source"] == "seed" for row in rows)
    assert all(isinstance(row["config_json"], dict) for row in rows)


def test_expression_seed_rows_are_json_serializable():
    rows = get_initial_expression_definitions()
    assert rows
    assert all(row["strategy_layer"] == "expression_bucket" for row in rows)
    assert all(isinstance(row["config_json"], dict) for row in rows)


def test_option_expression_seeds_publish_payload_policy_metadata():
    rows = {row["strategy_id"]: row for row in get_initial_expression_definitions()}

    directional_policy = rows["defined_risk_directional_option"]["config_json"]["option_policy"]
    volatility_policy = rows["volatility_event_option"]["config_json"]["option_policy"]

    assert directional_policy["profit_target_pct"] == 0.65
    assert directional_policy["non_event_dte_days"] == 28
    assert directional_policy["long_call_target_delta"] == 0.42
    assert volatility_policy["event_dte_days"] == 7
    assert volatility_policy["close_conditions"] == ["event_exit_after_reaction", "premium_stop"]


def test_combined_definition_loader_preserves_strategy_then_expression_order():
    rows = load_all_trading_definitions()

    assert len(rows) == 24
    assert [row["strategy_layer"] for row in rows[:19]] == ["tactical_pattern"] * 19
    assert [row["strategy_layer"] for row in rows[19:]] == ["expression_bucket"] * 5
