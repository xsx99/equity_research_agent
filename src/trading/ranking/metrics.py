"""Pure adjusted-bar normalization and raw relative-strength formulas."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from math import sqrt
from statistics import fmean, stdev
from typing import Iterable

from src.trading.ranking.records import AdjustedDailyBar, NormalizedBarSet, RawRankingMetrics


def normalize_adjusted_bars(
    bars: Iterable[AdjustedDailyBar],
    decision_time: datetime,
) -> NormalizedBarSet:
    """Filter bars by availability, sort by session, and reject duplicate sessions."""
    available = tuple(
        sorted(
            (bar for bar in bars if bar.available_for_decision_at <= decision_time),
            key=lambda bar: bar.session_date,
        )
    )
    duplicate_dates = sorted(
        session_date
        for session_date, count in Counter(bar.session_date for bar in available).items()
        if count > 1
    )
    invalid_reason = (
        f"duplicate_session_date:{duplicate_dates[0].isoformat()}" if duplicate_dates else None
    )
    source_refs = tuple(sorted({ref for bar in available for ref in bar.source_refs}))
    adjustment_sources = tuple(
        sorted({bar.adjustment_source for bar in available if bar.adjustment_source})
    )
    max_available = max(
        (bar.available_for_decision_at for bar in available),
        default=None,
    )
    return NormalizedBarSet(
        bars=available,
        invalid_reason=invalid_reason,
        source_refs=source_refs,
        adjustment_sources=adjustment_sources,
        max_available_for_decision_at=max_available,
    )


def build_raw_metrics(
    *,
    ticker: str,
    bars: Iterable[AdjustedDailyBar],
    spy_bars: Iterable[AdjustedDailyBar],
    decision_time: datetime,
) -> RawRankingMetrics:
    """Calculate v1 raw metrics from data available at ``decision_time``."""
    normalized = normalize_adjusted_bars(bars, decision_time)
    spy_normalized = normalize_adjusted_bars(spy_bars, decision_time)
    if normalized.invalid_reason is not None:
        return _invalid_metrics(ticker, normalized, spy_normalized, normalized.invalid_reason)

    closes = [float(bar.close) for bar in normalized.bars if _valid_close(bar.close)]
    volumes = [float(bar.volume) for bar in normalized.bars if _valid_volume(bar.volume)]
    spy_closes = [
        float(bar.close) for bar in spy_normalized.bars if _valid_close(bar.close)
    ]
    returns = {window: _simple_return(closes, window) for window in (1, 5, 20, 60)}
    spy_returns = {window: _simple_return(spy_closes, window) for window in (5, 20, 60)}
    daily_returns = _daily_returns(closes)

    missing: list[str] = []
    if len(closes) < 61:
        missing.append("valid_closes_61")
    if len(volumes) < 21:
        missing.append("valid_volumes_21")
    if spy_normalized.invalid_reason is not None:
        missing.append(f"spy_{spy_normalized.invalid_reason}")
    if len(spy_closes) < 61:
        missing.append("spy_valid_closes_61")
    if not normalized.bars or not all(bar.is_adjusted for bar in normalized.bars):
        missing.append("adjusted_bars")
    if not normalized.bars or not all(bar.split_adjusted for bar in normalized.bars):
        missing.append("split_adjusted_bars")
    spy_is_adjusted = bool(spy_normalized.bars) and all(
        bar.is_adjusted for bar in spy_normalized.bars
    )
    spy_is_split_adjusted = bool(spy_normalized.bars) and all(
        bar.split_adjusted for bar in spy_normalized.bars
    )
    if not spy_is_adjusted:
        missing.append("spy_adjusted_bars")
    if not spy_is_split_adjusted:
        missing.append("spy_split_adjusted_bars")

    for window, value in returns.items():
        if value is None:
            missing.append(f"return_{window}d")

    alphas: dict[int, float | None] = {}
    for window in (5, 20, 60):
        ticker_return = returns[window]
        spy_return = spy_returns[window]
        alphas[window] = (
            ticker_return - spy_return
            if ticker_return is not None
            and spy_return is not None
            and spy_normalized.invalid_reason is None
            and spy_is_adjusted
            and spy_is_split_adjusted
            else None
        )
        if alphas[window] is None:
            missing.append(f"alpha_vs_spy_{window}d")

    relative_volume, zero_volume_baseline = _relative_volume(volumes, 20)
    if relative_volume is None:
        missing.append(
            "relative_volume_20d_zero_baseline"
            if zero_volume_baseline
            else "relative_volume_20d"
        )

    realized_volatility = (
        stdev(daily_returns[-20:]) * sqrt(252) if len(daily_returns) >= 20 else None
    )
    if realized_volatility is None:
        missing.append("realized_volatility_20d")

    drawdown = closes[-1] / max(closes[-60:]) - 1 if len(closes) >= 60 else None
    if drawdown is None:
        missing.append("drawdown_60d")

    concentration = _positive_return_concentration(daily_returns, 20)
    if concentration is None:
        missing.append("one_day_concentration_20d")

    return RawRankingMetrics(
        ticker=ticker,
        return_1d=returns[1],
        return_5d=returns[5],
        return_20d=returns[20],
        return_60d=returns[60],
        alpha_vs_spy_5d=alphas[5],
        alpha_vs_spy_20d=alphas[20],
        alpha_vs_spy_60d=alphas[60],
        relative_volume_20d=relative_volume,
        realized_volatility_20d=realized_volatility,
        drawdown_60d=drawdown,
        one_day_concentration_20d=concentration,
        is_fully_eligible=not missing,
        missing_inputs=tuple(dict.fromkeys(missing)),
        **_provenance(normalized, spy_normalized),
    )


def _invalid_metrics(
    ticker: str,
    normalized: NormalizedBarSet,
    spy_normalized: NormalizedBarSet,
    invalid_reason: str,
) -> RawRankingMetrics:
    return RawRankingMetrics(
        ticker=ticker,
        return_1d=None,
        return_5d=None,
        return_20d=None,
        return_60d=None,
        alpha_vs_spy_5d=None,
        alpha_vs_spy_20d=None,
        alpha_vs_spy_60d=None,
        relative_volume_20d=None,
        realized_volatility_20d=None,
        drawdown_60d=None,
        one_day_concentration_20d=None,
        is_fully_eligible=False,
        missing_inputs=(invalid_reason,),
        **_provenance(normalized, spy_normalized),
    )


def _provenance(
    normalized: NormalizedBarSet,
    spy_normalized: NormalizedBarSet,
) -> dict[str, object]:
    all_input_bars = (*normalized.bars, *spy_normalized.bars)
    return {
        "bar_count": len(normalized.bars),
        "last_bar_date": normalized.bars[-1].session_date if normalized.bars else None,
        "all_bars_adjusted": bool(all_input_bars)
        and all(bar.is_adjusted for bar in all_input_bars),
        "all_bars_split_adjusted": bool(all_input_bars)
        and all(bar.split_adjusted for bar in all_input_bars),
        "adjustment_sources": tuple(
            sorted({*normalized.adjustment_sources, *spy_normalized.adjustment_sources})
        ),
        "source_refs": tuple(sorted({*normalized.source_refs, *spy_normalized.source_refs})),
        "max_available_for_decision_at": max(
            (
                available_at
                for available_at in (
                    normalized.max_available_for_decision_at,
                    spy_normalized.max_available_for_decision_at,
                )
                if available_at is not None
            ),
            default=None,
        ),
    }


def _simple_return(closes: list[float], sessions: int) -> float | None:
    if len(closes) <= sessions or closes[-sessions - 1] == 0:
        return None
    return closes[-1] / closes[-sessions - 1] - 1


def _daily_returns(closes: list[float]) -> list[float]:
    return [
        current / previous - 1
        for previous, current in zip(closes, closes[1:])
        if previous != 0
    ]


def _relative_volume(volumes: list[float], window: int) -> tuple[float | None, bool]:
    if len(volumes) <= window:
        return None, False
    baseline = fmean(volumes[-window - 1 : -1])
    if baseline == 0:
        return None, True
    return volumes[-1] / baseline, False


def _positive_return_concentration(
    daily_returns: list[float],
    window: int,
) -> float | None:
    if len(daily_returns) < window:
        return None
    recent = daily_returns[-window:]
    positive_sum = sum(max(value, 0.0) for value in recent)
    if positive_sum == 0:
        return 0.0
    return max(recent[-1], 0.0) / positive_sum


def _valid_close(value: float | None) -> bool:
    return value is not None and value > 0


def _valid_volume(value: float | None) -> bool:
    return value is not None and value >= 0
