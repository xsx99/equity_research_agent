"""Ticker-first presenter helpers for the today workspace."""
from __future__ import annotations

from typing import Any

_ACTIONABLE_DECISIONS = {"enter_long", "enter_short", "trim", "exit"}
_ACTIONABLE_ORDER_STATUSES = {"pending", "accepted", "partial_fill"}


def build_ticker_workspace(
    *,
    trade_rows,
    selected_ticker,
    positions_by_ticker,
    risk_by_ticker,
    signal_history_by_ticker,
    news_by_ticker,
    fundamentals_by_ticker,
):
    del risk_by_ticker, signal_history_by_ticker, news_by_ticker, fundamentals_by_ticker

    normalized_positions = {_normalize_ticker(ticker): payload for ticker, payload in positions_by_ticker.items()}
    ticker_items = _build_ticker_items(trade_rows)
    buckets = {
        "action_now": [],
        "in_position": [],
        "watch": [],
    }

    for item in ticker_items:
        ticker = item["ticker"]
        if _is_action_now(item):
            buckets["action_now"].append(item)
        elif ticker in normalized_positions:
            buckets["in_position"].append(item)
        else:
            buckets["watch"].append(item)

    normalized_selected_ticker = _normalize_ticker(selected_ticker)
    available_tickers = {item["ticker"] for items in buckets.values() for item in items}
    if normalized_selected_ticker not in available_tickers:
        normalized_selected_ticker = _default_selected_ticker(buckets)

    return {
        "selected_ticker": normalized_selected_ticker,
        "buckets": buckets,
        "detail": None,
    }


def _build_ticker_items(trade_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items_by_ticker: dict[str, dict[str, Any]] = {}
    for row in trade_rows:
        ticker = _normalize_ticker(row.get("ticker"))
        if not ticker:
            continue

        item = dict(row)
        item["ticker"] = ticker

        existing = items_by_ticker.get(ticker)
        if existing is None or _item_priority(item) > _item_priority(existing):
            items_by_ticker[ticker] = item

    return list(items_by_ticker.values())


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

    return has_material_signal_change


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
    for bucket_name in ("action_now", "in_position", "watch"):
        if buckets[bucket_name]:
            return buckets[bucket_name][0]["ticker"]
    return None
