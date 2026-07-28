from datetime import date, datetime, timezone

import pytest

from src.trading.signals.sources import SourceRecord
from src.trading.signals.snapshots import SignalSnapshotResult, apply_universe_ranking_overlay
from src.trading.signals.technical import build_technical_signals, compute_relative_strength
from src.trading.ranking.records import UniverseRankingRecord


def test_ranking_overlay_keeps_one_day_diagnostics_and_marks_insufficient_score_missing():
    timestamp = datetime(2026, 7, 21, 13, 30, tzinfo=timezone.utc)
    snapshot = SignalSnapshotResult(
        signal_snapshot_id="snapshot", ticker="AAA", snapshot_type="pre_open", decision_time=timestamp,
        available_for_decision_at=timestamp, max_input_available_for_decision_at=timestamp,
        signal_json={"technical": {"rs_vs_spy_1d": 0.03}}, source_freshness_json={},
        missing_signals_json=[], stale_signals_json=[], source_record_refs_json=[],
        source_available_times_json={}, excluded_future_source_count=0, point_in_time_passed=True,
    )
    ranking = UniverseRankingRecord(
        universe_ranking_id="ranking", universe_ranking_run_id="run", ticker="AAA", decision_time=timestamp,
        status="insufficient_data", overall_rank=None, overall_percentile=None,
        relative_strength_score=None, data_confidence=0.2, peer_group_type="market", peer_group_id="market",
        peer_group_size=3, is_automatic_shortlist=False, forced_inclusion_reasons=("open_position",),
        raw_metrics_json={"return_20d": None}, normalized_metrics_json={}, positive_contributors_json=(),
        negative_contributors_json=(), missing_inputs=("valid_closes_61",), source_refs=("bars:AAA",),
        available_for_decision_at=timestamp,
    )

    result = apply_universe_ranking_overlay(snapshot, ranking)

    assert result.signal_json["technical"]["rs_vs_spy_1d"] == 0.03
    assert result.signal_json["technical"]["relative_strength_score"] is None
    assert result.signal_json["technical"]["relative_strength_forced_inclusion_reasons"] == ["open_position"]
    assert "technical.relative_strength_score" in result.missing_signals_json


def test_technical_signals_build_price_volume_and_relative_strength_fields():
    available_at = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    record = SourceRecord(
        ticker="AAPL",
        source_family="technical",
        source="fixture",
        source_table="market_bars",
        source_record_id="bars-1",
        event_time=available_at,
        published_at=available_at,
        ingested_at=available_at,
        available_for_decision_at=available_at,
        payload={
            "bars": [
                {"date": date(2026, 5, 27), "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1_000_000},
                {"date": date(2026, 5, 28), "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1_100_000},
                {"date": date(2026, 5, 29), "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 1_200_000},
                {"date": date(2026, 6, 1), "open": 102.0, "high": 106.0, "low": 101.0, "close": 105.0, "volume": 2_000_000},
            ],
            "benchmark_returns": {"SPY": 0.01, "QQQ": 0.02},
            "premarket_gap_pct": 0.015,
        },
    )

    signals = build_technical_signals([record])

    assert signals.values["last_price"] == pytest.approx(105.0)
    assert signals.values["return_1d"] == pytest.approx(3 / 102)
    assert signals.values["return_5d"] is None
    assert signals.values["rs_vs_spy_1d"] == pytest.approx((3 / 102) - 0.01)
    assert signals.values["rs_vs_qqq_1d"] == pytest.approx((3 / 102) - 0.02)
    assert signals.values["relative_volume"] == pytest.approx(2_000_000 / 1_100_000)
    assert signals.values["dollar_volume"] == pytest.approx(105.0 * 2_000_000)
    assert signals.values["premarket_gap_pct"] == pytest.approx(0.015)
    assert "return_5d" in signals.missing


def test_technical_signals_build_intraday_vwap_fields():
    available_at = datetime(2026, 7, 21, 17, 0, tzinfo=timezone.utc)
    record = SourceRecord(
        ticker="AAPL",
        source_family="technical",
        source="fixture",
        source_table="market_bars",
        source_record_id="bars-1",
        event_time=available_at,
        published_at=available_at,
        ingested_at=available_at,
        available_for_decision_at=available_at,
        payload={
            "bars": [
                {"date": date(2026, 7, 17), "open": 96.0, "high": 101.0, "low": 95.0, "close": 100.0, "volume": 1_000_000},
                {"date": date(2026, 7, 20), "open": 100.0, "high": 103.0, "low": 99.0, "close": 102.0, "volume": 1_100_000},
            ],
            "intraday_bars": [
                {"timestamp": "2026-07-21T13:30:00+00:00", "open": 103.0, "high": 104.0, "low": 102.0, "close": 103.0, "volume": 100},
                {"timestamp": "2026-07-21T13:31:00+00:00", "open": 103.0, "high": 106.0, "low": 104.0, "close": 105.0, "volume": 200},
                {"timestamp": "2026-07-21T13:32:00+00:00", "open": 105.0, "high": 107.0, "low": 105.0, "close": 106.0, "volume": 300},
            ],
        },
    )

    signals = build_technical_signals([record])

    first_vwap = 103.0
    second_vwap = ((103.0 * 100) + (105.0 * 200)) / 300
    final_vwap = ((103.0 * 100) + (105.0 * 200) + (106.0 * 300)) / 600
    assert signals.values["vwap_now"] == pytest.approx(final_vwap)
    assert signals.values["price_vs_vwap_now"] == pytest.approx((106.0 - final_vwap) / final_vwap)
    assert signals.values["vwap_return_since_open"] == pytest.approx((final_vwap - 103.0) / 103.0)
    assert signals.values["vwap_return_since_last_close"] == pytest.approx((final_vwap - 102.0) / 102.0)
    assert signals.values["vwap_ma_20"] == pytest.approx((first_vwap + second_vwap + final_vwap) / 3)


def test_compute_relative_strength_subtracts_benchmark_return_from_ticker_return():
    assert compute_relative_strength(0.12, 0.05) == pytest.approx(0.07)
