"""Technical signal extraction from point-in-time market source rows."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from src.trading.signals.sources import SourceRecord


REQUIRED_TECHNICAL_FIELDS = (
    "return_1d",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_60d",
    "price_vs_sma_20",
    "price_vs_sma_50",
    "price_vs_sma_200",
    "trend_slope_20d",
    "rsi_2",
    "rsi_3",
    "rsi_14",
    "atr_pct",
    "realized_volatility_percentile",
    "drawdown_from_recent_high",
    "distance_from_52w_high",
    "relative_volume",
    "volume_acceleration",
    "dollar_volume",
    "premarket_gap_pct",
    "rs_vs_spy_1d",
    "rs_vs_qqq_1d",
)


@dataclass(frozen=True)
class TechnicalSignals:
    values: dict[str, Any]
    missing: tuple[str, ...]
    stale: tuple[str, ...] = ()


def compute_relative_strength(
    ticker_return: float | None,
    benchmark_return: float | None,
) -> float | None:
    if ticker_return is None or benchmark_return is None:
        return None
    return ticker_return - benchmark_return


def build_technical_signals(records: list[SourceRecord] | tuple[SourceRecord, ...]) -> TechnicalSignals:
    """Build the PR02 technical MVP signal family from latest available market row."""
    if not records:
        return TechnicalSignals(values={}, missing=("market_bars",))
    record = max(records, key=lambda item: item.available_for_decision_at)
    bars = list(record.payload.get("bars") or [])
    intraday_bars = list(record.payload.get("intraday_bars") or [])
    closes = [_as_float(bar.get("close")) for bar in bars if _as_float(bar.get("close")) is not None]
    volumes = [_as_float(bar.get("volume")) for bar in bars if _as_float(bar.get("volume")) is not None]
    latest_intraday_close = _latest_intraday_close(intraday_bars)
    latest_close = latest_intraday_close if latest_intraday_close is not None else (closes[-1] if closes else None)
    latest_volume = volumes[-1] if volumes else None
    return_1d = _return_over(closes, 1)
    vwap_fields = _intraday_vwap_fields(
        intraday_bars=intraday_bars,
        latest_price=latest_close,
        prior_close=closes[-1] if closes else None,
    )
    values: dict[str, Any] = {
        "last_price": latest_close,
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
        "dollar_volume": (
            latest_close * latest_volume
            if latest_close is not None and latest_volume is not None
            else None
        ),
        "premarket_gap_pct": record.payload.get("premarket_gap_pct"),
        **vwap_fields,
    }
    benchmark_returns = record.payload.get("benchmark_returns") or {}
    values["rs_vs_spy_1d"] = compute_relative_strength(return_1d, benchmark_returns.get("SPY"))
    values["rs_vs_qqq_1d"] = compute_relative_strength(return_1d, benchmark_returns.get("QQQ"))
    missing = tuple(key for key in REQUIRED_TECHNICAL_FIELDS if values.get(key) is None)
    return TechnicalSignals(values=values, missing=missing)


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _latest_intraday_close(bars: list[dict[str, Any]]) -> float | None:
    for bar in reversed(bars):
        close = _as_float(bar.get("close")) if isinstance(bar, dict) else None
        if close is not None:
            return close
    return None


def _intraday_vwap_fields(
    *,
    intraday_bars: list[dict[str, Any]],
    latest_price: float | None,
    prior_close: float | None,
) -> dict[str, float | None]:
    cumulative_notional = 0.0
    cumulative_volume = 0.0
    cumulative_vwaps: list[float] = []
    session_open: float | None = None

    for bar in intraday_bars:
        if not isinstance(bar, dict):
            continue
        high = _as_float(bar.get("high"))
        low = _as_float(bar.get("low"))
        close = _as_float(bar.get("close"))
        volume = _as_float(bar.get("volume"))
        if session_open is None:
            session_open = _as_float(bar.get("open"))
        if high is None or low is None or close is None or volume is None or volume <= 0:
            continue
        typical_price = (high + low + close) / 3
        cumulative_notional += typical_price * volume
        cumulative_volume += volume
        if cumulative_volume > 0:
            cumulative_vwaps.append(cumulative_notional / cumulative_volume)

    vwap_now = cumulative_vwaps[-1] if cumulative_vwaps else None
    return {
        "vwap_now": vwap_now,
        "price_vs_vwap_now": _distance(latest_price, vwap_now),
        "vwap_return_since_open": _distance(vwap_now, session_open),
        "vwap_return_since_last_close": _distance(vwap_now, prior_close),
        "vwap_ma_20": statistics.fmean(cumulative_vwaps[-20:]) if cumulative_vwaps else None,
    }


def _distance(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None or baseline == 0:
        return None
    return (value - baseline) / baseline


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
