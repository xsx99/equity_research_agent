"""Ticker-first presenter helpers for the today workspace."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.web.presenters.today_copy import lifecycle_label
from src.web.presenters.today_workspace_detail import _build_detail, _item_last_updated_at
from src.web.presenters.today_workspace_format import (
    _EMPTY_MARKER,
    _format_recency_label,
    _format_timestamp_label,
    _humanize_label,
    _normalize_datetime,
    _normalize_ticker,
)
from src.web.presenters.today_workspace_timeline import _latest_row

_ACTIONABLE_DECISIONS = {"enter_long", "enter_short", "trim", "exit"}
_ACTIONABLE_ORDER_STATUSES = {"pending", "accepted", "partial_fill"}

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
    as_of: datetime | None = None,
):
    reference_time = _normalize_datetime(as_of) or datetime.now(timezone.utc)
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
        elif ticker in normalized_positions:
            # An open position always wins over a historical closed one for the
            # same ticker (e.g. a prior trade closed earlier, then re-entered).
            # Otherwise the position shows in the portfolio but vanishes from the
            # Open Positions bucket here.
            item["primary_state"] = "open_position"
            buckets["open_positions"].append(item)
        elif ticker in normalized_closed_positions:
            item["primary_state"] = "closed"
            buckets["closed_today"].append(item)
        elif _is_reviewing(item):
            item["primary_state"] = "reviewing"
            buckets["reviewing"].append(item)
        else:
            item["primary_state"] = "watch"
            buckets["watch"].append(item)
        item["attention_flags"] = _attention_flags(item)
        item["latest_decision"] = _humanize_label(item.get("decision"))
        item["card_label"] = _card_label(item)
        item["card_detail"] = _card_detail(item)
        last_updated_at = _item_last_updated_at(
            item,
            position=normalized_positions.get(ticker),
            closed_position=normalized_closed_positions.get(ticker),
            risk=normalized_risk.get(ticker),
            signal_history=normalized_signal_history.get(ticker),
            news_items=normalized_news.get(ticker),
            fundamental_items=normalized_fundamentals.get(ticker),
        )
        if last_updated_at is not None:
            item["last_updated_label"] = _format_timestamp_label(last_updated_at)
            item["recency_label"] = _format_recency_label(last_updated_at, as_of=reference_time)

    buckets["in_position"] = buckets["open_positions"]

    normalized_selected_ticker = _normalize_ticker(selected_ticker)
    available_tickers = {item["ticker"] for items in buckets.values() for item in items}
    if normalized_selected_ticker not in available_tickers:
        normalized_selected_ticker = _default_selected_ticker(buckets)

    # Latest decision run across all tickers — one shared timestamp for the header.
    # (Per-card `recency_label` stays per-ticker; it reflects each ticker's latest
    # activity, not the batch decision time.)
    last_run_at = max(
        (
            normalized
            for row in trade_rows
            if (normalized := _normalize_datetime(row.get("created_at"))) is not None
        ),
        default=None,
    )

    return {
        "selected_ticker": normalized_selected_ticker,
        "buckets": buckets,
        "last_run_at": last_run_at,
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

def _card_label(row: dict[str, Any]) -> str:
    primary_state = str(row.get("primary_state") or "").strip().lower()
    if primary_state == "open_position":
        return lifecycle_label("open_position") or _EMPTY_MARKER
    return _humanize_label(row.get("decision")) or "No Decision"

def _card_detail(row: dict[str, Any]) -> str | None:
    primary_state = str(row.get("primary_state") or "").strip().lower()
    latest_decision = row.get("latest_decision")
    if primary_state == "open_position" and latest_decision:
        return f"Latest decision: {latest_decision}"
    return None
