"""Timezone helpers for scheduler and trade-date logic."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LEGACY_TIMEZONE_ALIASES: dict[str, str] = {
    "US/Eastern": "America/New_York",
}


def resolve_timezone(
    tz_name: str,
    *,
    fallback: str = "UTC",
) -> ZoneInfo:
    """Resolve a timezone name, retrying known legacy aliases before fallback."""
    candidates: list[str] = []
    for candidate in (tz_name, LEGACY_TIMEZONE_ALIASES.get(tz_name), fallback):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        try:
            return ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            continue

    return ZoneInfo("UTC")


def as_trade_date(value: datetime, market_timezone: ZoneInfo) -> date:
    """Convert a timestamp into a market-local trade date."""
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(market_timezone).date()
