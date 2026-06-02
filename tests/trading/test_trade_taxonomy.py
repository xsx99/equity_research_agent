from src.trading.strategies.taxonomy import TRADE_IDENTITIES, get_trade_identity_policy


def test_trade_identities_include_required_pools():
    assert "core_holding" in TRADE_IDENTITIES
    assert "tactical_stock_trade" in TRADE_IDENTITIES
    assert "tactical_option_trade" in TRADE_IDENTITIES
    assert "risk_hedge_overlay" in TRADE_IDENTITIES
    assert "watch_only" in TRADE_IDENTITIES


def test_core_holding_is_separate_from_short_term_pool():
    policy = get_trade_identity_policy("core_holding")
    assert policy.instrument == "stock"
    assert policy.portfolio_pool == "core"
    assert policy.can_be_sold_by_short_term_signal is False


def test_tactical_option_trade_requires_leg_based_risk():
    policy = get_trade_identity_policy("tactical_option_trade")
    assert policy.instrument == "paper_option_strategy"
    assert policy.requires_option_legs is True
    assert policy.requires_max_loss is True
    assert policy.requires_assignment_plan_when_short_options is True


def test_risk_hedge_overlay_is_risk_manager_owned():
    policy = get_trade_identity_policy("risk_hedge_overlay")
    assert policy.instrument == "paper_option_hedge"
    assert policy.portfolio_pool == "risk_hedge"
    assert policy.generated_by == "risk_manager"
    assert policy.counts_toward_strategy_win_rate is False
