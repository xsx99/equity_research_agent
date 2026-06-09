"""Initial versioned strategy catalog for the V2 trading workflow."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StrategyCatalogItem:
    """In-code seed definition for one strategy or expression bucket."""

    strategy_id: str
    display_name: str
    strategy_layer: str
    typical_horizon: str
    core_thesis: str
    required_signals: tuple[str, ...]
    risk_tags: tuple[str, ...]
    invalidators: tuple[str, ...]
    optional_signals: tuple[str, ...] = ()
    scoring_rules: dict[str, Any] = field(default_factory=dict)
    selection_policy: dict[str, Any] = field(default_factory=dict)
    macro_blocked_regimes: tuple[str, ...] = ()
    allowed_trade_identities: tuple[str, ...] = ()
    allowed_instruments: tuple[str, ...] = ()
    allowed_option_strategy_types: tuple[str, ...] = ()
    required_option_leg_fields: tuple[str, ...] = ()
    required_assignment_fields: tuple[str, ...] = ()
    option_policy: dict[str, Any] = field(default_factory=dict)
    default_trade_identity: str | None = None
    default_exit_policy: str | None = None
    earnings_policy: str | None = None

    @property
    def version(self) -> str:
        """All initial catalog rows are v1 seeds."""
        return "v1"

    def config_json(self) -> dict[str, Any]:
        """Return JSON-serializable strategy config fields."""
        return {
            "strategy_id": self.strategy_id,
            "display_name": self.display_name,
            "strategy_layer": self.strategy_layer,
            "typical_horizon": self.typical_horizon,
            "core_thesis": self.core_thesis,
            "required_signals": list(self.required_signals),
            "optional_signals": list(self.optional_signals),
            "scoring_rules": self.scoring_rules,
            "selection_policy": dict(self.selection_policy or _default_selection_policy(self)),
            "risk_tags": list(self.risk_tags),
            "macro_blocked_regimes": list(self.macro_blocked_regimes),
            "invalidators": list(self.invalidators),
            "default_trade_identity": self.default_trade_identity,
            "allowed_trade_identities": list(self.allowed_trade_identities),
            "allowed_instruments": list(self.allowed_instruments),
            "allowed_option_strategy_types": list(self.allowed_option_strategy_types),
            "required_option_leg_fields": list(self.required_option_leg_fields),
            "required_assignment_fields": list(self.required_assignment_fields),
            "option_policy": self.option_policy,
            "earnings_policy": self.earnings_policy,
            "default_exit_policy": self.default_exit_policy,
        }


OPTION_LEG_FIELDS = (
    "option_type",
    "side",
    "quantity",
    "strike",
    "expiry",
    "dte",
    "delta",
    "gamma",
    "theta",
    "vega",
    "iv_rank_or_percentile",
    "bid",
    "ask",
    "mid",
    "chosen_price",
)

ASSIGNMENT_FIELDS = (
    "assignment_notional",
    "underlying_exposure",
    "assignment_plan",
)


def _default_selection_policy(item: StrategyCatalogItem) -> dict[str, Any]:
    if item.strategy_layer != "tactical_pattern":
        return {}
    policy: dict[str, Any] = {
        "actionable_score_threshold": 0.55,
        "default_candidate_action": "enter_long",
        "default_candidate_direction": "bullish",
        "eligible_expression_bucket_ids": ["long_stock"],
    }
    if item.strategy_id == "strong_theme_catalyst_continuation_v1":
        policy["eligible_expression_bucket_ids"] = ["long_stock", "defined_risk_directional_option"]
    elif item.strategy_id == "strong_theme_no_clear_near_term_entry_v1":
        policy.update(
            {
                "default_candidate_action": "no_trade",
                "default_candidate_direction": "neutral",
                "eligible_expression_bucket_ids": [
                    "defined_risk_income_spread",
                    "volatility_event_option",
                ],
            }
        )
    elif item.strategy_id == "core_accumulation_on_pullback_v1":
        policy["eligible_expression_bucket_ids"] = ["core_stock_accumulation"]
    return policy


INITIAL_STRATEGY_CATALOG: tuple[StrategyCatalogItem, ...] = (
    StrategyCatalogItem(
        strategy_id="catalyst_breakout_v1",
        display_name="Catalyst Breakout",
        strategy_layer="tactical_pattern",
        typical_horizon="2d-4w",
        core_thesis="New information reprices the stock.",
        required_signals=(
            "fresh_high_signal_catalyst",
            "post_catalyst_volume_expansion",
            "key_level_break",
            "close_above_prior_resistance",
            "news_or_filing_timestamp_freshness",
        ),
        optional_signals=("relative_strength_vs_peer_basket", "analyst_revision_cluster"),
        scoring_rules={"min_relative_volume": 1.5, "requires_price_confirmation": True},
        risk_tags=("catalyst_risk", "breakout_risk"),
        macro_blocked_regimes=("stressed",),
        invalidators=("breaks reclaimed resistance", "catalyst is contradicted", "volume fades"),
    ),
    StrategyCatalogItem(
        strategy_id="gap_and_go_v1",
        display_name="Gap-and-Go",
        strategy_layer="tactical_pattern",
        typical_horizon="intraday-3d",
        core_thesis="Overnight information continues as momentum.",
        required_signals=(
            "opening_gap_pct",
            "vwap_hold",
            "opening_range_high_break",
            "relative_volume",
            "no_immediate_gap_fade",
        ),
        optional_signals=("fresh_catalyst_type", "sector_rank_percentile"),
        scoring_rules={"min_opening_gap_pct": 0.02, "min_relative_volume": 1.5},
        risk_tags=("gap_risk", "intraday_momentum"),
        macro_blocked_regimes=("stressed",),
        invalidators=("loses VWAP", "fails opening range high", "relative volume fades"),
    ),
    StrategyCatalogItem(
        strategy_id="gap_fade_fill_v1",
        display_name="Gap Fade / Gap Fill",
        strategy_layer="tactical_pattern",
        typical_horizon="intraday-2d",
        core_thesis="Opening reaction overextended.",
        required_signals=(
            "large_opening_gap",
            "vwap_failure",
            "opening_range_breakdown",
            "weak_relative_volume_after_initial_spike",
            "gap_fill_distance",
        ),
        scoring_rules={"min_opening_gap_pct": 0.04, "requires_vwap_failure": True},
        risk_tags=("gap_risk", "mean_reversion"),
        invalidators=("reclaims VWAP", "holds opening range high", "new catalyst confirms gap"),
    ),
    StrategyCatalogItem(
        strategy_id="volatility_compression_breakout_v1",
        display_name="Volatility Compression Breakout",
        strategy_layer="tactical_pattern",
        typical_horizon="1-6w",
        core_thesis="Compressed volatility releases into trend.",
        required_signals=(
            "multi_day_narrow_range",
            "falling_realized_volatility",
            "bollinger_or_keltner_squeeze",
            "breakout_volume_expansion",
            "range_high_break",
        ),
        scoring_rules={"min_compression_days": 5, "min_breakout_relative_volume": 1.3},
        risk_tags=("breakout_risk", "volatility_expansion"),
        invalidators=("breakout fails back into range", "volume expansion reverses", "market breadth deteriorates"),
    ),
    StrategyCatalogItem(
        strategy_id="base_breakout_v1",
        display_name="Base Breakout",
        strategy_layer="tactical_pattern",
        typical_horizon="2-8w",
        core_thesis="Second-stage trend begins after consolidation.",
        required_signals=(
            "constructive_base_duration",
            "resistance_breakout_or_new_high",
            "volume_confirmation",
            "relative_strength_vs_sector_or_spy",
        ),
        optional_signals=("institutional_accumulation_proxy",),
        scoring_rules={"min_base_days": 15, "min_relative_volume": 1.2},
        risk_tags=("breakout_risk", "trend_following"),
        invalidators=("falls back below base breakout", "relative strength breaks", "volume confirms reversal"),
    ),
    StrategyCatalogItem(
        strategy_id="trend_pullback_v1",
        display_name="Trend Pullback",
        strategy_layer="tactical_pattern",
        typical_horizon="1-8w",
        core_thesis="Trend continues after internal digestion.",
        required_signals=(
            "established_uptrend",
            "pullback_to_support_or_sma_or_vwap",
            "lower_selling_volume",
            "rsi_reset_without_trend_break",
            "bounce_confirmation",
        ),
        scoring_rules={"max_pullback_pct_from_recent_high": 0.12, "requires_trend_intact": True},
        risk_tags=("trend_following", "pullback_entry"),
        invalidators=("support breaks", "trend structure fails", "bounce confirmation reverses"),
    ),
    StrategyCatalogItem(
        strategy_id="post_catalyst_pullback_v1",
        display_name="Post-Catalyst Pullback",
        strategy_layer="tactical_pattern",
        typical_horizon="1-6w",
        core_thesis="Better second entry after catalyst repricing.",
        required_signals=(
            "prior_positive_catalyst",
            "controlled_pullback_into_gap_or_support",
            "gap_not_fully_broken",
            "volume_dries_on_pullback",
            "reclaim_trigger",
        ),
        scoring_rules={"max_gap_fill_pct": 0.6, "requires_reclaim_trigger": True},
        risk_tags=("catalyst_risk", "pullback_entry"),
        invalidators=("fills and loses catalyst gap", "reclaim fails", "source catalyst weakens"),
    ),
    StrategyCatalogItem(
        strategy_id="earnings_drift_v1",
        display_name="Earnings Drift",
        strategy_layer="tactical_pattern",
        typical_horizon="2w-3m",
        core_thesis="Post-earnings expectations continue to drift upward.",
        required_signals=(
            "earnings_beat_and_raise",
            "positive_guidance",
            "post_earnings_gap_not_filled",
            "analyst_revisions",
            "stable_or_improving_margin_narrative",
        ),
        scoring_rules={"requires_direct_company_earnings": True, "min_revision_count": 1},
        risk_tags=("earnings_event", "expectation_revision"),
        invalidators=("gap fully fails", "guidance is walked back", "analyst revisions reverse"),
    ),
    StrategyCatalogItem(
        strategy_id="analyst_revision_momentum_v1",
        display_name="Analyst Revision Momentum",
        strategy_layer="tactical_pattern",
        typical_horizon="1-3m",
        core_thesis="Valuation model is being revised upward.",
        required_signals=(
            "eps_or_target_price_estimate_increase",
            "multiple_analyst_upgrades_or_revisions",
            "post_earnings_revision_cluster",
            "price_confirmation",
        ),
        scoring_rules={"min_revision_count": 2, "requires_price_confirmation": True},
        risk_tags=("revision_momentum", "valuation_repricing"),
        invalidators=("revision cluster stalls", "price rejects revision news", "fundamental narrative weakens"),
    ),
    StrategyCatalogItem(
        strategy_id="sympathy_trade_v1",
        display_name="Sympathy Trade",
        strategy_layer="tactical_pattern",
        typical_horizon="2d-4w",
        core_thesis="Logic propagates from stock A to stock B.",
        required_signals=(
            "peer_or_industry_leader_catalyst",
            "structured_relationship_linkage",
            "lagging_related_stock",
            "sector_breadth_confirmation",
            "no_direct_negative_news",
        ),
        optional_signals=("target_relative_strength_confirmation",),
        scoring_rules={"requires_structured_relationship": True, "requires_target_confirmation": True},
        risk_tags=("readthrough_risk", "sympathy_trade"),
        invalidators=("target fails to confirm", "source catalyst is not transferable", "direct target negative news appears"),
    ),
    StrategyCatalogItem(
        strategy_id="relative_strength_rotation_v1",
        display_name="Relative Strength Rotation",
        strategy_layer="tactical_pattern",
        typical_horizon="2w-3m",
        core_thesis="Capital rotates into the stronger asset or group.",
        required_signals=(
            "outperforming_benchmark",
            "improving_relative_strength_rank",
            "institutional_rotation_proxy",
            "liquidity_confirmation",
        ),
        scoring_rules={"min_relative_strength_percentile": 0.75, "requires_liquidity_confirmation": True},
        risk_tags=("rotation", "relative_strength"),
        invalidators=("relative strength rank rolls over", "rotation breadth fails", "liquidity dries up"),
    ),
    StrategyCatalogItem(
        strategy_id="pre_catalyst_runup_v1",
        display_name="Pre-Catalyst Run-up",
        strategy_layer="tactical_pattern",
        typical_horizon="3d-4w",
        core_thesis="Traders position before the event.",
        required_signals=(
            "known_upcoming_event",
            "rising_volume_before_event",
            "positive_estimate_or_news_drift",
            "price_strength_into_event",
        ),
        optional_signals=("options_or_volatility_expansion",),
        scoring_rules={"max_days_to_event": 20, "requires_event_date": True},
        risk_tags=("event_risk", "pre_event_positioning"),
        invalidators=("event setup deteriorates", "price strength breaks", "event risk exceeds plan"),
    ),
    StrategyCatalogItem(
        strategy_id="failed_breakdown_reclaim_v1",
        display_name="Failed Breakdown / Reclaim",
        strategy_layer="tactical_pattern",
        typical_horizon="2d-3w",
        core_thesis="Failed breakdown creates reversal squeeze.",
        required_signals=(
            "break_below_support",
            "quick_reclaim_above_support_or_vwap",
            "short_term_reversal_volume",
            "trapped_shorts_signal",
            "close_back_inside_range",
        ),
        scoring_rules={"max_days_below_support": 3, "requires_close_back_inside_range": True},
        risk_tags=("reversal", "failed_breakdown"),
        invalidators=("re-loses reclaimed support", "reversal volume disappears", "new lows confirm breakdown"),
    ),
    StrategyCatalogItem(
        strategy_id="oversold_bounce_v1",
        display_name="Oversold Bounce",
        strategy_layer="tactical_pattern",
        typical_horizon="1d-2w",
        core_thesis="Short-term oversold move mean reverts.",
        required_signals=(
            "extreme_short_term_oversold",
            "capitulation_volume",
            "stabilization_or_reclaim_trigger",
            "no_unresolved_major_negative_catalyst",
        ),
        scoring_rules={"max_rsi_3": 20, "requires_reclaim_trigger": True},
        risk_tags=("mean_reversion", "falling_knife_risk"),
        invalidators=("no stabilization", "negative catalyst worsens", "capitulation continues"),
    ),
    StrategyCatalogItem(
        strategy_id="short_squeeze_breakout_v1",
        display_name="Short Squeeze Breakout",
        strategy_layer="tactical_pattern",
        typical_horizon="1d-2w",
        core_thesis="Crowded short positioning is forced to cover.",
        required_signals=(
            "high_short_interest",
            "positive_catalyst",
            "volume_surge",
            "breakout_through_resistance",
            "days_to_cover_or_liquidity_risk",
        ),
        optional_signals=("rising_borrow_fee",),
        scoring_rules={"min_short_interest_pct_float": 0.1, "requires_breakout": True},
        risk_tags=("short_squeeze", "high_volatility"),
        invalidators=("breakout fails", "borrow pressure eases", "catalyst is rejected"),
    ),
    StrategyCatalogItem(
        strategy_id="strong_theme_catalyst_continuation_v1",
        display_name="Strong Theme Catalyst Continuation",
        strategy_layer="tactical_pattern",
        typical_horizon="intraday-3m",
        core_thesis="Best candidates are theme leaders with fresh catalysts and confirmed near-term continuation.",
        required_signals=(
            "clear_bullish_catalyst",
            "theme_alignment",
            "relative_strength_vs_benchmark_or_peers",
            "volume_price_confirmation",
        ),
        scoring_rules={"requires_theme_mapping": True, "requires_relative_strength_confirmation": True},
        risk_tags=("theme_momentum", "catalyst_risk"),
        invalidators=("theme leadership fades", "price confirmation fails", "catalyst is contradicted"),
    ),
    StrategyCatalogItem(
        strategy_id="strong_theme_no_clear_near_term_entry_v1",
        display_name="Strong Theme No Clear Near-Term Entry",
        strategy_layer="tactical_pattern",
        typical_horizon="2-8w",
        core_thesis="The underlying is interesting, but the common-stock entry is not clean enough yet.",
        required_signals=(
            "strong_theme",
            "acceptable_underlying_quality_or_liquidity",
            "relative_strength_still_intact",
            "no_clean_common_stock_trigger",
        ),
        scoring_rules={"requires_expression_bucket_review": True, "stock_entry_must_be_unclean": True},
        risk_tags=("theme_momentum", "entry_timing_risk"),
        invalidators=("theme breaks", "liquidity deteriorates", "underlying quality weakens"),
    ),
    StrategyCatalogItem(
        strategy_id="valuation_repair_quality_software_v1",
        display_name="Valuation Repair Quality Software",
        strategy_layer="tactical_pattern",
        typical_horizon="2-12w",
        core_thesis="Valuation repair can create positive drift, but timing and entry quality determine the expression.",
        required_signals=(
            "quality_software_name",
            "improving_valuation_margin_or_growth_narrative",
            "stabilizing_estimates",
            "relative_strength_improving_from_depressed_base",
        ),
        scoring_rules={"requires_quality_software_context": True, "requires_estimate_stabilization": True},
        risk_tags=("valuation_repair", "software_multiple_risk"),
        invalidators=("estimate stabilization fails", "valuation repair reverses", "relative strength deteriorates"),
    ),
    StrategyCatalogItem(
        strategy_id="core_accumulation_on_pullback_v1",
        display_name="Core Accumulation On Pullback",
        strategy_layer="tactical_pattern",
        typical_horizon="multi-month+",
        core_thesis="Add to core only when the pullback improves risk/reward and portfolio concentration allows it.",
        required_signals=(
            "approved_core_holding",
            "thesis_intact",
            "pullback_into_defined_support_or_risk_budget_availability",
        ),
        scoring_rules={"requires_active_portfolio_intent": True, "requires_core_budget_availability": True},
        risk_tags=("core_accumulation", "concentration_risk"),
        invalidators=("core thesis invalidated", "support breaks materially", "concentration cap blocks add"),
    ),
    StrategyCatalogItem(
        strategy_id="long_stock",
        display_name="Long Stock",
        strategy_layer="expression_bucket",
        typical_horizon="intraday-3m",
        core_thesis="Own the common stock when direct directional exposure is the cleanest expression.",
        required_signals=("near_term_continuation_confirmed", "acceptable_stock_entry_risk_reward", "liquidity_confirmation"),
        risk_tags=("stock_directional_exposure",),
        invalidators=("stock entry trigger fails", "risk_reward_deteriorates", "liquidity_check_fails"),
        default_trade_identity="tactical_stock_trade",
        allowed_trade_identities=("tactical_stock_trade",),
        allowed_instruments=("common_stock",),
        default_exit_policy="strategy_invalidators_or_target_horizon",
    ),
    StrategyCatalogItem(
        strategy_id="defined_risk_directional_option",
        display_name="Directional Long Option",
        strategy_layer="expression_bucket",
        typical_horizon="intraday-4w",
        core_thesis="Express directional views through long calls or long puts only.",
        required_signals=("directional_catalyst_or_setup", "option_convexity_preferable", "premium_defined_max_loss"),
        risk_tags=("option_premium_risk", "convexity"),
        invalidators=("directional_setup_invalidated", "option_liquidity_missing", "event_risk_exceeds_plan"),
        default_trade_identity="tactical_option_trade",
        allowed_trade_identities=("tactical_option_trade",),
        allowed_instruments=("paper_option_strategy",),
        allowed_option_strategy_types=("long_call", "long_put"),
        required_option_leg_fields=OPTION_LEG_FIELDS,
        option_policy={
            "requires_max_loss": True,
            "max_loss_source": "premium_paid",
            "no_short_option_legs": True,
            "profit_target_pct": 0.65,
            "non_event_dte_days": 28,
            "long_call_strike_pct_above_spot": 0.02,
            "long_put_strike_pct_below_spot": 0.02,
            "long_call_target_delta": 0.42,
            "long_put_target_delta": -0.42,
            "close_conditions": ["take_profit_65pct", "time_stop_10d"],
        },
        earnings_policy="avoid_unpriced_high_risk_events",
        default_exit_policy="profit_target_loss_limit_event_or_expiry_rules",
    ),
    StrategyCatalogItem(
        strategy_id="defined_risk_income_spread",
        display_name="Credit Spread",
        strategy_layer="expression_bucket",
        typical_horizon="2-8w",
        core_thesis="Express short-premium views only through put credit spreads or call credit spreads with explicit max loss.",
        required_signals=("attractive_premium", "clear_direction_or_range_thesis", "capped_risk_short_premium_preferred"),
        risk_tags=("defined_risk_short_premium", "assignment_risk"),
        invalidators=("spread_thesis_invalidated", "max_loss_missing", "assignment_plan_missing"),
        default_trade_identity="tactical_option_trade",
        allowed_trade_identities=("tactical_option_trade",),
        allowed_instruments=("paper_option_strategy",),
        allowed_option_strategy_types=("put_credit_spread", "call_credit_spread"),
        required_option_leg_fields=OPTION_LEG_FIELDS,
        required_assignment_fields=ASSIGNMENT_FIELDS,
        option_policy={
            "requires_max_loss": True,
            "requires_margin_requirement": True,
            "requires_assignment_plan_when_short_options": True,
            "profit_target_pct": 0.5,
            "non_event_dte_days": 28,
            "short_put_strike_pct_below_spot": 0.03,
            "long_put_strike_pct_below_spot": 0.08,
            "short_call_strike_pct_above_spot": 0.03,
            "long_call_strike_pct_above_spot": 0.08,
            "short_leg_target_delta_abs": 0.28,
            "long_leg_target_delta_abs": 0.12,
            "close_conditions": ["take_profit_50pct"],
            "roll_conditions": ["7_dte_if_otm"],
            "assignment_plan": "close_or_roll_before_expiry_if_itm",
            "strategy_pairing_method": "vertical_by_expiry_and_width",
        },
        earnings_policy="avoid_holding_through_unapproved_binary_events",
        default_exit_policy="profit_target_loss_limit_assignment_or_expiry_rules",
    ),
    StrategyCatalogItem(
        strategy_id="volatility_event_option",
        display_name="Volatility Event Option",
        strategy_layer="expression_bucket",
        typical_horizon="intraday-4w",
        core_thesis="Express event volatility through long straddles or long strangles only.",
        required_signals=("uncertain_direction", "material_event_volatility", "acceptable_long_vol_premium_risk"),
        risk_tags=("long_volatility", "event_risk"),
        invalidators=("event_volatility_no_longer_attractive", "option_liquidity_missing", "premium_risk_exceeds_budget"),
        default_trade_identity="tactical_option_trade",
        allowed_trade_identities=("tactical_option_trade",),
        allowed_instruments=("paper_option_strategy",),
        allowed_option_strategy_types=("long_straddle", "long_strangle"),
        required_option_leg_fields=OPTION_LEG_FIELDS,
        option_policy={
            "requires_max_loss": True,
            "max_loss_source": "net_debit",
            "no_short_option_legs": True,
            "profit_target_pct": 0.35,
            "event_dte_days": 7,
            "straddle_target_delta_abs": 0.24,
            "strangle_call_strike_pct_above_spot_bullish": 0.04,
            "strangle_call_strike_pct_above_spot_default": 0.03,
            "strangle_put_strike_pct_below_spot_bearish": 0.04,
            "strangle_put_strike_pct_below_spot_default": 0.03,
            "strangle_call_target_delta": 0.26,
            "strangle_put_target_delta": -0.14,
            "close_conditions": ["event_exit_after_reaction", "premium_stop"],
            "roll_conditions": ["event_window_only"],
            "strategy_pairing_method": "same_expiry_long_vol",
        },
        earnings_policy="event_through_expiry_must_be_explicit",
        default_exit_policy="event_exit_or_premium_loss_limit",
    ),
    StrategyCatalogItem(
        strategy_id="core_stock_accumulation",
        display_name="Core Stock Accumulation",
        strategy_layer="expression_bucket",
        typical_horizon="multi-month+",
        core_thesis="Add to a core position through stock only when the core-pool rules approve it.",
        required_signals=("approved_core_holding", "portfolio_risk_budget_available", "core_add_rule_triggered"),
        risk_tags=("core_accumulation", "concentration_risk"),
        invalidators=("portfolio_intent_missing", "core_add_rule_not_satisfied", "concentration_cap_blocks_add"),
        default_trade_identity="core_holding",
        allowed_trade_identities=("core_holding",),
        allowed_instruments=("common_stock",),
        default_exit_policy="core_intent_add_trim_and_thesis_invalidator_rules",
    ),
)


def get_initial_strategy_definitions() -> list[dict[str, object]]:
    """Return seed rows ready for StrategyDefinition insertion."""
    return [
        {
            "strategy_id": item.strategy_id,
            "version": item.version,
            "display_name": item.display_name,
            "strategy_layer": item.strategy_layer,
            "typical_horizon": item.typical_horizon,
            "allowed_common_stock_direction": "long_only",
            "config_json": item.config_json(),
            "lifecycle_status": "active",
            "source": "seed",
            "parent_strategy_id": None,
            "evidence_json": {},
            "is_active": True,
        }
        for item in INITIAL_STRATEGY_CATALOG
    ]
