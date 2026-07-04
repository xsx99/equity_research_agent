"""Coverage helpers for sparse market-wide signal families."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.config import INSIDER_COVERAGE_WINDOW_DAYS


def is_insider_data_covered(
    latest_filing_at: datetime | None,
    *,
    decision_time: datetime,
    coverage_window_days: int = INSIDER_COVERAGE_WINDOW_DAYS,
) -> bool:
    """Return True when market-wide Form 4 collection is current enough."""
    if latest_filing_at is None:
        return False
    latest = _normalize_utc(latest_filing_at)
    decision = _normalize_utc(decision_time)
    return latest >= decision - timedelta(days=coverage_window_days)


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
