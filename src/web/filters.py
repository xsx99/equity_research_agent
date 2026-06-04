"""Jinja2 template filters and globals."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


def pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value * 100:+.2f}%"


def fmt_conf(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.0%}"


def fmt_currency(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def fmt_number(value: Any, decimals: int = 2) -> str:
    if value is None or value == "":
        return "—"
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    quantized = number.quantize(Decimal(1).scaleb(-decimals))
    return f"{quantized:,.{decimals}f}"


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def iso_datetime(value: Any) -> str:
    dt = _coerce_datetime(value)
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_time(value: Any, display: str = "datetime") -> str:
    dt = _coerce_datetime(value)
    if dt is None:
        return "—"

    local_dt = dt.astimezone()
    if display == "date":
        return local_dt.strftime("%Y-%m-%d")
    if display == "month_day":
        return local_dt.strftime("%m-%d")
    if display == "datetime_seconds":
        return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    return local_dt.strftime("%Y-%m-%d %H:%M %Z")


def register(templates) -> None:
    """Register all filters and globals on a Jinja2Templates instance."""
    templates.env.globals["pct"] = pct
    templates.env.globals["fmt_conf"] = fmt_conf
    templates.env.globals["fmt_currency"] = fmt_currency
    templates.env.globals["fmt_number"] = fmt_number
    templates.env.filters["iso_datetime"] = iso_datetime
    templates.env.filters["local_time"] = local_time
