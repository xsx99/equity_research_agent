"""Ticker-first presenter helpers for the today workspace."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.web.presenters.today_copy import (
    expression_bucket_label,
    lifecycle_label,
    operator_text,
    order_status_label,
    risk_reason_label,
    risk_status_label,
    strategy_label,
)

_ACTIONABLE_DECISIONS = {"enter_long", "enter_short", "trim", "exit"}
_ACTIONABLE_ORDER_STATUSES = {"pending", "accepted", "partial_fill"}
_EMPTY_MARKER = "No material update"
_NO_MATERIAL_TICKER_NEWS = "No material ticker-specific news."
_TECHNICAL_CHART_SPECS = (
    ("price / key level trend", {"price", "price_trend", "key_levels"}),
    ("relative strength trend", {"relative_strength", "relative_strength_trend", "rs"}),
)
_SIGNAL_GROUP_ORDER = (
    "Risk blockers",
    "Decision drivers",
    "Trend",
    "Insider",
    "Policy / Social",
    "Evidence",
    "Data quality",
)


def build_ticker_workspace(
    *,
    trade_rows,
    selected_ticker,
    positions_by_ticker,
    closed_positions_by_ticker=None,
    risk_by_ticker,
    signal_history_by_ticker,
    news_by_ticker,
    fundamentals_by_ticker,
):
    normalized_positions = {_normalize_ticker(ticker): payload for ticker, payload in positions_by_ticker.items()}
    normalized_closed_positions = {
        _normalize_ticker(ticker): payload for ticker, payload in (closed_positions_by_ticker or {}).items()
    }
    normalized_risk = {_normalize_ticker(ticker): payload for ticker, payload in risk_by_ticker.items()}
    normalized_signal_history = {
        _normalize_ticker(ticker): payload for ticker, payload in signal_history_by_ticker.items()
    }
    normalized_news = {_normalize_ticker(ticker): payload for ticker, payload in news_by_ticker.items()}
    normalized_fundamentals = {
        _normalize_ticker(ticker): payload for ticker, payload in fundamentals_by_ticker.items()
    }
    rows_by_ticker = _group_rows_by_ticker(trade_rows)
    ticker_items = _build_ticker_items(
        rows_by_ticker=rows_by_ticker,
        positions_by_ticker=normalized_positions,
        closed_positions_by_ticker=normalized_closed_positions,
        risk_by_ticker=normalized_risk,
        signal_history_by_ticker=normalized_signal_history,
        news_by_ticker=normalized_news,
        fundamentals_by_ticker=normalized_fundamentals,
    )
    buckets = {
        "action_now": [],
        "open_positions": [],
        "closed_today": [],
        "reviewing": [],
        "watch": [],
    }

    for item in ticker_items:
        ticker = item["ticker"]
        if _is_action_now(item):
            item["primary_state"] = "action_now"
            buckets["action_now"].append(item)
        elif ticker in normalized_closed_positions:
            item["primary_state"] = "closed"
            buckets["closed_today"].append(item)
        elif ticker in normalized_positions:
            item["primary_state"] = "open_position"
            buckets["open_positions"].append(item)
        elif _is_reviewing(item):
            item["primary_state"] = "reviewing"
            buckets["reviewing"].append(item)
        else:
            item["primary_state"] = "watch"
            buckets["watch"].append(item)
        item["attention_flags"] = _attention_flags(item)

    buckets["in_position"] = buckets["open_positions"]

    normalized_selected_ticker = _normalize_ticker(selected_ticker)
    available_tickers = {item["ticker"] for items in buckets.values() for item in items}
    if normalized_selected_ticker not in available_tickers:
        normalized_selected_ticker = _default_selected_ticker(buckets)

    return {
        "selected_ticker": normalized_selected_ticker,
        "buckets": buckets,
        "detail": _build_detail(
            selected_ticker=normalized_selected_ticker,
            rows_by_ticker=rows_by_ticker,
            positions_by_ticker=normalized_positions,
            closed_positions_by_ticker=normalized_closed_positions,
            risk_by_ticker=normalized_risk,
            signal_history_by_ticker=normalized_signal_history,
            news_by_ticker=normalized_news,
            fundamentals_by_ticker=normalized_fundamentals,
        ),
    }


def _build_ticker_items(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    positions_by_ticker: dict[str | None, Any],
    closed_positions_by_ticker: dict[str | None, Any],
    risk_by_ticker: dict[str | None, Any],
    signal_history_by_ticker: dict[str | None, Any],
    news_by_ticker: dict[str | None, Any],
    fundamentals_by_ticker: dict[str | None, Any],
) -> list[dict[str, Any]]:
    items_by_ticker: dict[str, dict[str, Any]] = {}
    ticker_keys = list(rows_by_ticker.keys())
    for ticker_group in (
        positions_by_ticker,
        closed_positions_by_ticker,
        risk_by_ticker,
        signal_history_by_ticker,
        news_by_ticker,
        fundamentals_by_ticker,
    ):
        for ticker in ticker_group.keys():
            if ticker and ticker not in ticker_keys:
                ticker_keys.append(ticker)

    for ticker in ticker_keys:
        if not ticker:
            continue

        row_items = rows_by_ticker.get(ticker) or []
        if row_items:
            items_by_ticker[ticker] = _latest_row(row_items, "created_at")
            continue

        items_by_ticker[ticker] = {"ticker": ticker}

    return list(items_by_ticker.values())


def _group_rows_by_ticker(trade_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    rows_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in trade_rows:
        ticker = _normalize_ticker(row.get("ticker"))
        if not ticker:
            continue

        normalized_row = dict(row)
        normalized_row["ticker"] = ticker
        rows_by_ticker.setdefault(ticker, []).append(normalized_row)

    return rows_by_ticker


def _normalize_ticker(value: Any) -> str | None:
    if value is None:
        return None
    ticker = str(value).strip().upper()
    return ticker or None


def _is_action_now(row: dict[str, Any]) -> bool:
    order_status = str(row.get("order_status") or "").strip().lower()
    if order_status in _ACTIONABLE_ORDER_STATUSES:
        return True

    decision = str(row.get("decision") or "").strip().lower()
    risk_status = str(row.get("risk_status") or "").strip().lower()
    has_material_signal_change = bool(row.get("material_signal_change"))

    if decision in _ACTIONABLE_DECISIONS and (
        has_material_signal_change
        or risk_status in {"high", "critical", "blocked"}
        or "high" in risk_status
        or "critical" in risk_status
        or "blocked" in risk_status
        or "reduced" in risk_status
    ):
        return True

    if risk_status in {"high", "critical", "blocked"}:
        return True
    if "high" in risk_status or "critical" in risk_status or "blocked" in risk_status:
        return True
    if "reduced" in risk_status:
        return True

    return False


def _item_priority(row: dict[str, Any]) -> tuple[int, int, int, int]:
    order_status = str(row.get("order_status") or "").strip().lower()
    decision = str(row.get("decision") or "").strip().lower()
    risk_status = str(row.get("risk_status") or "").strip().lower()
    has_material_signal_change = bool(row.get("material_signal_change"))
    return (
        1 if order_status in _ACTIONABLE_ORDER_STATUSES else 0,
        1 if has_material_signal_change else 0,
        1 if decision in _ACTIONABLE_DECISIONS else 0,
        1 if (
            risk_status in {"high", "critical", "blocked"}
            or "high" in risk_status
            or "critical" in risk_status
            or "blocked" in risk_status
            or "reduced" in risk_status
        )
        else 0,
    )


def _default_selected_ticker(buckets: dict[str, list[dict[str, Any]]]) -> str | None:
    for bucket_name in ("action_now", "open_positions", "reviewing", "watch", "closed_today"):
        if buckets[bucket_name]:
            return buckets[bucket_name][0]["ticker"]
    return None


def _is_reviewing(row: dict[str, Any]) -> bool:
    if bool(row.get("material_signal_change")):
        return True

    risk_status = str(row.get("risk_status") or "").strip().lower()
    if risk_status in {"high", "critical", "blocked"}:
        return True
    if "high" in risk_status or "critical" in risk_status or "blocked" in risk_status or "reduced" in risk_status:
        return True

    return False


def _attention_flags(row: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if bool(row.get("material_signal_change")):
        flags.append("material_change")

    order_status = str(row.get("order_status") or "").strip().lower()
    if order_status in _ACTIONABLE_ORDER_STATUSES:
        flags.append("pending_execution")

    risk_status = str(row.get("risk_status") or "").strip().lower()
    if (
        risk_status in {"high", "critical", "blocked"}
        or "high" in risk_status
        or "critical" in risk_status
        or "blocked" in risk_status
        or "reduced" in risk_status
    ):
        flags.append("risk_attention")

    return flags


def _build_detail(
    *,
    selected_ticker: str | None,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    positions_by_ticker: dict[str | None, Any],
    closed_positions_by_ticker: dict[str | None, Any],
    risk_by_ticker: dict[str | None, Any],
    signal_history_by_ticker: dict[str | None, Any],
    news_by_ticker: dict[str | None, Any],
    fundamentals_by_ticker: dict[str | None, Any],
) -> dict[str, Any] | None:
    if not selected_ticker:
        return None

    raw_decisions = rows_by_ticker.get(selected_ticker, [])
    decision_history = _sort_timestamped_items(raw_decisions, "created_at")
    latest_decision = _latest_decision(raw_decisions)
    signal_history = signal_history_by_ticker.get(selected_ticker) or {}
    technical_charts = _build_technical_charts(signal_history.get("technical"))
    news_snippets = _build_snippets(news_by_ticker.get(selected_ticker))
    fundamental_snippets = _build_snippets(fundamentals_by_ticker.get(selected_ticker))
    position = positions_by_ticker.get(selected_ticker) or {"summary": _EMPTY_MARKER}
    closed_position = closed_positions_by_ticker.get(selected_ticker) or {}
    risk = risk_by_ticker.get(selected_ticker) or {}
    risk_history = _build_risk_history(risk.get("history"))
    trade_summary = _decision_summary(latest_decision)
    key_drivers = _decision_rationale_items(latest_decision, "key_drivers")
    counterarguments = _decision_rationale_items(latest_decision, "counterarguments")
    invalidators = _decision_invalidators(latest_decision)
    signal_summary = {
        **_build_signal_summary(signal_history),
        "technical_charts": technical_charts,
        "news_snippets": news_snippets,
        "event_news_summary": _build_event_news_summary(news_snippets),
        "fundamental_snippets": fundamental_snippets,
    }
    latest_risk_summary = {
        "status": risk.get("status") or _EMPTY_MARKER,
        "status_label": risk_status_label(risk.get("status")) or _EMPTY_MARKER,
        "reason": risk_reason_label(risk.get("reason")) or operator_text(risk.get("reason")) or _EMPTY_MARKER,
        "lookahead_risk_source": risk.get("lookahead_risk_source"),
        "hedge_overlay_reason": _hedge_overlay_reason(risk.get("generated_hedge_action")),
    }

    latest_conclusion = {
        "trade_decision": {
            "ticker": selected_ticker,
            "value": latest_decision.get("decision"),
            "label": _humanize_label(latest_decision.get("decision")) or _EMPTY_MARKER,
            "strategy_id": latest_decision.get("selected_strategy_id") or _EMPTY_MARKER,
            "strategy_label": strategy_label(latest_decision.get("selected_strategy_id")) or _EMPTY_MARKER,
            "expression_bucket_id": latest_decision.get("expression_bucket_id") or _EMPTY_MARKER,
            "expression_bucket_label": expression_bucket_label(latest_decision.get("expression_bucket_id")) or _EMPTY_MARKER,
            "confidence": latest_decision.get("confidence"),
        },
        "signal_summary": signal_summary,
        "risk_summary": latest_risk_summary,
        "position_execution": {
            "position": position,
            "position_label": position.get("position_label"),
            "order_status": position.get("order_status") or latest_decision.get("order_status") or _EMPTY_MARKER,
            "order_status_label": order_status_label(position.get("order_status") or latest_decision.get("order_status"))
            or _EMPTY_MARKER,
            "summary": position.get("summary") or _EMPTY_MARKER,
        },
    }
    if trade_summary != _EMPTY_MARKER:
        latest_conclusion["trade_decision"]["summary"] = trade_summary
    if key_drivers:
        latest_conclusion["trade_decision"]["key_drivers"] = key_drivers
    if counterarguments:
        latest_conclusion["trade_decision"]["counterarguments"] = counterarguments
    if invalidators:
        latest_conclusion["trade_decision"]["invalidators"] = invalidators

    tabs = {
        "timeline": _build_timeline(
            signal_history=signal_history,
            decisions=decision_history,
            risk_history=risk_history,
            latest_signal_summary=signal_summary,
            latest_risk_summary=latest_risk_summary,
        ),
        "trend": {
            "technical": technical_charts,
            "news": news_snippets,
            "fundamental": fundamental_snippets,
        },
        "decisions": _build_decision_list(decision_history),
        "risk": {
            "current_stance": latest_conclusion["risk_summary"],
            "position_state": position,
            "history": risk_history,
            "raw_json": risk.get("raw_json"),
        },
    }

    return {
        "ticker": selected_ticker,
        "lifecycle": _build_lifecycle(
            latest_decision=latest_decision,
            decisions=decision_history,
            position=position,
            closed_position=closed_position,
        ),
        "latest_conclusion": latest_conclusion,
        "tabs": tabs,
    }


def _build_signal_summary(signal_history: Any) -> dict[str, Any]:
    summary_items = signal_history.get("summary") if isinstance(signal_history, dict) else signal_history
    timeline_items = signal_history.get("timeline") if isinstance(signal_history, dict) else None
    bullets = _dedupe_summary_bullets(summary_items)
    if bullets == [_EMPTY_MARKER]:
        return {
            "summary_bullets": bullets,
            "hidden_bullet_count": 0,
            "latest_signal_time_label": _latest_signal_time_label(timeline_items),
            "primary_sections": ({"label": "Status", "bullets": (_EMPTY_MARKER,)},),
            "grouped_sections": (),
        }

    grouped = _group_summary_bullets(bullets)
    if len(bullets) <= 5:
        primary = bullets
        hidden_count = 0
    else:
        ordered = []
        for label in _SIGNAL_GROUP_ORDER:
            ordered.extend(grouped.get(label, ()))
        primary = ordered[:5]
        hidden_count = max(len(ordered) - len(primary), 0)
    sections = tuple(
        {"label": label, "bullets": tuple(grouped[label])}
        for label in _SIGNAL_GROUP_ORDER
        if grouped.get(label)
    )
    return {
        "summary_bullets": primary,
        "hidden_bullet_count": hidden_count,
        "latest_signal_time_label": _latest_signal_time_label(timeline_items),
        "primary_sections": _primary_signal_sections(primary),
        "grouped_sections": sections,
    }


def _primary_signal_sections(primary_bullets: list[str]) -> tuple[dict[str, Any], ...]:
    grouped_primary = _group_summary_bullets(primary_bullets)
    return tuple(
        {"label": label, "bullets": tuple(grouped_primary[label])}
        for label in _SIGNAL_GROUP_ORDER
        if grouped_primary.get(label)
    )


def _dedupe_summary_bullets(summary_items: Any) -> list[str]:
    if isinstance(summary_items, list):
        bullets = []
        seen: set[str] = set()
        for item in summary_items:
            bullet = str(item).strip()
            if not bullet or bullet in seen:
                continue
            seen.add(bullet)
            bullets.append(operator_text(bullet))
        if bullets:
            return bullets
    return [_EMPTY_MARKER]


def _group_summary_bullets(bullets: list[str]) -> dict[str, list[str]]:
    grouped = {label: [] for label in _SIGNAL_GROUP_ORDER}
    for bullet in bullets:
        grouped[_summary_group_label(bullet)].append(bullet)
    return grouped


def _summary_group_label(bullet: str) -> str:
    normalized = bullet.strip().lower()
    if any(token in normalized for token in ("blocked", "risk ", "invalidator", "event cluster")):
        return "Risk blockers"
    if any(token in normalized for token in ("insider", "form 4", "cluster buy", "net buy")):
        return "Insider"
    if any(token in normalized for token in ("policy", "social", "tariff", "trump", "official update")):
        return "Policy / Social"
    if any(token in normalized for token in ("relative strength", "breakout", "trend", "volume", "price ")):
        return "Trend"
    if any(token in normalized for token in ("stale", "missing", "data quality", "freshness")):
        return "Data quality"
    if any(token in normalized for token in ("catalyst", "guidance", "earnings", "headline", "fresh ")):
        return "Evidence"
    return "Decision drivers"


def _build_technical_charts(technical_items: Any) -> list[dict[str, Any]]:
    items = technical_items if isinstance(technical_items, list) else []
    charts: list[dict[str, Any]] = []
    for chart_type, labels in _TECHNICAL_CHART_SPECS:
        source = next(
            (
                item
                for item in items
                if str(item.get("label") or "").strip().lower() in labels
            ),
            None,
        )
        if source is None:
            charts.append(
                {
                    "chart_type": chart_type,
                    "label": _EMPTY_MARKER,
                    "points": [],
                    "summary": _EMPTY_MARKER,
                    "empty": True,
                }
            )
            continue

        charts.append(
            {
                "chart_type": chart_type,
                "label": source.get("label") or _EMPTY_MARKER,
                "points": list(source.get("points") or []),
                "summary": source.get("summary") or _EMPTY_MARKER,
                "empty": False,
            }
        )
    return charts


def _build_snippets(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items:
        return [_empty_snippet()]

    snippets: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        snippets.append(
            {
                "title": operator_text(item.get("title")) or _EMPTY_MARKER,
                "summary": operator_text(item.get("summary")) or _EMPTY_MARKER,
                "time": item.get("published_at") or item.get("as_of"),
                "event_type": item.get("event_type"),
                "importance": item.get("importance"),
                "empty": False,
            }
        )
    snippets.sort(key=lambda item: _sort_key_desc(item.get("time")))
    return snippets or [_empty_snippet()]


def _build_event_news_summary(news_snippets: list[dict[str, Any]]) -> str | None:
    primary_snippet = next(
        (
            item
            for item in news_snippets
            if _is_material_news_snippet(item)
        ),
        None,
    )
    if primary_snippet is None:
        has_non_empty_news = any(not item.get("empty") for item in news_snippets)
        return _NO_MATERIAL_TICKER_NEWS if has_non_empty_news else None

    title = str(primary_snippet.get("title") or "").strip()
    summary = str(primary_snippet.get("summary") or "").strip()
    if title and summary and summary != title:
        return f"{title}: {_with_terminal_period(summary)}"
    if summary:
        return _with_terminal_period(summary)
    if title:
        return _with_terminal_period(title)
    return None


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
    if stripped.endswith((".", "!", "?")):
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
    return {
        "label": _humanize_label(row.get("decision")) or _EMPTY_MARKER,
        "strategy_label": strategy_label(row.get("selected_strategy_id")) or _EMPTY_MARKER,
        "summary": _decision_summary(row),
    }


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


def _format_timestamp_label(value: Any) -> str | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


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
        return [str(item).strip() for item in invalidators if str(item).strip()]
    return []


def _decision_rationale_items(row: dict[str, Any], key: str) -> list[str]:
    values = row.get(key)
    if isinstance(values, list):
        return [str(item).strip() for item in values if str(item).strip()]
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
