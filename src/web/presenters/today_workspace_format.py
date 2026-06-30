"""Formatting and empty-state helpers for the today workspace."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.web.presenters.today_copy import operator_text, risk_reason_label

_EMPTY_MARKER = "No material update"
_NO_MATERIAL_TICKER_NEWS = "No material ticker-specific news."
_NEWS_SUMMARY_MAX_CHARS = 280

def _normalize_ticker(value: Any) -> str | None:
    if value is None:
        return None
    ticker = str(value).strip().upper()
    return ticker or None

def _truncate_news_text(value: str, *, limit: int = _NEWS_SUMMARY_MAX_CHARS) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact

    for marker in (". ", "! ", "? "):
        boundary = compact.rfind(marker, 0, limit)
        if boundary >= limit // 2:
            return compact[:boundary].rstrip() + "…"

    boundary = compact.rfind(" ", 0, limit)
    if boundary >= limit // 2:
        return compact[:boundary].rstrip() + "…"

    return compact[:limit].rstrip() + "…"

def _format_recency_label(value: Any, *, as_of: datetime | None = None) -> str | None:
    parsed = _parse_timestamp(value)
    reference_time = _normalize_datetime(as_of)
    if parsed is None or reference_time is None:
        return None

    elapsed_seconds = int((reference_time - parsed).total_seconds())
    if elapsed_seconds < 60:
        return "just now"

    elapsed_minutes = elapsed_seconds // 60
    if elapsed_minutes < 60:
        return f"{elapsed_minutes}m ago"

    elapsed_hours = elapsed_seconds // 3600
    if elapsed_hours < 24:
        return f"{elapsed_hours}h ago"

    elapsed_days = elapsed_seconds // 86400
    if elapsed_days < 7:
        return f"{elapsed_days}d ago"

    elapsed_weeks = elapsed_days // 7
    if elapsed_weeks < 5:
        return f"{elapsed_weeks}w ago"

    return _format_timestamp_label(parsed)

def _is_material_news_snippet(item: dict[str, Any]) -> bool:
    if item.get("empty"):
        return False
    if not (item.get("title") or item.get("summary")):
        return False
    event_type = str(item.get("event_type") or "").strip().casefold()
    if event_type == "general_news":
        return False
    importance = str(item.get("importance") or "").strip().casefold()
    if importance == "low":
        return False
    return True

def _with_terminal_period(value: str) -> str:
    stripped = value.rstrip()
    if not stripped:
        return stripped
    if stripped.endswith((".", "!", "?", "…")):
        return stripped
    return f"{stripped}."

def _latest_signal_time_label(timeline_items: Any) -> str | None:
    if not isinstance(timeline_items, list):
        return None

    latest: datetime | None = None
    for item in timeline_items:
        if not isinstance(item, dict):
            continue
        parsed = _parse_timestamp(item.get("time"))
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed

    if latest is None:
        return None
    return latest.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def _format_timestamp_label(value: Any) -> str | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def _humanize_label(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace("_", " ")
    if not text:
        return None
    return " ".join(part.capitalize() for part in text.split())

def _decision_summary(row: dict[str, Any]) -> str:
    thesis = str(row.get("thesis") or "").strip()
    if thesis:
        return operator_text(thesis)

    metadata = row.get("metadata_json")
    if isinstance(metadata, dict):
        selection_reason = str(metadata.get("selection_reason") or "").strip()
        if selection_reason:
            return operator_text(selection_reason)

    return _EMPTY_MARKER

def _decision_list_summary(row: dict[str, Any]) -> str:
    metadata = row.get("metadata_json")
    if isinstance(metadata, dict):
        selection_reason = str(metadata.get("selection_reason") or "").strip()
        if selection_reason:
            return operator_text(selection_reason)
    return _decision_summary(row)

def _decision_invalidators(row: dict[str, Any]) -> list[str]:
    invalidators = row.get("invalidators")
    if isinstance(invalidators, list):
        cleaned = [operator_text(str(item).strip()) for item in invalidators if str(item).strip()]
        return [item for item in cleaned if item]
    return []

def _decision_rationale_items(row: dict[str, Any], key: str) -> list[str]:
    values = row.get(key)
    if isinstance(values, list):
        cleaned = [operator_text(str(item).strip()) for item in values if str(item).strip()]
        return [item for item in cleaned if item]
    return []

def _risk_summary_copy(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return _EMPTY_MARKER
    if text == _EMPTY_MARKER:
        return _EMPTY_MARKER
    return risk_reason_label(text) or operator_text(text) or text

def _empty_snippet() -> dict[str, Any]:
    return {
        "title": _EMPTY_MARKER,
        "summary": _EMPTY_MARKER,
        "time": None,
        "event_type": None,
        "importance": None,
        "empty": True,
    }

def _empty_timeline_item() -> dict[str, Any]:
    return {
        "time": None,
        "time_label": None,
        "title": "Latest Snapshot",
        "change_type": "latest_snapshot",
        "signal_summary": (_EMPTY_MARKER,),
        "trade_decision": {"label": _EMPTY_MARKER, "strategy_label": _EMPTY_MARKER, "summary": _EMPTY_MARKER},
        "risk": {"status_label": _EMPTY_MARKER, "summary": _EMPTY_MARKER},
        "change_summary": (),
        "detail_anchor": "timeline-empty",
        "empty": True,
    }

def _empty_decision_item() -> dict[str, Any]:
    return {
        "time": None,
        "decision": _EMPTY_MARKER,
        "confidence": None,
        "strategy_id": _EMPTY_MARKER,
        "expression_bucket_id": _EMPTY_MARKER,
        "detail_anchor": "decision-empty",
        "empty": True,
    }

def _empty_risk_history_item() -> dict[str, Any]:
    return {
        "time": None,
        "status": _EMPTY_MARKER,
        "summary": _EMPTY_MARKER,
        "empty": True,
    }

def _sort_key(value: Any) -> tuple[int, str]:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return (1, datetime.max.replace(tzinfo=timezone.utc).isoformat())
    return (0, parsed.astimezone(timezone.utc).isoformat())

def _sort_key_desc(value: Any) -> tuple[int, float]:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return (1, 0.0)
    return (0, -parsed.astimezone(timezone.utc).timestamp())

def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed

def _normalize_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _parse_timestamp(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
