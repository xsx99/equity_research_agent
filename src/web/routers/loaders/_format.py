"""Leaf formatting and normalization helpers for today router loaders."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_diff(a: Any, b: Any) -> float | None:
    left = _safe_float(a)
    right = _safe_float(b)
    if left is None or right is None:
        return None
    return left - right


def _safe_pct(numerator: Any, denominator: Any) -> float | None:
    num = _safe_float(numerator)
    den = _safe_float(denominator)
    if num is None or den in (None, 0):
        return None
    return num / den


def _safe_sum(rows: tuple[dict[str, Any], ...], key: str) -> float | None:
    total = 0.0
    found = False
    for row in rows:
        value = _safe_float(row.get(key))
        if value is None:
            continue
        total += value
        found = True
    return total if found else None


def _exposure_ratio(exposure: object, account_equity: object) -> float | None:
    exposure_value = _to_float(exposure)
    if exposure_value is None:
        return None
    if abs(exposure_value) <= 1.0:
        return exposure_value

    equity_value = _to_float(account_equity)
    if equity_value is None or equity_value == 0.0:
        return None
    return exposure_value / equity_value


def _normalize_order_status(status: str | None) -> str | None:
    normalized = str(status or "").strip().lower()
    if not normalized:
        return None
    mapping = {
        "pending_new": "pending",
        "partially_filled": "partial_fill",
    }
    return mapping.get(normalized, normalized)


def _sentence_join(*parts: Any) -> str:
    cleaned = [str(part).strip().rstrip(".") for part in parts if str(part or "").strip()]
    if not cleaned:
        return ""
    return ". ".join(cleaned) + "."


def _to_decimal(value: str) -> Decimal:
    try:
        return Decimal(value.strip())
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError(f"Invalid decimal value: {value}") from exc


def _split_csv(raw: str, *, uppercase: bool = False) -> list[str]:
    parts = []
    for value in raw.split(","):
        normalized = value.strip()
        if not normalized:
            continue
        parts.append(normalized.upper() if uppercase else normalized)
    return parts


def _group_latest_by_ticker(rows: tuple[dict[str, Any], ...]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        if ticker not in grouped:
            grouped[ticker] = dict(row)
    return grouped


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_pct(value: Any) -> str:
    return f"{float(value) * 100:.2f}%"


def _format_decimal(value: Any) -> str:
    return f"{float(value):.2f}"
