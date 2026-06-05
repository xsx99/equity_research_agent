"""Ticker-first presenter helpers for the today workspace."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.web.presenters.today_copy import expression_bucket_label, lifecycle_label, risk_status_label, strategy_label

_ACTIONABLE_DECISIONS = {"enter_long", "enter_short", "trim", "exit"}
_ACTIONABLE_ORDER_STATUSES = {"pending", "accepted", "partial_fill"}
_EMPTY_MARKER = "No material update"
_TECHNICAL_CHART_SPECS = (
    ("price / key level trend", {"price", "price_trend", "key_levels"}),
    ("relative strength trend", {"relative_strength", "relative_strength_trend", "rs"}),
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
    trade_summary = _decision_summary(latest_decision)
    invalidators = _decision_invalidators(latest_decision)

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
        "signal_summary": {
            "summary_bullets": _build_summary_bullets(signal_history.get("summary")),
            "technical_charts": technical_charts,
            "news_snippets": news_snippets,
            "fundamental_snippets": fundamental_snippets,
        },
        "risk_summary": {
            "status": risk.get("status") or _EMPTY_MARKER,
            "status_label": risk_status_label(risk.get("status")) or _EMPTY_MARKER,
            "reason": risk.get("reason") or _EMPTY_MARKER,
        },
        "position_execution": {
            "position": position,
            "position_label": position.get("position_label"),
            "order_status": position.get("order_status") or latest_decision.get("order_status") or _EMPTY_MARKER,
            "summary": position.get("summary") or _EMPTY_MARKER,
        },
    }
    if trade_summary != _EMPTY_MARKER:
        latest_conclusion["trade_decision"]["summary"] = trade_summary
    if invalidators:
        latest_conclusion["trade_decision"]["invalidators"] = invalidators

    tabs = {
        "timeline": _build_timeline(
            signal_history=signal_history,
            news_items=news_by_ticker.get(selected_ticker),
            decisions=decision_history,
            closed_position=closed_position,
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
            "history": _build_risk_history(risk.get("history")),
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


def _build_summary_bullets(summary_items: Any) -> list[str]:
    if isinstance(summary_items, list):
        bullets = []
        seen: set[str] = set()
        for item in summary_items:
            bullet = str(item).strip()
            if not bullet or bullet in seen:
                continue
            seen.add(bullet)
            bullets.append(bullet)
        if bullets:
            return bullets
    return [_EMPTY_MARKER]


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
                "title": item.get("title") or _EMPTY_MARKER,
                "summary": item.get("summary") or _EMPTY_MARKER,
                "time": item.get("published_at") or item.get("as_of"),
                "empty": False,
            }
        )
    snippets.sort(key=lambda item: _sort_key_desc(item.get("time")))
    return snippets or [_empty_snippet()]


def _build_timeline(
    *,
    signal_history: dict[str, Any],
    news_items: Any,
    decisions: list[dict[str, Any]],
    closed_position: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []

    for index, item in enumerate(signal_history.get("timeline") or [], start=1):
        if not isinstance(item, dict):
            continue
        timeline.append(
            {
                "time": item.get("time"),
                "event_type": item.get("event_type") or "signal",
                "summary": item.get("summary") or _EMPTY_MARKER,
                "detail_anchor": f"signal-{index}",
            }
        )

    for index, item in enumerate(news_items or [], start=1):
        if not isinstance(item, dict):
            continue
        timeline.append(
            {
                "time": item.get("published_at"),
                "event_type": "news",
                "summary": item.get("title") or _EMPTY_MARKER,
                "detail_anchor": f"news-{index}",
            }
        )

    for index, item in enumerate(decisions, start=1):
        timeline.append(
            {
                "time": item.get("created_at"),
                "event_type": _timeline_event_type(item, closed_position=closed_position),
                "summary": _humanize_label(item.get("decision")) or _EMPTY_MARKER,
                "detail_anchor": f"decision-{index}",
            }
        )

    timeline.sort(key=lambda item: _sort_key(item.get("time")))
    return timeline or [_empty_timeline_item()]


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
                "summary": item.get("summary") or _EMPTY_MARKER,
            }
        )
    items.sort(key=lambda item: _sort_key(item.get("time")))
    return items or [_empty_risk_history_item()]


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
        return thesis

    metadata = row.get("metadata_json")
    if isinstance(metadata, dict):
        selection_reason = str(metadata.get("selection_reason") or "").strip()
        if selection_reason:
            return selection_reason

    return _EMPTY_MARKER


def _decision_list_summary(row: dict[str, Any]) -> str:
    metadata = row.get("metadata_json")
    if isinstance(metadata, dict):
        selection_reason = str(metadata.get("selection_reason") or "").strip()
        if selection_reason:
            return selection_reason
    return _decision_summary(row)


def _decision_invalidators(row: dict[str, Any]) -> list[str]:
    invalidators = row.get("invalidators")
    if isinstance(invalidators, list):
        return [str(item).strip() for item in invalidators if str(item).strip()]
    return []


def _empty_snippet() -> dict[str, Any]:
    return {
        "title": _EMPTY_MARKER,
        "summary": _EMPTY_MARKER,
        "time": None,
        "empty": True,
    }


def _empty_timeline_item() -> dict[str, Any]:
    return {
        "time": None,
        "event_type": "empty",
        "summary": _EMPTY_MARKER,
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
