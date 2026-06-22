from __future__ import annotations

from datetime import date

from scripts import run_trading_earnings_calendar_smoke


def test_run_trading_earnings_calendar_smoke_exits_non_zero_without_finnhub_key(
    monkeypatch,
    capsys,
):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setattr(run_trading_earnings_calendar_smoke, "load_dotenv", lambda: None)

    exit_code = run_trading_earnings_calendar_smoke.main([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "FINNHUB_API_KEY not set" in captured.err
    assert "earnings events cannot be generated" in captured.err


def test_run_trading_earnings_calendar_smoke_prints_finnhub_result(
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    monkeypatch.setattr(run_trading_earnings_calendar_smoke, "load_dotenv", lambda: None)

    class _StubProvider:
        def __init__(self) -> None:
            self.closed = False

        def _fetch_earnings_in_days_from_finnhub(self, ticker: str):
            assert ticker == "MU"
            return {"earnings_in_days": 4, "earnings_date": date(2026, 6, 25)}

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(
        run_trading_earnings_calendar_smoke,
        "AlpacaMarketDataProvider",
        _StubProvider,
    )

    exit_code = run_trading_earnings_calendar_smoke.main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"ticker": "MU"' in captured.out
    assert '"earnings_in_days": 4' in captured.out
    assert '"earnings_date": "2026-06-25"' in captured.out
