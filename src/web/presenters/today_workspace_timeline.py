"""Timeline and lifecycle helpers for the today workspace presenter."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.web.presenters.today_copy import (
    expression_bucket_label,
    lifecycle_label,
    operator_text,
    risk_status_label,
    strategy_label,
)
from src.web.presenters.today_workspace_format import (
    _EMPTY_MARKER,
    _decision_list_summary,
    _decision_summary,
    _empty_decision_item,
    _empty_risk_history_item,
    _empty_timeline_item,
    _format_timestamp_label,
    _humanize_label,
    _parse_timestamp,
    _risk_summary_copy,
    _sort_key,
)

def _build_timeline(
    *,
    signal_history: dict[str, Any],
    decisions: list[dict[str, Any]],
    risk_history: list[dict[str, Any]],
    latest_signal_summary: dict[str, Any],
    latest_risk_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    signal_events = _build_signal_timeline_events(signal_history.get("timeline"))
    if signal_events:
        material_events = [item for item in signal_events[1:] if item.get("material_change")]
        if material_events:
            timeline.append(
                _history_card_from_signal_event(
                    signal_events[0],
                    decisions=decisions,
                    risk_history=risk_history,
                    latest_risk_summary=latest_risk_summary,
                    change_type="baseline",
                )
            )
            timeline.extend(
                _history_card_from_signal_event(
                    item,
                    decisions=decisions,
                    risk_history=risk_history,
                    latest_risk_summary=latest_risk_summary,
                    change_type="material_change",
                )
                for item in material_events
            )
        else:
            timeline.append(
                _history_card_from_signal_event(
                    signal_events[-1],
                    decisions=decisions,
                    risk_history=risk_history,
                    latest_risk_summary=latest_risk_summary,
                    change_type="latest_snapshot",
                )
            )

    timeline.extend(
        _history_card_from_decision(
            item,
            risk_history=risk_history,
            latest_risk_summary=latest_risk_summary,
            latest_signal_summary=latest_signal_summary,
            change_type="material_change" if index > 0 else "baseline",
            detail_anchor=f"decision-{index + 1}",
        )
        for index, item in enumerate(decisions)
    )

    timeline.sort(key=lambda item: _sort_key(item.get("time")))
    return timeline or [_empty_timeline_item()]

def _build_history_highlights(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dated_by_day: dict[str, dict[str, Any]] = {}
    undated: list[dict[str, Any]] = []
    for item in timeline:
        parsed = _parse_timestamp(item.get("time"))
        if parsed is None:
            undated.append(item)
            continue
        day_key = parsed.astimezone(timezone.utc).date().isoformat()
        current = dated_by_day.get(day_key)
        if current is None or _sort_key(item.get("time")) > _sort_key(current.get("time")):
            dated_by_day[day_key] = item

    limited_dated = sorted(dated_by_day.values(), key=lambda item: _sort_key(item.get("time")))[-10:]
    return sorted([*limited_dated, *undated], key=lambda item: _sort_key(item.get("time")))

def _build_signal_timeline_events(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    events: list[dict[str, Any]] = []
    ordered_items = _sort_timestamped_items(items, "time")
    seen_signal_entries: set[tuple[str, str, str, str]] = set()
    phase_counts: dict[str, int] = {}
    previous_phase_state: dict[str, dict[str, str]] = {}
    previous_phase_summary: dict[str, str] = {}

    for index, item in enumerate(ordered_items, start=1):
        if not isinstance(item, dict):
            continue
        phase = _timeline_phase_value(item)
        event_type = str(item.get("event_type") or "signal").strip().lower() or "signal"
        summary = str(item.get("summary") or _EMPTY_MARKER).strip() or _EMPTY_MARKER
        signal_entry_key = (
            str(item.get("time") or ""),
            phase,
            event_type,
            summary,
        )
        if signal_entry_key in seen_signal_entries:
            continue
        seen_signal_entries.add(signal_entry_key)

        phase_key = phase or event_type
        phase_counts[phase_key] = phase_counts.get(phase_key, 0) + 1
        current_state = _timeline_state_map(summary)
        previous_state = previous_phase_state.get(phase_key, {})
        previous_summary = previous_phase_summary.get(phase_key)
        delta_fields = _timeline_delta_fields(previous_state, current_state)
        summary_changed = bool(previous_summary and previous_summary != summary)

        event = {
            "time": item.get("time"),
            "time_label": _format_timestamp_label(item.get("time")),
            "title": _timeline_history_title(phase, event_type, phase_counts[phase_key], item.get("time")),
            "summary": summary,
            "detail_anchor": f"signal-{index}",
            "material_change": phase_counts[phase_key] > 1 and (bool(delta_fields) or summary_changed),
        }
        if delta_fields:
            event["change_summary"] = tuple(delta_fields)
        elif event["material_change"]:
            event["change_summary"] = ("signal summary updated",)
        source_refs = tuple(item.get("source_refs") or ())
        if source_refs:
            event["source_refs"] = source_refs

        previous_phase_state[phase_key] = current_state
        previous_phase_summary[phase_key] = summary
        events.append(event)

    events.sort(key=lambda item: _sort_key(item.get("time")))
    return events

def _history_card_from_signal_event(
    item: dict[str, Any],
    *,
    decisions: list[dict[str, Any]],
    risk_history: list[dict[str, Any]],
    latest_risk_summary: dict[str, Any],
    change_type: str,
) -> dict[str, Any]:
    decision = _latest_item_as_of(decisions, "created_at", item.get("time"))
    return {
        "time": item.get("time"),
        "time_label": item.get("time_label") or _format_timestamp_label(item.get("time")),
        "title": item.get("title") or "Signal Snapshot",
        "change_type": change_type,
        "signal_summary": tuple(_history_signal_bullets(item.get("summary"))),
        "trade_decision": _history_trade_decision_view(decision),
        "risk": _history_risk_view(
            _latest_item_as_of(risk_history, "time", item.get("time")),
            latest_risk_summary=latest_risk_summary,
        ),
        "change_summary": tuple(item.get("change_summary") or ()),
        "detail_anchor": item.get("detail_anchor"),
        "source_refs": tuple(item.get("source_refs") or ()),
    }

def _history_card_from_decision(
    item: dict[str, Any],
    *,
    risk_history: list[dict[str, Any]],
    latest_risk_summary: dict[str, Any],
    latest_signal_summary: dict[str, Any],
    change_type: str,
    detail_anchor: str,
) -> dict[str, Any]:
    label = _humanize_label(item.get("decision")) or _EMPTY_MARKER
    return {
        "time": item.get("created_at"),
        "time_label": _format_timestamp_label(item.get("created_at")),
        "title": f"Decision: {label}",
        "change_type": change_type,
        "signal_summary": tuple(latest_signal_summary.get("summary_bullets") or (_EMPTY_MARKER,)),
        "trade_decision": _history_trade_decision_view(item),
        "risk": _history_risk_view(
            _latest_item_as_of(risk_history, "time", item.get("created_at")),
            latest_risk_summary=latest_risk_summary,
        ),
        "change_summary": (),
        "detail_anchor": detail_anchor,
        "source_refs": (),
    }

def _timeline_phase_value(item: dict[str, Any]) -> str:
    phase = str(item.get("phase") or "").strip().lower()
    if phase:
        return phase
    event_type = str(item.get("event_type") or "").strip().lower()
    if event_type in {"pre_open", "intraday", "post_close"}:
        return event_type
    return ""

def _timeline_history_title(phase: str, event_type: str, occurrence: int, time_value: Any) -> str:
    if phase:
        return _timeline_phase_title(phase, occurrence, time_value)
    if occurrence == 1:
        return "Initial Snapshot"
    if event_type == "intraday":
        label = _intraday_time_label(time_value)
        return f"Intraday Refresh {label}".strip()
    return "Signal Update"

def _timeline_phase_title(phase: str, occurrence: int, time_value: Any) -> str:
    base = " ".join(part.capitalize() for part in phase.replace("_", " ").split()) or "Signal"
    if occurrence == 1:
        return f"{base} Baseline"
    if phase == "intraday":
        label = _intraday_time_label(time_value)
        return f"{base} Refresh {label}".strip()
    return f"{base} Rerun"

def _intraday_time_label(value: Any) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return ""
    return parsed.astimezone(timezone.utc).strftime("%H:%M")

def _timeline_state_map(summary: Any) -> dict[str, str]:
    text = str(summary or "").strip()
    if not text:
        return {}
    state: dict[str, str] = {}
    for raw_clause in text.replace(";", ",").split(","):
        clause = raw_clause.strip()
        lowered = clause.lower()
        if lowered.startswith("sentiment "):
            state["sentiment"] = clause.split(" ", 1)[1].strip()
        elif lowered.startswith("risk "):
            state["risk"] = clause.split(" ", 1)[1].strip()
        elif lowered.startswith("candidate "):
            state["candidate"] = clause.split(" ", 1)[1].strip()
        elif lowered.startswith("event "):
            state["event"] = clause.split(" ", 1)[1].strip()
    return state

def _timeline_delta_fields(previous_state: dict[str, str], current_state: dict[str, str]) -> list[str]:
    if not previous_state:
        return []
    delta_fields = []
    for key, current_value in current_state.items():
        previous_value = previous_state.get(key)
        if previous_value and previous_value != current_value:
            delta_fields.append(
                f"{key} {operator_text(previous_value) or previous_value} -> {operator_text(current_value) or current_value}"
            )
        elif key not in previous_state:
            delta_fields.append(f"new {key}")
    return delta_fields

def _history_signal_bullets(summary: Any) -> list[str]:
    text = str(summary or "").strip()
    if not text:
        return [_EMPTY_MARKER]

    bullets: list[str] = []
    for clause in text.rstrip(".").split(";"):
        for piece in clause.split(","):
            normalized = piece.strip().rstrip(".")
            if normalized:
                cleaned = operator_text(normalized)
                bullets.append(cleaned[0].upper() + cleaned[1:] if cleaned else cleaned)
    return bullets or [_EMPTY_MARKER]

def _history_trade_decision_view(item: dict[str, Any] | None) -> dict[str, Any]:
    row = item or {}
    trade_decision = {
        "label": _humanize_label(row.get("decision")) or _EMPTY_MARKER,
        "strategy_label": strategy_label(row.get("selected_strategy_id")) or _EMPTY_MARKER,
        "summary": _decision_summary(row),
    }
    thesis = operator_text(row.get("thesis")) or None
    approved_weight = row.get("approved_weight")
    confidence = row.get("confidence")
    if thesis is not None:
        trade_decision["thesis"] = thesis
    if approved_weight is not None:
        trade_decision["approved_weight"] = approved_weight
    if confidence is not None:
        trade_decision["confidence"] = confidence
    return trade_decision

def _history_risk_view(item: dict[str, Any] | None, *, latest_risk_summary: dict[str, Any]) -> dict[str, Any]:
    if item:
        return {
            "status_label": risk_status_label(item.get("status")) or _humanize_label(item.get("status")) or _EMPTY_MARKER,
            "summary": _risk_summary_copy(item.get("summary")),
        }
    return {
        "status_label": latest_risk_summary.get("status_label") or _EMPTY_MARKER,
        "summary": latest_risk_summary.get("reason") or _EMPTY_MARKER,
    }

def _latest_item_as_of(items: list[dict[str, Any]], time_key: str, as_of: Any) -> dict[str, Any] | None:
    if not items:
        return None

    as_of_dt = _parse_timestamp(as_of)
    if as_of_dt is None:
        return items[-1]

    latest: dict[str, Any] | None = None
    for item in items:
        item_dt = _parse_timestamp(item.get(time_key))
        if item_dt is None:
            continue
        if item_dt <= as_of_dt:
            latest = item
    return latest or items[-1]

def _build_decision_list(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decision_items: list[dict[str, Any]] = []
    for index, item in enumerate(decisions, start=1):
        decision_item = {
            "time": item.get("created_at"),
            "decision": _humanize_label(item.get("decision")) or _EMPTY_MARKER,
            "confidence": item.get("confidence"),
            "strategy_id": item.get("selected_strategy_id") or _EMPTY_MARKER,
            "strategy_label": strategy_label(item.get("selected_strategy_id")) or _EMPTY_MARKER,
            "expression_bucket_id": item.get("expression_bucket_id") or _EMPTY_MARKER,
            "expression_bucket_label": expression_bucket_label(item.get("expression_bucket_id")) or _EMPTY_MARKER,
            "detail_anchor": f"decision-{index}",
        }
        summary = _decision_list_summary(item)
        if summary != _EMPTY_MARKER:
            decision_item["summary"] = summary
        decision_items.append(decision_item)
    return decision_items or [_empty_decision_item()]

def _build_risk_history(history: Any) -> list[dict[str, Any]]:
    if not isinstance(history, list) or not history:
        return [_empty_risk_history_item()]

    items: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "time": item.get("time"),
                "status": item.get("status") or _EMPTY_MARKER,
                "summary": _risk_summary_copy(item.get("summary")),
            }
        )
    items.sort(key=lambda item: _sort_key(item.get("time")))
    return items or [_empty_risk_history_item()]

def _hedge_overlay_reason(generated_hedge_action: Any) -> str | None:
    if not isinstance(generated_hedge_action, dict):
        return None
    reason_code = generated_hedge_action.get("reason_code")
    if reason_code is None:
        return None
    return str(reason_code).strip() or None

def _build_lifecycle(
    *,
    latest_decision: dict[str, Any],
    decisions: list[dict[str, Any]],
    position: dict[str, Any],
    closed_position: dict[str, Any],
) -> dict[str, Any]:
    entry_decision = next(
        (item for item in decisions if str(item.get("decision") or "").strip().lower() in {"enter_long", "enter_short"}),
        {},
    )
    exit_decision = next(
        (item for item in reversed(decisions) if str(item.get("decision") or "").strip().lower() == "exit"),
        {},
    )

    if closed_position:
        state = "closed"
        opened_at = closed_position.get("opened_at")
        closed_at = closed_position.get("closed_at")
        realized_pnl = closed_position.get("realized_pnl")
    elif position and position.get("summary") != _EMPTY_MARKER:
        state = "open_position"
        opened_at = position.get("opened_at")
        closed_at = None
        realized_pnl = position.get("realized_pnl")
    else:
        state = "watch"
        opened_at = None
        closed_at = None
        realized_pnl = None

    return {
        "state": state,
        "state_label": lifecycle_label(state) or _EMPTY_MARKER,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "realized_pnl": realized_pnl,
        "entry_summary": _decision_summary(entry_decision),
        "exit_summary": _decision_summary(exit_decision),
    }

def _sort_timestamped_items(items: Any, timestamp_key: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    normalized_items = [item for item in items if isinstance(item, dict)]
    return sorted(normalized_items, key=lambda item: _sort_key(item.get(timestamp_key)))

def _latest_decision(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    ordered_decisions = _sort_timestamped_items(decisions, "created_at")
    return ordered_decisions[-1] if ordered_decisions else {}

def _latest_row(rows: list[dict[str, Any]], timestamp_key: str) -> dict[str, Any]:
    ordered_rows = _sort_timestamped_items(rows, timestamp_key)
    return ordered_rows[-1] if ordered_rows else {}

def _timeline_event_type(item: dict[str, Any], *, closed_position: dict[str, Any] | None) -> str:
    if closed_position:
        decision = str(item.get("decision") or "").strip().lower()
        if decision in {"enter_long", "enter_short"}:
            return "entry"
        if decision == "exit":
            return "close"
    return "decision"
