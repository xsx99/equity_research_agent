from __future__ import annotations

from datetime import date, datetime, timezone

from src.trading.runtime.trade_day import local_day_bounds_utc, trade_date_for


def test_trade_date_for_returns_same_local_day_for_realistic_close_case():
    now = datetime(2026, 3, 10, 23, 30, tzinfo=timezone.utc)

    assert trade_date_for(now, "America/New_York") == date(2026, 3, 10)


def test_trade_date_for_prefers_local_date_across_utc_boundary():
    now = datetime(2026, 6, 5, 1, 30, tzinfo=timezone.utc)

    assert trade_date_for(now, "America/New_York") == date(2026, 6, 4)


def test_local_day_bounds_utc_returns_standard_day_window():
    assert local_day_bounds_utc(date(2026, 3, 10), "America/New_York") == (
        datetime(2026, 3, 10, 4, 0, tzinfo=timezone.utc),
        datetime(2026, 3, 11, 4, 0, tzinfo=timezone.utc),
    )


def test_local_day_bounds_utc_handles_dst_spring_forward():
    assert local_day_bounds_utc(date(2026, 3, 8), "America/New_York") == (
        datetime(2026, 3, 8, 5, 0, tzinfo=timezone.utc),
        datetime(2026, 3, 9, 4, 0, tzinfo=timezone.utc),
    )
