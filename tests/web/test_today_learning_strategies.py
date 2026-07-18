from __future__ import annotations

import json
from decimal import Decimal

from src.web.presenters.today_learning_strategies import build_today_learning_strategies, _proposal_status_rank


def test_build_today_learning_strategies_exposes_funnel_and_weight_inputs():
    payload = build_today_learning_strategies(
        reflection={"status": "succeeded", "status_label": "Succeeded"},
        learning_factors=(
            {
                "factor_key": "lf-active-score",
                "title": "Raise conviction on reclaim setups",
                "status": "active",
                "status_label": "Active",
                "scope": "strategy",
                "scope_label": "Strategy",
                "effect_tags": ("increase_score",),
            },
            {
                "factor_key": "lf-active-risk",
                "title": "Trim risk when event clusters stack",
                "status": "active",
                "status_label": "Active",
                "scope": "risk",
                "scope_label": "Risk",
                "effect_tags": ("reduce_exposure",),
            },
            {
                "factor_key": "lf-shadow",
                "title": "Observe looser sizing",
                "status": "shadow",
                "status_label": "Shadow",
                "scope": "portfolio",
                "scope_label": "Portfolio",
                "effect_tags": ("increase_risk_budget",),
            },
        ),
        strategy_performance=(
            {"strategy_id": "earnings_drift_v1", "lifecycle_status": "active", "lifecycle_status_label": "Active"},
        ),
        strategy_proposals=(
            {"proposed_strategy_id": "semis_readthrough_v1", "proposal_status": "accepted", "proposal_status_label": "Accepted"},
            {"proposed_strategy_id": "gap_reclaim_v1", "proposal_status": "duplicate_rejected", "proposal_status_label": "Duplicate Rejected"},
        ),
        strategy_definitions=(
            {"strategy_id": "semis_readthrough_v1", "lifecycle_status": "shadow", "lifecycle_status_label": "Shadow"},
            {"strategy_id": "hedge_overlay_v1", "lifecycle_status": "experimental", "lifecycle_status_label": "Experimental"},
        ),
        strategy_evaluation_results=(
            {"evaluation_status": "promoted", "new_lifecycle_status": "shadow"},
            {"evaluation_status": "promoted", "new_lifecycle_status": "experimental"},
            {"evaluation_status": "observed", "new_lifecycle_status": None},
        ),
    )

    observability = payload["observability"]
    assert observability["funnel"][0] == {"label": "Learning Factors Created", "count": 3}
    assert observability["funnel"][1] == {"label": "Applied Today", "count": 3}
    assert observability["funnel"][2] == {"label": "Strategy Proposals", "count": 2}
    assert observability["funnel"][3] == {"label": "New Strategy Definitions", "count": 2}
    assert observability["funnel"][4] == {"label": "Promoted", "count": 2}
    assert observability["promotion_breakdown"] == (
        {"label": "Shadow", "count": 1},
        {"label": "Experimental", "count": 1},
        {"label": "Active", "count": 0},
    )
    assert observability["weight_inputs"] == (
        {
            "factor_key": "lf-active-risk",
            "title": "Trim risk when event clusters stack",
            "scope_label": "Risk",
            "effect_summary": "reduce exposure",
        },
        {
            "factor_key": "lf-active-score",
            "title": "Raise conviction on reclaim setups",
            "scope_label": "Strategy",
            "effect_summary": "increase score",
        },
    )


def test_build_today_learning_strategies_adds_learning_summary_text():
    payload = build_today_learning_strategies(
        reflection={"status": "succeeded", "status_label": "Succeeded"},
        learning_factors=(
            {
                "factor_key": "lf-earnings-vol",
                "title": "Post-earnings volatility mean reversion",
                "status": "active",
                "status_label": "Active",
                "scope": "strategy",
                "scope_label": "Strategy",
                "strategy_id": "earnings_drift_v1",
                "recommendation": "Increase put-spread allocation in elevated-vol regimes.",
                "confidence": Decimal("0.78"),
                "effect_tags": ("increase_score",),
            },
        ),
        strategy_performance=(
            {
                "strategy_id": "earnings_drift_v1",
                "lifecycle_status": "active",
                "lifecycle_status_label": "Active",
                "win_rate": Decimal("62.0"),
                "total_pnl": Decimal("3240"),
            },
        ),
        strategy_proposals=(),
        strategy_definitions=(),
        strategy_evaluation_results=(),
    )

    performance_row = payload["strategy_performance"][0]
    assert performance_row["learning_summary"]
    assert "62.0% win rate" in performance_row["learning_summary"]
    assert "Latest learning" in performance_row["learning_summary"]
    assert "Post-earnings volatility mean reversion" in performance_row["learning_summary"]
    assert "Increase put-spread allocation in elevated-vol regimes." in performance_row["learning_summary"]
    assert payload["learning_summary_text"]
    assert "1 active strategy" in payload["learning_summary_text"]
    assert "earnings_drift_v1" in payload["learning_summary_text"]


