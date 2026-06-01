"""Deterministic point-in-time signal snapshot builders."""
from __future__ import annotations

import math
import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from src.trading.event_news_signals import build_event_news_signals
from src.trading.fundamental_signals import build_fundamental_signals
from src.trading.point_in_time import filter_point_in_time_records
from src.trading.signal_sources import SourceRecord


@dataclass(frozen=True)
class SignalSnapshotResult:
    """In-memory pre-open signal snapshot artifact."""

    signal_snapshot_id: str
    ticker: str
    snapshot_type: str
    decision_time: datetime
    available_for_decision_at: datetime
    max_input_available_for_decision_at: datetime | None
    signal_json: dict[str, dict[str, Any]]
    source_freshness_json: dict[str, str]
    missing_signals_json: list[str]
    stale_signals_json: list[str]
    source_record_refs_json: list[dict[str, str]]
    source_available_times_json: dict[str, str]
    excluded_future_source_count: int
    point_in_time_passed: bool
    selection_source: str = "scanner"
    manual_request_id: str | None = None


def compute_relative_strength(
    ticker_return: float | None,
    benchmark_return: float | None,
) -> float | None:
    if ticker_return is None or benchmark_return is None:
        return None
    return ticker_return - benchmark_return


def build_signal_snapshot(
    *,
    ticker: str,
    decision_time: datetime,
    source_records: Iterable[SourceRecord],
    snapshot_type: str,
    selection_source: str = "scanner",
    manual_request_id: str | None = None,
) -> SignalSnapshotResult:
    """Build a replayable PR02 signal snapshot from PIT-filtered source rows."""
    audit = filter_point_in_time_records(tuple(source_records), decision_time)
    records_by_family = _group_records(audit.records)
    technical = _build_technical_signals(records_by_family.get("technical", ()))
    fundamental = build_fundamental_signals(records_by_family.get("fundamental", ()))
    events_news = build_event_news_signals(
        records_by_family.get("events_news", ()),
        decision_time=decision_time,
    )
    missing = [
        *_missing_with_prefix("technical", technical["missing"]),
        *_missing_with_prefix("fundamental", fundamental.missing),
        *_missing_with_prefix("events_news", events_news.missing),
        "option_chain_availability",
        "full_sec_insider_interpretation",
        "full_transcript_interpretation",
        "macro_sector_readthrough",
    ]
    source_freshness = {
        family: ("fresh" if family in records_by_family else "missing")
        for family in ("technical", "fundamental", "events_news")
    }
    available_for_decision_at = audit.max_input_available_for_decision_at or decision_time
    return SignalSnapshotResult(
        signal_snapshot_id=str(uuid.uuid4()),
        ticker=ticker.strip().upper(),
        snapshot_type=snapshot_type,
        decision_time=decision_time,
        available_for_decision_at=available_for_decision_at,
        max_input_available_for_decision_at=audit.max_input_available_for_decision_at,
        signal_json={
            "technical": technical["values"],
            "fundamental": fundamental.values,
            "events_news": events_news.values,
        },
        source_freshness_json=source_freshness,
        missing_signals_json=missing,
        stale_signals_json=[],
        source_record_refs_json=list(audit.source_record_refs),
        source_available_times_json=audit.source_available_times,
        excluded_future_source_count=audit.excluded_future_source_count,
        point_in_time_passed=audit.point_in_time_passed,
        selection_source=selection_source,
        manual_request_id=manual_request_id,
    )


def _build_technical_signals(records: tuple[SourceRecord, ...]) -> dict[str, Any]:
    if not records:
        return {"values": {}, "missing": ("market_bars",)}
    record = max(records, key=lambda item: item.available_for_decision_at)
    bars = list(record.payload.get("bars") or [])
    closes = [_as_float(bar.get("close")) for bar in bars if _as_float(bar.get("close")) is not None]
    volumes = [_as_float(bar.get("volume")) for bar in bars if _as_float(bar.get("volume")) is not None]
    latest_close = closes[-1] if closes else None
    latest_volume = volumes[-1] if volumes else None
    return_1d = _return_over(closes, 1)
    values: dict[str, Any] = {
        "return_1d": return_1d,
        "return_5d": _return_over(closes, 5),
        "return_10d": _return_over(closes, 10),
        "return_20d": _return_over(closes, 20),
        "return_60d": _return_over(closes, 60),
        "price_vs_sma_20": _sma_distance(latest_close, closes, 20),
        "price_vs_sma_50": _sma_distance(latest_close, closes, 50),
        "price_vs_sma_200": _sma_distance(latest_close, closes, 200),
        "trend_slope_20d": _trend_slope(closes, 20),
        "rsi_2": _rsi(closes, 2),
        "rsi_3": _rsi(closes, 3),
        "rsi_14": _rsi(closes, 14),
        "atr_pct": _atr_pct(bars, latest_close, 14),
        "realized_volatility_percentile": _realized_volatility_percentile(closes),
        "drawdown_from_recent_high": _drawdown_from_high(closes, 60),
        "distance_from_52w_high": _drawdown_from_high(closes, 252),
        "relative_volume": _relative_volume(volumes, 20),
        "volume_acceleration": _volume_acceleration(volumes),
        "dollar_volume": latest_close * latest_volume if latest_close is not None and latest_volume is not None else None,
        "premarket_gap_pct": record.payload.get("premarket_gap_pct"),
    }
    benchmark_returns = record.payload.get("benchmark_returns") or {}
    values["rs_vs_spy_1d"] = compute_relative_strength(return_1d, benchmark_returns.get("SPY"))
    values["rs_vs_qqq_1d"] = compute_relative_strength(return_1d, benchmark_returns.get("QQQ"))
    missing = tuple(key for key, value in values.items() if value is None)
    return {"values": values, "missing": missing}


