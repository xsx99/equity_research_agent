from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.web.presenters.today_portfolio_analytics import build_portfolio_analytics


def test_build_portfolio_analytics_returns_none_when_history_has_no_equity():
    assert build_portfolio_analytics([]) is None
    assert build_portfolio_analytics([{"time": "2026-06-16T13:00:00Z", "day_pnl": 10.0}]) is None


def test_build_portfolio_analytics_handles_single_point_series():
    payload = build_portfolio_analytics(
        [
            {
                "time": datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc),
                "equity": 100.0,
                "day_pnl": 0.0,
            }
        ]
    )

    assert payload is not None
    assert payload["point_count"] == 1
    assert payload["equity_start"] == 100.0
    assert payload["equity_end"] == 100.0
    assert payload["metrics"]["total_return"] == 0.0
    assert payload["metrics"]["max_drawdown"] == 0.0
    assert payload["metrics"]["win_days"] == 0
    assert payload["metrics"]["loss_days"] == 0
    assert payload["metrics"]["profitable_days_pct"] == 0.0
    assert payload["metrics"]["daily_profit_factor"] is None
    assert len(payload["equity_points"].split()) == 1
    assert len(payload["daily_bars"]) == 1


def test_build_portfolio_analytics_computes_series_geometry_and_metrics():
    payload = build_portfolio_analytics(
        [
            {
                "time": datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc),
                "equity": 100.0,
                "day_pnl": 0.0,
            },
            {
                "time": datetime(2026, 6, 17, 13, 0, tzinfo=timezone.utc),
                "equity": 120.0,
                "day_pnl": 20.0,
            },
            {
                "time": datetime(2026, 6, 18, 13, 0, tzinfo=timezone.utc),
                "equity": 114.0,
                "day_pnl": -6.0,
            },
            {
                "time": datetime(2026, 6, 19, 13, 0, tzinfo=timezone.utc),
                "equity": 126.0,
                "day_pnl": 12.0,
            },
        ]
    )

    assert payload is not None
    assert payload["point_count"] == 4
    assert payload["equity_start"] == 100.0
    assert payload["equity_end"] == 126.0
    assert payload["equity_min"] == 100.0
    assert payload["equity_max"] == 126.0
    assert len(payload["equity_points"].split()) == 4
    assert len(payload["daily_bars"]) == 4
    assert payload["metrics"]["total_return"] == pytest.approx(0.26)
    assert payload["metrics"]["max_drawdown"] == pytest.approx(0.05)
    assert payload["metrics"]["win_days"] == 2
    assert payload["metrics"]["loss_days"] == 1
    assert payload["metrics"]["profitable_days_pct"] == pytest.approx(2 / 3)
    assert payload["metrics"]["best_day"] == pytest.approx(20.0)
    assert payload["metrics"]["worst_day"] == pytest.approx(-6.0)
    assert payload["metrics"]["avg_day_pnl"] == pytest.approx(26.0 / 3.0)
    assert payload["metrics"]["daily_profit_factor"] == pytest.approx(32.0 / 6.0)
