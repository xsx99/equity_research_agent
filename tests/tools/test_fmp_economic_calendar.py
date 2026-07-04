"""Unit tests for the FMP economic-calendar provider."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.providers.market_data.fmp_economic_calendar import FMPEconomicCalendar


def test_fmp_economic_calendar_normalizes_us_high_and_medium_events():
    calls: list[tuple[date, date]] = []

    def _rows(start: date, end: date) -> list[dict[str, object]]:
        calls.append((start, end))
        return [
            {
                "date": "2026-07-10 12:30:00",
                "country": "US",
                "currency": "USD",
                "event": "CPI (YoY)",
                "impact": "High",
            },
            {
                "date": "2026-07-15 18:00:00",
                "country": "United States",
                "currency": "USD",
                "event": "FOMC Rate Decision",
                "impact": "Medium",
            },
            {
                "date": "2026-07-16 13:15:00",
                "country": "US",
                "currency": "USD",
                "event": "Industrial Production",
                "impact": "Low",
            },
            {
                "date": "2026-07-17 09:00:00",
                "country": "Germany",
                "currency": "EUR",
                "event": "ZEW Survey",
                "impact": "High",
            },
            {
                "date": "not-a-date",
                "country": "US",
                "currency": "USD",
                "event": "Broken Date",
                "impact": "High",
            },
        ]

    provider = FMPEconomicCalendar(api_key=None, horizon_days=14, row_fetcher=_rows)

    events = provider.macro_events(date(2026, 7, 3))

    assert calls == [(date(2026, 7, 3), date(2026, 7, 17))]
    assert events == (
        {
            "event_code": "cpi_yoy",
            "event_time": datetime(2026, 7, 10, 12, 30, tzinfo=timezone.utc),
            "title": "CPI (YoY)",
            "severity_hint": "high",
            "source": "fmp_economic_calendar",
        },
        {
            "event_code": "fomc_rate_decision",
            "event_time": datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc),
            "title": "FOMC Rate Decision",
            "severity_hint": "medium",
            "source": "fmp_economic_calendar",
        },
    )


def test_fmp_economic_calendar_memoizes_once_per_as_of_date():
    calls: list[tuple[date, date]] = []

    def _rows(start: date, end: date) -> list[dict[str, object]]:
        calls.append((start, end))
        return [
            {
                "date": f"{start.isoformat()} 12:30:00",
                "country": "US",
                "currency": "USD",
                "event": "Nonfarm Payrolls",
                "impact": "High",
            }
        ]

    provider = FMPEconomicCalendar(api_key=None, horizon_days=7, row_fetcher=_rows)

    first = provider.macro_events(date(2026, 7, 3))
    second = provider.macro_events(date(2026, 7, 3))
    third = provider.macro_events(date(2026, 7, 4))

    assert first == second
    assert third[0]["event_time"].date() == date(2026, 7, 4)
    assert calls == [
        (date(2026, 7, 3), date(2026, 7, 10)),
        (date(2026, 7, 4), date(2026, 7, 11)),
    ]


def test_fmp_economic_calendar_degrades_to_empty_without_key_or_on_fetch_error(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    assert FMPEconomicCalendar(api_key=None, row_fetcher=None).macro_events(date(2026, 7, 3)) == ()

    def _raise(start: date, end: date) -> list[dict[str, object]]:
        raise RuntimeError("provider unavailable")

    assert FMPEconomicCalendar(api_key=None, row_fetcher=_raise).macro_events(date(2026, 7, 3)) == ()


def test_fmp_economic_calendar_fetches_rows_from_http_client():
    requests: list[tuple[str, dict[str, str]]] = []

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, object]]:
            return [
                {
                    "date": "2026-07-10 12:30:00",
                    "country": "US",
                    "currency": "USD",
                    "event": "PPI",
                    "impact": "Medium",
                }
            ]

    class _Client:
        def get(self, url: str, *, params: dict[str, str]) -> _Response:
            requests.append((url, params))
            return _Response()

    events = FMPEconomicCalendar(api_key="key", client=_Client(), horizon_days=2).macro_events(
        date(2026, 7, 3)
    )

    assert requests == [
        (
            "https://financialmodelingprep.com/api/v3/economic_calendar",
            {"from": "2026-07-03", "to": "2026-07-05", "apikey": "key"},
        )
    ]
    assert events[0]["event_code"] == "ppi"
    assert events[0]["severity_hint"] == "medium"
