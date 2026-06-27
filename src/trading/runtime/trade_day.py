from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def trade_date_for(now: datetime, tz: str) -> date:
    if now.tzinfo is None:
        raise ValueError("trade_date_for_requires_timezone_aware_datetime")
    return now.astimezone(ZoneInfo(tz)).date()


def local_day_bounds_utc(trade_date: date, tz: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(tz)
    local_start = datetime.combine(trade_date, time.min, tzinfo=zone)
    local_end = datetime.combine(trade_date + timedelta(days=1), time.min, tzinfo=zone)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)
