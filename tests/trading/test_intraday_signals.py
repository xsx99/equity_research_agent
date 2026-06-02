from __future__ import annotations

from datetime import datetime, timezone

from src.trading.intraday.signals import build_intraday_signal_snapshot
from src.trading.signals import SignalSnapshotResult


def _baseline_snapshot() -> SignalSnapshotResult:
    now = datetime(2026, 6, 2, 13, 30, tzinfo=timezone.utc)
    return SignalSnapshotResult(
        signal_snapshot_id="baseline-1",
        ticker="NVDA",
        snapshot_type="pre_open",
        decision_time=now,
        available_for_decision_at=now,
        max_input_available_for_decision_at=now,
        signal_json={
            "technical": {
                "last_price": 120.0,
                "relative_volume": 1.2,
                "rs_vs_spy_1d": 0.03,
            },
            "fundamental": {
                "market_cap_bucket": "mega",
            },
            "events_news": {
                "high_signal_news_count_24h": 0,
            },
        },
        source_freshness_json={
            "technical": "fresh",
            "fundamental": "fresh",
            "events_news": "fresh",
        },
        missing_signals_json=[],
        stale_signals_json=[],
        source_record_refs_json=[],
        source_available_times_json={},
        excluded_future_source_count=0,
        point_in_time_passed=True,
    )


def test_build_intraday_signal_snapshot_tracks_refresh_carry_forward_and_deltas():
    baseline = _baseline_snapshot()
    previous = build_intraday_signal_snapshot(
        intraday_signal_scan_id="scan-1",
        ticker="NVDA",
        decision_time=datetime(2026, 6, 2, 14, 30, tzinfo=timezone.utc),
        baseline_snapshot=baseline,
        previous_intraday_snapshot=None,
        refreshed_signals_json={
            "technical": {
                "last_price": 123.0,
                "relative_volume": 1.6,
            },
            "events_news": {
                "high_signal_news_count_24h": 1,
            },
        },
        source_freshness_json={
            "technical": "fresh",
            "fundamental": "not_required",
            "events_news": "fresh",
        },
    )

    current = build_intraday_signal_snapshot(
        intraday_signal_scan_id="scan-2",
        ticker="NVDA",
        decision_time=datetime(2026, 6, 2, 15, 30, tzinfo=timezone.utc),
        baseline_snapshot=baseline,
        previous_intraday_snapshot=previous,
        refreshed_signals_json={
            "technical": {
                "last_price": 125.0,
                "relative_volume": 1.9,
            },
            "events_news": {
                "high_signal_news_count_24h": 2,
            },
        },
        source_freshness_json={
            "technical": "fresh",
            "fundamental": "carried_forward_from_baseline",
            "events_news": "fresh",
        },
    )

    assert current.baseline_signal_snapshot_id == "baseline-1"
    assert current.previous_intraday_snapshot_id == previous.intraday_signal_snapshot_id
    assert current.refreshed_signals_json["technical"]["last_price"] == 125.0
    assert current.carried_forward_signals_json == {"fundamental": {"market_cap_bucket": "mega"}}
    assert current.delta_vs_baseline_json["technical"]["last_price"] == 5.0
    assert current.delta_vs_previous_json["technical"]["last_price"] == 2.0
    assert current.delta_vs_baseline_json["events_news"]["high_signal_news_count_24h"] == 2
    assert current.source_freshness_json["fundamental"] == "carried_forward_from_baseline"
