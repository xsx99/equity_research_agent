from __future__ import annotations

from datetime import date

import scripts.run_fred_economic_calendar_smoke as smoke


def test_fred_calendar_smoke_skips_without_api_key(monkeypatch):
    monkeypatch.setattr(smoke.app_config, "FRED_API_KEY", None)

    payload = smoke.run_smoke(as_of=date(2026, 7, 3), horizon_days=14)

    assert payload == {
        "status": "skipped",
        "reason": "FRED_API_KEY not set",
        "as_of": "2026-07-03",
        "horizon_days": 14,
        "events": [],
    }


def test_fred_calendar_smoke_serializes_events(monkeypatch):
    monkeypatch.setattr(smoke.app_config, "FRED_API_KEY", "key")

    class _Provider:
        def __init__(self, *, api_key: str, horizon_days: int) -> None:
            assert api_key == "key"
            assert horizon_days == 14

        def macro_events(self, as_of: date):
            assert as_of == date(2026, 7, 3)
            return (
                {
                    "event_code": "consumer_price_index",
                    "event_time": smoke.datetime(2026, 7, 14, 13, 30, tzinfo=smoke.timezone.utc),
                    "title": "Consumer Price Index",
                    "severity_hint": "high",
                    "source": "fred_release_calendar",
                },
            )

    monkeypatch.setattr(smoke, "FREDEconomicCalendar", _Provider)

    payload = smoke.run_smoke(as_of=date(2026, 7, 3), horizon_days=14)

    assert payload["status"] == "ok"
    assert payload["event_count"] == 1
    assert payload["events"][0]["event_time"] == "2026-07-14T13:30:00+00:00"
