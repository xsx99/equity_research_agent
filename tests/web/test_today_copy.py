"""Tests for user-facing today workspace copy helpers."""
from __future__ import annotations

from src.web.presenters.today_copy import (
    candidate_result_label,
    lifecycle_label,
    manual_request_mode_label,
    manual_request_status_label,
    risk_status_label,
    strategy_label,
)


def test_strategy_label_translates_internal_ids_to_operator_copy():
    assert strategy_label("direct_negative_catalyst") == "Negative catalyst detected"
    assert strategy_label("valuation_repair_quality_software_v1") == "Valuation repair setup"


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
