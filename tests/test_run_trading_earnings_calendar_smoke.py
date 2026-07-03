from __future__ import annotations

from datetime import date

from scripts import run_trading_earnings_calendar_smoke


def test_run_trading_earnings_calendar_smoke_prints_nasdaq_result(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(run_trading_earnings_calendar_smoke, "load_dotenv", lambda: None)

    class _StubCalendar:
        def next_earnings_date(self, ticker: str, as_of: date):
            assert ticker == "MU"
            assert as_of == date(2026, 6, 21)
            return date(2026, 6, 25)

    monkeypatch.setattr(
        run_trading_earnings_calendar_smoke,
        "NasdaqEarningsCalendar",
        lambda horizon_days: _StubCalendar(),
    )

    exit_code = run_trading_earnings_calendar_smoke.main(["MU", "--as-of", "2026-06-21"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"ticker": "MU"' in captured.out
    assert '"earnings_in_days": 4' in captured.out
    assert '"earnings_date": "2026-06-25"' in captured.out