def _group_records(records: tuple[SourceRecord, ...]) -> dict[str, tuple[SourceRecord, ...]]:
    grouped: dict[str, list[SourceRecord]] = {}
    for record in records:
        grouped.setdefault(record.source_family, []).append(record)
    return {family: tuple(items) for family, items in grouped.items()}


def _missing_with_prefix(prefix: str, fields: Iterable[str]) -> list[str]:
    return [f"{prefix}.{field}" for field in fields]


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _return_over(closes: list[float], lookback: int) -> float | None:
    if len(closes) <= lookback:
        return None
    start = closes[-lookback - 1]
    if start == 0:
        return None
    return (closes[-1] - start) / start


def _sma_distance(latest_close: float | None, closes: list[float], window: int) -> float | None:
    if latest_close is None or len(closes) < window:
        return None
    sma = statistics.fmean(closes[-window:])
    if sma == 0:
        return None
    return (latest_close - sma) / sma


def _trend_slope(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    first = closes[-window]
    if first == 0:
        return None
    return (closes[-1] - first) / first / window


def _rsi(closes: list[float], period: int) -> float | None:
    if len(closes) <= period:
        return None
    deltas = [closes[index] - closes[index - 1] for index in range(len(closes) - period, len(closes))]
    gains = [delta for delta in deltas if delta > 0]
    losses = [-delta for delta in deltas if delta < 0]
    average_gain = statistics.fmean(gains) if gains else 0.0
    average_loss = statistics.fmean(losses) if losses else 0.0
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    rs = average_gain / average_loss
    return 100 - (100 / (1 + rs))


def _atr_pct(bars: list[dict[str, Any]], latest_close: float | None, window: int) -> float | None:
    if latest_close is None or latest_close == 0 or len(bars) < window:
        return None
    ranges: list[float] = []
    for bar in bars[-window:]:
        high = _as_float(bar.get("high"))
        low = _as_float(bar.get("low"))
        if high is not None and low is not None:
            ranges.append(high - low)
    if not ranges:
        return None
    return statistics.fmean(ranges) / latest_close


def _realized_volatility_percentile(closes: list[float]) -> float | None:
    if len(closes) < 22:
        return None
    returns = [
        (closes[index] - closes[index - 1]) / closes[index - 1]
        for index in range(1, len(closes))
        if closes[index - 1] != 0
    ]
    if len(returns) < 21:
        return None
    latest_vol = statistics.pstdev(returns[-20:])
    historical = [
        statistics.pstdev(returns[index - 20:index])
        for index in range(20, len(returns) + 1)
    ]
    if not historical:
        return None
    rank = sum(1 for value in historical if value <= latest_vol)
    return rank / len(historical)


def _drawdown_from_high(closes: list[float], window: int) -> float | None:
    if not closes:
        return None
    subset = closes[-window:]
    high = max(subset)
    if high == 0:
        return None
    return (closes[-1] - high) / high


def _relative_volume(volumes: list[float], window: int) -> float | None:
    if len(volumes) <= 1:
        return None
    baseline = volumes[-window - 1:-1] if len(volumes) > window else volumes[:-1]
    if not baseline:
        return None
    average = statistics.fmean(baseline)
    if average == 0:
        return None
    return volumes[-1] / average


def _volume_acceleration(volumes: list[float]) -> float | None:
    if len(volumes) < 3:
        return None
    previous = statistics.fmean(volumes[-3:-1])
    if previous == 0:
        return None
    return (volumes[-1] - previous) / previous
