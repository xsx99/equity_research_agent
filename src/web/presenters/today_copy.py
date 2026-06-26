"""Operator-facing copy helpers for the today workspace."""
from __future__ import annotations

import re
from typing import Any

_SMOKE_DISPLAY_LABEL = "Live pre-open verification"

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
    "watch": "Watch",
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
    "tactical_stock_trade": "Tactical Stock Trade",
    "tactical_option_trade": "Tactical Option Trade",
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

_RISK_APPETITE_LABELS = {
    "balanced": "Balanced",
    "conservative": "Conservative",
    "aggressive": "Aggressive",
    "unavailable": "Unavailable",
}

_MACRO_REGIME_LABELS = {
    "risk_off": "Risk Off",
    "risk_on": "Risk On",
    "neutral": "Neutral",
    "unavailable": "Unavailable",
}

_RUNTIME_MODE_LABELS = {
    "live": "Live",
    "dry_run": "Dry Run",
    "live_manual_review": "Live Manual Review",
}

_LIVE_STATUS_LABELS = {
    "live": "Live",
    "degraded": "Degraded",
    "unavailable": "Unavailable",
}

_ORDER_STATUS_LABELS = {
    "accepted": "Accepted",
    "cancelled": "Cancelled",
    "canceled": "Cancelled",
    "filled": "Filled",
    "partial_fill": "Partial Fill",
    "pending": "Pending",
    "rejected": "Rejected",
}

_OPTION_STRATEGY_TYPE_LABELS = {
    "long_call": "Long Call",
    "long_put": "Long Put",
    "covered_call": "Covered Call",
    "protective_put": "Protective Put",
}

_RECOMMENDED_ACTION_LABELS = {
    "block_open": "Block New Entry",
}

_RISK_REASON_LABELS = {
    "within_limits": "Within Limits",
}

_INTENT_TYPE_LABELS = {
    "core_index": "Core Index",
    "core_holding": "Core Holding",
}

_CACHE_STATUS_LABELS = {
    "hit": "Cache Hit",
    "miss": "Cache Miss",
    "stale": "Stale Cache",
}

_INLINE_LABELS = {
    **_CANDIDATE_RESULT_LABELS,
    **_LIFECYCLE_LABELS,
    **_RISK_STATUS_LABELS,
    **_TRADE_IDENTITY_LABELS,
    **_MANUAL_REQUEST_MODE_LABELS,
    **_MANUAL_REQUEST_STATUS_LABELS,
    **_RISK_APPETITE_LABELS,
    **_MACRO_REGIME_LABELS,
    **_RUNTIME_MODE_LABELS,
    **_LIVE_STATUS_LABELS,
    **_ORDER_STATUS_LABELS,
    **_OPTION_STRATEGY_TYPE_LABELS,
    **_RECOMMENDED_ACTION_LABELS,
    **_RISK_REASON_LABELS,
    **_INTENT_TYPE_LABELS,
    **_CACHE_STATUS_LABELS,
}

_INLINE_IDENTIFIER_PATTERN = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")
_SMOKE_COPY_PATTERN = re.compile(
    r"lpsmoke(?:[_\s-]?\d+)?|codex live preopen (?:verification|order smoke(?::[A-Za-z0-9._-]+)?)|codex-smoke(?:[-_:][A-Za-z0-9._-]+)+",
    re.IGNORECASE,
)
_DEGRADED_LINKAGE_PATTERN = re.compile(
    r"backend audit linkage has not reached a signal snapshot yet\.?",
    re.IGNORECASE,
)


def strategy_label(value: Any) -> str:
    if is_internal_smoke_text(value):
        return _SMOKE_DISPLAY_LABEL
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


def risk_appetite_label(value: Any) -> str:
    return _mapped_or_humanized(value, _RISK_APPETITE_LABELS)


def macro_regime_label(value: Any) -> str:
    return _mapped_or_humanized(value, _MACRO_REGIME_LABELS)


def runtime_mode_label(value: Any) -> str:
    return _mapped_or_humanized(value, _RUNTIME_MODE_LABELS)


def live_status_label(value: Any) -> str:
    return _mapped_or_humanized(value, _LIVE_STATUS_LABELS)


def job_status_label(value: Any) -> str:
    return _mapped_or_humanized(value, {})


def order_status_label(value: Any) -> str:
    return _mapped_or_humanized(value, _ORDER_STATUS_LABELS)


def option_strategy_type_label(value: Any) -> str:
    return _mapped_or_humanized(value, _OPTION_STRATEGY_TYPE_LABELS)


def recommended_action_label(value: Any) -> str:
    return _mapped_or_humanized(value, _RECOMMENDED_ACTION_LABELS)


def risk_reason_label(value: Any) -> str:
    return _mapped_or_humanized(value, _RISK_REASON_LABELS)


def event_type_label(value: Any) -> str:
    return _mapped_or_humanized(value, {})


def risk_source_label(value: Any) -> str:
    return _mapped_or_humanized(value, {})


def intent_type_label(value: Any) -> str:
    return _mapped_or_humanized(value, _INTENT_TYPE_LABELS)


def scope_label(value: Any) -> str:
    return _mapped_or_humanized(value, {})


def generic_status_label(value: Any) -> str:
    return _mapped_or_humanized(value, {})


def cache_status_label(value: Any) -> str:
    return _mapped_or_humanized(value, _CACHE_STATUS_LABELS)


def operator_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _DEGRADED_LINKAGE_PATTERN.fullmatch(text):
        return "Signal details not available yet."
    if _SMOKE_COPY_PATTERN.fullmatch(text):
        return _SMOKE_DISPLAY_LABEL
    text = _SMOKE_COPY_PATTERN.sub(_SMOKE_DISPLAY_LABEL, text)
    return _INLINE_IDENTIFIER_PATTERN.sub(_replace_inline_identifier, text)


def is_internal_smoke_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return _SMOKE_COPY_PATTERN.search(text) is not None


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


def _replace_inline_identifier(match: re.Match[str]) -> str:
    token = match.group(0)
    return _INLINE_LABELS.get(token, _humanize_id(token))