def test_build_today_learning_strategies_dedupes_strategy_proposals_and_learning_factors():
    payload = build_today_learning_strategies(
        reflection={"status": "succeeded", "status_label": "Succeeded"},
        learning_factors=(
            {
                "factor_key": "lf-1",
                "title": "Reflection observation",
                "status": "active",
                "status_label": "Active",
                "scope": "portfolio",
                "scope_label": "Portfolio",
                "effect_tags": (),
            },
            {
                "factor_key": "lf-2",
                "title": "Reflection observation",
                "status": "active",
                "status_label": "Active",
                "scope": "portfolio",
                "scope_label": "Portfolio",
                "effect_tags": (),
            },
        ),
        strategy_performance=(),
        strategy_proposals=(
            {
                "proposed_strategy_id": "post_gap_vwap_reclaim_v1",
                "display_name": "Post-gap VWAP Reclaim",
                "proposal_status": "duplicate_rejected",
                "proposal_status_label": "Duplicate Rejected",
            },
            {
                "proposed_strategy_id": "post_gap_vwap_reclaim_v1",
                "display_name": "Post-gap VWAP Reclaim",
                "proposal_status": "accepted",
                "proposal_status_label": "Accepted",
            },
        ),
        strategy_definitions=(),
        strategy_evaluation_results=(),
    )

    assert len(payload["strategy_proposals"]) == 1
    assert payload["strategy_proposals"][0]["proposal_status_label"] == "Accepted + Duplicate Rejected"
    assert payload["strategy_proposals"][0]["proposal_count"] == 2
    assert len(payload["learning_factors"]) == 1
    assert payload["learning_factors"][0]["occurrence_count"] == 2


def test_build_today_learning_strategies_ranks_insufficient_evidence_with_rejections():
    assert _proposal_status_rank({"proposal_status": "insufficient_evidence_rejected"})[0] < 99


def test_build_today_learning_strategies_normalizes_reflection_points_for_display():
    payload = build_today_learning_strategies(
        reflection={
            "status": "succeeded",
            "status_label": "Succeeded",
            "what_worked": (
                json.dumps(
                    {
                        "contribution": "High-quality software setup drove gains",
                        "reason": "Analyst sentiment and market trend were both supportive.",
                        "strategy": "valuation_repair_quality_software_v1",
                        "ticker": "CRDO",
                    }
                ),
            ),
            "what_failed": (
                {
                    "contribution": "Missed positive catalyst news",
                    "reason": "The hold decision conflicted with bullish news and low RSI.",
                    "strategy": "catalyst_breakout_v1",
                    "ticker": "NOK",
                },
            ),
            "attribution": (
                {
                    "strategy_id": "portfolio",
                    "result": "mixed",
                    "root_cause": json.dumps(
                        {
                            "bullish_trades": [
                                {
                                    "ticker": "CRDO",
                                    "strategy": "valuation_repair_quality_software_v1",
                                    "pnl": 0.003999,
                                }
                            ],
                            "bearish_trades": [],
                            "risk_off_trades": [],
                        }
                    ),
                },
            ),
        },
        learning_factors=(),
        strategy_performance=(),
        strategy_proposals=(),
        strategy_definitions=(),
        strategy_evaluation_results=(),
    )

    reflection = payload["reflection"]
    assert reflection["what_worked"][0]["summary"] == "High-quality software setup drove gains"
    assert reflection["what_worked"][0]["reason"] == "Analyst sentiment and market trend were both supportive."
    assert reflection["what_worked"][0]["tags"] == ("CRDO", "Valuation Repair Quality Software V1")
    assert reflection["what_failed"][0]["tags"] == ("NOK", "Catalyst Breakout V1")
    assert reflection["attribution"][0]["root_cause_summary"] == (
        "Bullish trades: CRDO via valuation_repair_quality_software_v1 (+0.0040 P&L)"
    )
    assert "{" not in reflection["what_worked"][0]["summary"]
