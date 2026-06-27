"""Common scalar and formatting helpers for SQLAlchemy trading repositories."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from src.trading.brokers.paper_option import PaperOptionOrderRecord


def _to_uuid(value: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, str(value))


def _to_uuid_or_none(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    return _to_uuid(value)


def _decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _datetime_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _legacy_option_client_order_id(order: PaperOptionOrderRecord) -> str:
    return (
        order.client_order_id
        or f"{order.trade_date.isoformat()}:{order.ticker}:{order.strategy_id}:{order.action}"
    )


def _format_option_contract_symbol(*, ticker: str, expiry: date, option_type: str, strike: float) -> str:
    option_code = "C" if option_type == "call" else "P"
    strike_component = f"{int(round(float(strike) * 1000)):08d}"
    return f"{ticker.upper()}{expiry.strftime('%y%m%d')}{option_code}{strike_component}"


def _latest_row_sort_key(row: Any, timestamp_field: str, id_field: str) -> tuple[datetime, str]:
    timestamp = getattr(row, timestamp_field, None) or datetime.min.replace(tzinfo=timezone.utc)
    return timestamp, str(getattr(row, id_field, "") or "")


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
