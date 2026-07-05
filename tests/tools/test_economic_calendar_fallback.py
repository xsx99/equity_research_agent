"""Tests for macro economic-calendar provider fallback behavior."""
from __future__ import annotations

from datetime import date

from src.providers.market_data.economic_calendar import EconomicCalendarFallback


def test_economic_calendar_fallback_uses_first_provider_with_events():
    calls: list[str] = []

    class _Primary:
        def macro_events(self, as_of: date) -> tuple[dict[str, object], ...]:
            calls.append(f"primary:{as_of.isoformat()}")
            return ({"event_code": "cpi"},)

    class _Secondary:
        def macro_events(self, as_of: date) -> tuple[dict[str, object], ...]:
            calls.append(f"secondary:{as_of.isoformat()}")
            return ({"event_code": "ppi"},)

    events = EconomicCalendarFallback(_Primary(), _Secondary()).macro_events(date(2026, 7, 3))

    assert events == ({"event_code": "cpi"},)
    assert calls == ["primary:2026-07-03"]


def test_economic_calendar_fallback_uses_next_provider_when_primary_empty():
    calls: list[str] = []

    class _Primary:
        def macro_events(self, as_of: date) -> tuple[dict[str, object], ...]:
            calls.append("primary")
            return ()

    class _Secondary:
        def macro_events(self, as_of: date) -> tuple[dict[str, object], ...]:
            calls.append("secondary")
            return ({"event_code": "ppi"},)

    events = EconomicCalendarFallback(_Primary(), _Secondary()).macro_events(date(2026, 7, 3))

    assert events == ({"event_code": "ppi"},)
    assert calls == ["primary", "secondary"]


def test_economic_calendar_fallback_degrades_to_empty_when_all_providers_fail():
    class _Failing:
        def macro_events(self, as_of: date) -> tuple[dict[str, object], ...]:
            raise RuntimeError("unavailable")

    assert EconomicCalendarFallback(_Failing()).macro_events(date(2026, 7, 3)) == ()
