"""Operator-facing copy helpers for the today workspace."""
from __future__ import annotations

from typing import Any

_STRATEGY_LABELS = {
    "direct_negative_catalyst": "Negative catalyst detected",
    "valuation_repair_quality_software_v1": "Valuation repair setup",
}

_CANDIDATE_RESULT_LABELS = {
    "blocked_by_missing_data": "Blocked: required data unavailable",
    "catalyst_watch": "Catalyst watch",
    "candidate": "Ready for review",
    "no_trade": "No clean entry, so no trade",
    "ordinary_watch": "Still on watch",
}

_LIFECYCLE_LABELS = {
    "closed": "Closed",
    "open_position": "Open Position",
}

_RISK_STATUS_LABELS = {
    "approved": "Approved",
    "reduced_by_concentration_limit": "Reduced: concentration limit",
    "lookahead_force_reduce": "Reduced: lookahead risk",
    "lookahead_reduce": "Reduced: lookahead risk",
    "lookahead_block_open": "Blocked: lookahead risk",
}

_TRADE_IDENTITY_LABELS = {
    "watch_only": "Watch Only",
}

_MANUAL_REQUEST_MODE_LABELS = {
    "review_only": "Review Only",
    "paper_trade_eligible": "Paper Trade Eligible",
}

_MANUAL_REQUEST_STATUS_LABELS = {
    "active": "Pinned",
    "dismissed": "Dismissed",
    "cancelled": "Cancelled",
}


def strategy_label(value: Any) -> str:
    return _mapped_or_humanized(value, _STRATEGY_LABELS)


def candidate_result_label(value: Any) -> str:
    return _mapped_or_humanized(value, _CANDIDATE_RESULT_LABELS)


def lifecycle_label(value: Any) -> str:
    return _mapped_or_humanized(value, _LIFECYCLE_LABELS)


def risk_status_label(value: Any) -> str:
    return _mapped_or_humanized(value, _RISK_STATUS_LABELS)


def expression_bucket_label(value: Any) -> str:
    return _humanize_id(value)


def trade_identity_label(value: Any) -> str:
    return _mapped_or_humanized(value, _TRADE_IDENTITY_LABELS)


def manual_request_mode_label(value: Any) -> str:
    return _mapped_or_humanized(value, _MANUAL_REQUEST_MODE_LABELS)


def manual_request_status_label(value: Any) -> str:
    return _mapped_or_humanized(value, _MANUAL_REQUEST_STATUS_LABELS)


def _mapped_or_humanized(value: Any, mapping: dict[str, str]) -> str:
    normalized = _normalize_key(value)
    if not normalized:
        return ""
    return mapping.get(normalized, _humanize_id(normalized))


def _humanize_id(value: Any) -> str:
    normalized = _normalize_key(value)
    if not normalized:
        return ""
    return " ".join(part.capitalize() for part in normalized.replace("_", " ").split())


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()
