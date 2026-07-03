from __future__ import annotations

from datetime import date

from src.providers.market_data.nasdaq_earnings import NasdaqEarningsCalendar


def test_nasdaq_earnings_calendar_returns_nearest_future_date_and_caches_per_as_of():
    calls: list[date] = []

    def row_fetcher(day: date):
        calls.append(day)
        if day == date(2026, 6, 3):
            return [{"symbol": "MSFT"}, {"symbol": "AAPL"}]
        if day == date(2026, 6, 5):
            return [{"symbol": "AAPL"}]
        return []

    calendar = NasdaqEarningsCalendar(horizon_days=4, row_fetcher=row_fetcher)

    assert calendar.next_earnings_date("aapl", date(2026, 6, 1)) == date(2026, 6, 3)
    assert calendar.next_earnings_date("MSFT", date(2026, 6, 1)) == date(2026, 6, 3)
    assert calendar.next_earnings_date("UNKNOWN", date(2026, 6, 1)) is None
    assert calls == [
        date(2026, 6, 1),
        date(2026, 6, 2),
        date(2026, 6, 3),
        date(2026, 6, 4),
        date(2026, 6, 5),
    ]


def test_nasdaq_earnings_calendar_rebuilds_cache_for_new_as_of_date():
    calls: list[date] = []

    def row_fetcher(day: date):
        calls.append(day)
        return [{"symbol": "AAPL"}] if day.day in {3, 4} else []

    calendar = NasdaqEarningsCalendar(horizon_days=2, row_fetcher=row_fetcher)

    assert calendar.next_earnings_date("AAPL", date(2026, 6, 1)) == date(2026, 6, 3)
    assert calendar.next_earnings_date("AAPL", date(2026, 6, 2)) == date(2026, 6, 3)

    assert calls == [
        date(2026, 6, 1),
        date(2026, 6, 2),
        date(2026, 6, 3),
        date(2026, 6, 2),
        date(2026, 6, 3),
        date(2026, 6, 4),
    ]


def test_nasdaq_earnings_calendar_degrades_to_none_when_fetcher_raises():
    def row_fetcher(day: date):
        raise RuntimeError(f"blocked:{day.isoformat()}")

    calendar = NasdaqEarningsCalendar(horizon_days=2, row_fetcher=row_fetcher)

    assert calendar.next_earnings_date("AAPL", date(2026, 6, 1)) is None


def test_nasdaq_earnings_calendar_fetches_api_rows_with_browser_headers():
    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"data": {"rows": [{"symbol": "AAPL"}]}}

    class _Client:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def get(self, url: str, *, params: dict[str, str], headers: dict[str, str]):
            self.calls.append({"url": url, "params": params, "headers": headers})
            return _Response()

    client = _Client()
    calendar = NasdaqEarningsCalendar(horizon_days=0, client=client)

    assert calendar.next_earnings_date("AAPL", date(2026, 6, 1)) == date(2026, 6, 1)
    assert client.calls == [
        {
            "url": "https://api.nasdaq.com/api/calendar/earnings",
            "params": {"date": "2026-06-01"},
            "headers": NasdaqEarningsCalendar.HEADERS,
        }
    ]
