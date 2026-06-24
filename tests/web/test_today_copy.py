"""Tests for user-facing today workspace copy helpers."""
from __future__ import annotations

from src.web.presenters.today_copy import (
    cache_status_label,
    candidate_result_label,
    generic_status_label,
    lifecycle_label,
    live_status_label,
    macro_regime_label,
    manual_request_mode_label,
    manual_request_status_label,
    operator_text,
    order_status_label,
    recommended_action_label,
    risk_reason_label,
    risk_status_label,
    runtime_mode_label,
    strategy_label,
)


def test_strategy_label_translates_internal_ids_to_operator_copy():
    assert strategy_label("direct_negative_catalyst") == "Negative catalyst detected"
    assert strategy_label("valuation_repair_quality_software_v1") == "Valuation repair setup"
    assert strategy_label("lpsmoke_181857") == "Live pre-open verification"
    assert strategy_label("codex-smoke-58f3aa39-20a4-44b5-91dc-bc2a7b98b463-option-trade") == "Live pre-open verification"


def test_candidate_result_label_translates_rejection_like_results():
    assert candidate_result_label("blocked_by_missing_data") == "Blocked: required data unavailable"
    assert candidate_result_label("no_trade") == "No clean entry, so no trade"
    assert candidate_result_label("ordinary_watch") == "Still on watch"


def test_manual_request_labels_translate_modes_and_statuses():
    assert manual_request_mode_label("review_only") == "Review Only"
    assert manual_request_mode_label("paper_trade_eligible") == "Paper Trade Eligible"
    assert manual_request_status_label("active") == "Pinned"


def test_lifecycle_label_translates_primary_states():
    assert lifecycle_label("closed") == "Closed"
    assert lifecycle_label("open_position") == "Open Position"


def test_risk_status_label_keeps_approved_but_humanizes_blocks():
    assert risk_status_label("approved") == "Approved"
    assert risk_status_label("reduced_by_concentration_limit") == "Reduced: concentration limit"
    assert risk_status_label("lookahead_force_reduce") == "Reduced: lookahead risk"
    assert risk_status_label("lookahead_block_open") == "Blocked: lookahead risk"


def test_status_helpers_translate_operator_visible_snake_case_values():
    assert macro_regime_label("risk_off") == "Risk Off"
    assert runtime_mode_label("dry_run") == "Dry Run"
    assert live_status_label("degraded") == "Degraded"
    assert order_status_label("partial_fill") == "Partial Fill"
    assert recommended_action_label("block_open") == "Block New Entry"
    assert risk_reason_label("within_limits") == "Within Limits"
    assert generic_status_label("succeeded") == "Succeeded"
    assert cache_status_label("miss") == "Cache Miss"


def test_operator_text_humanizes_embedded_snake_case_copy_without_touching_model_names():
    assert operator_text("Direct negative catalyst: general_news") == "Direct negative catalyst: General News"
    assert operator_text("Changed from watch to enter_long") == "Changed from watch to Enter Long"
    assert operator_text("Model gpt-5-mini remained stable") == "Model gpt-5-mini remained stable"


def test_operator_text_rewrites_internal_smoke_copy():
    assert operator_text("codex live preopen verification") == "Live pre-open verification"
    assert operator_text("codex-smoke-58f3aa39-20a4-44b5-91dc-bc2a7b98b463-option-trade") == "Live pre-open verification"
