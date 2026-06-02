"""Fundamental signal extraction from point-in-time source rows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.trading.signals.sources import SourceRecord


REQUIRED_FUNDAMENTAL_FIELDS = (
    "market_cap_bucket",
    "revenue_growth_score",
    "margin_trend_score",
    "quality_score",
    "valuation_percentile",
    "ev_sales_percentile",
    "fcf_margin_score",
    "short_interest_bucket",
)


@dataclass(frozen=True)
class FundamentalSignals:
    values: dict[str, Any]
    missing: tuple[str, ...]
    stale: tuple[str, ...] = ()


def build_fundamental_signals(records: list[SourceRecord] | tuple[SourceRecord, ...]) -> FundamentalSignals:
    """Build a compact fundamental MVP signal family from latest available row."""
    if not records:
        return FundamentalSignals(values={}, missing=REQUIRED_FUNDAMENTAL_FIELDS)
    record = max(records, key=lambda item: item.available_for_decision_at)
    payload = record.payload
    values: dict[str, Any] = {
        "market_cap_bucket": _market_cap_bucket(payload.get("market_cap")),
        "revenue_growth_score": payload.get("revenue_growth_score"),
        "margin_trend_score": payload.get("margin_trend_score"),
        "quality_score": payload.get("quality_score"),
        "valuation_percentile": payload.get("valuation_percentile"),
        "ev_sales_percentile": payload.get("ev_sales_percentile"),
        "fcf_margin_score": payload.get("fcf_margin_score"),
        "short_interest_bucket": _short_interest_bucket(payload.get("short_interest_pct_float")),
    }
    missing = tuple(field for field in REQUIRED_FUNDAMENTAL_FIELDS if values.get(field) is None)
    return FundamentalSignals(values=values, missing=missing)


def _market_cap_bucket(market_cap: object) -> str | None:
    if not isinstance(market_cap, (int, float)):
        return None
    if market_cap >= 200_000_000_000:
        return "mega"
    if market_cap >= 10_000_000_000:
        return "large"
    if market_cap >= 2_000_000_000:
        return "mid"
    if market_cap >= 300_000_000:
        return "small"
    return "micro"


def _short_interest_bucket(value: object) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    if value >= 20:
        return "high"
    if value >= 10:
        return "elevated"
    if value >= 5:
        return "moderate"
    return "low"
