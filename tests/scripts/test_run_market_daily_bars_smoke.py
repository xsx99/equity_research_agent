from __future__ import annotations

from datetime import datetime, timezone

from scripts.run_market_daily_bars_smoke import run_smoke


def test_market_daily_bars_smoke_runs_success_and_degraded_fixture_paths_without_io():
    result = run_smoke(
        as_of=datetime(2026, 10, 2, 20, 5, tzinfo=timezone.utc),
    )

    assert result["status"] == "passed"
    assert result["successful_run"]["tickers_succeeded"] == 4
    assert result["degraded_run"]["status"] == "degraded"
    assert result["degraded_run"]["rows_after_failure"] == 1
