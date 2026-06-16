"""Structured insider/Form 4 signal extraction from normalized source rows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.trading.signals.sources import SourceRecord


REQUIRED_INSIDER_FIELDS = (
    "purchase_count_30d",
    "sale_count_30d",
    "insider_net_buy_value_30d",
    "insider_net_buy_value_90d",
    "insider_cluster_buy_count_90d",
    "officer_buy_flag",
    "director_buy_flag",
    "sale_concentration_score",
    "recent_form4_filing_at",
)


@dataclass(frozen=True)
class InsiderSignals:
    values: dict[str, Any]
    missing: tuple[str, ...]
    stale: tuple[str, ...] = ()


def build_insider_signals(
    records: list[SourceRecord] | tuple[SourceRecord, ...],
    *,
    decision_time: datetime,
) -> InsiderSignals:
    """Aggregate structured insider rows into deterministic trading-side signals."""
    if not records:
        return InsiderSignals(values={}, missing=REQUIRED_INSIDER_FIELDS)

    thirty_day_cutoff = decision_time - timedelta(days=30)
    ninety_day_cutoff = decision_time - timedelta(days=90)
    buys_30d = 0
    sales_30d = 0
    buy_value_30d = 0.0
    sale_value_30d = 0.0
    buy_value_90d = 0.0
    sale_value_90d = 0.0
    cluster_buy_count_90d = 0
    officer_buy_flag = False
    director_buy_flag = False
    latest_published_at: datetime | None = None

    for record in records:
        payload = dict(record.payload or {})
        published_at = record.published_at
        latest_published_at = published_at if latest_published_at is None else max(latest_published_at, published_at)
        transaction_type = str(payload.get("transaction_type") or "").upper()
        total_value = float(payload.get("total_value") or 0.0)
        is_buy = transaction_type in {"P", "BUY", "A"}
        is_sale = transaction_type in {"S", "SELL"}
        within_30d = published_at >= thirty_day_cutoff
        within_90d = published_at >= ninety_day_cutoff

        if within_30d and is_buy:
            buys_30d += 1
            buy_value_30d += total_value
        if within_30d and is_sale:
            sales_30d += 1
            sale_value_30d += total_value
        if within_90d and is_buy:
            buy_value_90d += total_value
            cluster_buy_count_90d += 1
            officer_buy_flag = officer_buy_flag or bool(payload.get("is_officer"))
            director_buy_flag = director_buy_flag or bool(payload.get("is_director"))
        if within_90d and is_sale:
            sale_value_90d += total_value

    sale_concentration = 0.0
    if buy_value_90d > 0:
        sale_concentration = round(sale_value_90d / buy_value_90d, 4)
    elif sale_value_90d > 0:
        sale_concentration = 1.0

    values: dict[str, Any] = {
        "purchase_count_30d": buys_30d,
        "sale_count_30d": sales_30d,
        "insider_net_buy_value_30d": round(buy_value_30d - sale_value_30d, 4),
        "insider_net_buy_value_90d": round(buy_value_90d - sale_value_90d, 4),
        "insider_cluster_buy_count_90d": cluster_buy_count_90d,
        "officer_buy_flag": officer_buy_flag,
        "director_buy_flag": director_buy_flag,
        "sale_concentration_score": sale_concentration,
        "recent_form4_filing_at": latest_published_at.isoformat() if latest_published_at is not None else None,
    }
    missing = tuple(field for field in REQUIRED_INSIDER_FIELDS if values.get(field) is None)
    return InsiderSignals(values=values, missing=missing)
