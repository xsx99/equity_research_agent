"""Unit tests for the FRED economic-calendar provider."""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.providers.market_data.fred_economic_calendar import FREDEconomicCalendar


def test_fred_economic_calendar_default_timeout_is_long_enough_for_slow_release_calendar(
    monkeypatch,
):
    captured_timeouts: list[float] = []

    class _Client:
        def __init__(self, *, timeout: float) -> None:
            captured_timeouts.append(timeout)

    monkeypatch.setattr("src.providers.market_data.fred_economic_calendar.httpx.Client", _Client)

    FREDEconomicCalendar(api_key="fred-key")

    assert captured_timeouts == [30.0]


def test_fred_economic_calendar_normalizes_high_signal_release_dates():
    calls: list[tuple[str, dict[str, object]]] = []

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "release_dates": [
                    {
                        "release_id": 10,
                        "release_name": "Consumer Price Index",
                        "date": "2026-07-14",
                    },
                    {
                        "release_id": 46,
                        "release_name": "Producer Price Index",
                        "date": "2026-07-15",
                    },
                    {
                        "release_id": 50,
                        "release_name": "Employment Situation",
                        "date": "2026-07-02",
                    },
                    {
                        "release_id": 300,
                        "release_name": "Weekly Petroleum Status Report",
                        "date": "2026-07-08",
                    },
                    {
                        "release_id": 101,
                        "release_name": "FOMC Press Release",
                        "date": "2026-07-08",
                    },
                    {
                        "release_id": 345,
                        "release_name": "Research Consumer Price Index",
                        "date": "2026-07-14",
                    },
                    {
                        "release_id": 92,
                        "release_name": "Selected Real Retail Sales Series",
                        "date": "2026-07-16",
                    },
                    {
                        "release_id": 999,
                        "release_name": "Broken Date",
                        "date": "not-a-date",
                    },
                ]
            }

    class _Client:
        def get(self, url: str, *, params: dict[str, object]) -> _Response:
            calls.append((url, params))
            return _Response()

    provider = FREDEconomicCalendar(api_key="fred-key", client=_Client(), horizon_days=14)

    events = provider.macro_events(date(2026, 7, 3))

    assert calls == [
        (
            "https://api.stlouisfed.org/fred/releases/dates",
            {
                "api_key": "fred-key",
                "file_type": "json",
                "realtime_start": "2026-07-03",
                "realtime_end": "2026-07-17",
                "include_release_dates_with_no_data": "true",
                "sort_order": "asc",
                "limit": 1000,
            },
        )
    ]
    assert events == (
        {
            "event_code": "consumer_price_index",
            "event_time": datetime(2026, 7, 14, 13, 30, tzinfo=timezone.utc),
            "title": "Consumer Price Index",
            "severity_hint": "high",
            "source": "fred_release_calendar",
        },
        {
            "event_code": "producer_price_index",
            "event_time": datetime(2026, 7, 15, 13, 30, tzinfo=timezone.utc),
            "title": "Producer Price Index",
            "severity_hint": "high",
            "source": "fred_release_calendar",
        },
    )


def test_fred_economic_calendar_keeps_medium_signal_releases():
    def _rows(start: date, end: date) -> list[dict[str, object]]:
        return [
            {
                "release_id": 13,
                "release_name": "Industrial Production and Capacity Utilization",
                "date": "2026-07-16",
            },
            {
                "release_id": 323,
                "release_name": "Consumer Sentiment",
                "date": "2026-07-17",
            },
        ]

    events = FREDEconomicCalendar(api_key=None, row_fetcher=_rows).macro_events(date(2026, 7, 3))

    assert [event["event_code"] for event in events] == [
        "industrial_production_and_capacity_utilization",
        "consumer_sentiment",
    ]
    assert {event["severity_hint"] for event in events} == {"medium"}


def test_fred_economic_calendar_memoizes_once_per_as_of_date():
    calls: list[tuple[date, date]] = []

    def _rows(start: date, end: date) -> list[dict[str, object]]:
        calls.append((start, end))
        return [
            {
                "release_id": 10,
                "release_name": "Consumer Price Index",
                "date": start.isoformat(),
            }
        ]

    provider = FREDEconomicCalendar(api_key=None, horizon_days=7, row_fetcher=_rows)

    first = provider.macro_events(date(2026, 7, 3))
    second = provider.macro_events(date(2026, 7, 3))
    third = provider.macro_events(date(2026, 7, 4))

    assert first == second
    assert third[0]["event_time"].date() == date(2026, 7, 4)
    assert calls == [
        (date(2026, 7, 3), date(2026, 7, 10)),
        (date(2026, 7, 4), date(2026, 7, 11)),
    ]


def test_fred_economic_calendar_degrades_to_empty_without_key_or_on_fetch_error(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    assert FREDEconomicCalendar(api_key=None, row_fetcher=None).macro_events(date(2026, 7, 3)) == ()

    def _raise(start: date, end: date) -> list[dict[str, object]]:
        raise RuntimeError("provider unavailable")

    assert FREDEconomicCalendar(api_key=None, row_fetcher=_raise).macro_events(date(2026, 7, 3)) == ()
