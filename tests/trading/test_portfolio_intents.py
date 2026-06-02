from src.trading.portfolio.intents import (
    PortfolioIntentConfig,
    allowed_tactical_interactions_for_ticker,
    is_core_holding_approved,
    max_weight_for_ticker,
    tactical_interaction_allowed,
)


def test_core_holding_requires_active_approved_intent():
    intent = PortfolioIntentConfig(
        ticker="GOOGL",
        intent_type="core_growth",
        target_weight=0.08,
        max_weight=0.12,
        lifecycle_status="active",
        add_rules=["add_on_pullback"],
        trim_rules=["trim_above_max_weight"],
        thesis_invalidators=["cloud_growth_breaks_down"],
        allowed_tactical_interactions=["pause_adds", "trim_for_risk"],
    )

    assert is_core_holding_approved("GOOGL", [intent]) is True
    assert is_core_holding_approved("NVDA", [intent]) is False


def test_inactive_intent_does_not_approve_core_holding():
    paused_intent = PortfolioIntentConfig(
        ticker="GOOGL",
        intent_type="core_growth",
        target_weight=0.08,
        max_weight=0.12,
        lifecycle_status="paused",
        add_rules=["add_on_pullback"],
        trim_rules=["trim_above_max_weight"],
        thesis_invalidators=["cloud_growth_breaks_down"],
        allowed_tactical_interactions=["pause_adds"],
    )

    assert is_core_holding_approved("GOOGL", [paused_intent]) is False


def test_weight_and_tactical_interaction_helpers_use_active_intents():
    intent = PortfolioIntentConfig(
        ticker="googl",
        intent_type="core_growth",
        target_weight=0.08,
        max_weight=0.12,
        lifecycle_status="active",
        add_rules=["add_on_pullback"],
        trim_rules=["trim_above_max_weight"],
        thesis_invalidators=["cloud_growth_breaks_down"],
        allowed_tactical_interactions=["pause_adds", "trim_for_risk"],
    )

    assert max_weight_for_ticker("GOOGL", [intent]) == 0.12
    assert allowed_tactical_interactions_for_ticker("GOOGL", [intent]) == (
        "pause_adds",
        "trim_for_risk",
    )
    assert tactical_interaction_allowed("GOOGL", [intent], "trim_for_risk") is True
    assert tactical_interaction_allowed("GOOGL", [intent], "open_new_tactical") is False
    assert max_weight_for_ticker("NVDA", [intent]) is None
