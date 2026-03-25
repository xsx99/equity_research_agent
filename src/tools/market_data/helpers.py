"""Internal computation helpers for market data (returns, RSI, ATR, etc.)."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from src.tools.market_data.types import DailyBar, MarketSnapshot, TechnicalSignals

MARKET_TIMEZONE = ZoneInfo("America/New_York")
REGULAR_MARKET_OPEN = time(9, 30)
REGULAR_MARKET_CLOSE = time(16, 0)


def _empty_snapshot() -> MarketSnapshot:
    return {
        "last_price": None,
        "return_1d": None,
        "return_5d": None,
        "return_since_market_open": None,
        "session_volume": None,
        "avg_volume_20d": None,
        "relative_volume": None,
        "sector": None,
        "company_name": None,
        "earnings_in_days": None,
        "pe_ratio": None,
        "ps_ratio": None,
        "short_interest_pct_float": None,
        "technical_signals": _empty_technical_signals(),
    }


def _empty_technical_signals() -> TechnicalSignals:
    return {
        "momentum": {
            "rsi_14": None,
            "rsi_3": None,
        },
        "volatility": {
            "atr_14": None,
            "yesterday_range": None,
            "atr_multiple": None,
        },
    }


def _compute_return(
    last_price: Optional[float], anchor_price: Optional[float]
) -> Optional[float]:
    if last_price is None or anchor_price in (None, 0):
        return None
    return (last_price / anchor_price) - 1


def _to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_alpaca_data_base_url(data_base_url: Optional[str], default_url: str) -> str:
    raw_url = (data_base_url or default_url).rstrip("/")
    normalized_url = raw_url.removesuffix("/v2")
    if normalized_url in {
        "https://api.alpaca.markets",
        "https://paper-api.alpaca.markets",
    }:
        return default_url
    return normalized_url


def _parse_bar_date(value: Any) -> Optional[date]:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None


def _parse_bar_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized_now(now: Optional[datetime]) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _is_regular_market_session(now: datetime) -> bool:
    eastern_now = now.astimezone(MARKET_TIMEZONE)
    current_time = eastern_now.time()
    return (
        eastern_now.weekday() < 5
        and REGULAR_MARKET_OPEN <= current_time < REGULAR_MARKET_CLOSE
    )


def _compute_return_since_market_open(
    last_bar: Optional[DailyBar],
    now: datetime,
) -> Optional[float]:
    if last_bar is None or not _is_regular_market_session(now):
        return None
    if last_bar["date"] != now.astimezone(MARKET_TIMEZONE).date():
        return None
    return _compute_return(last_bar.get("close"), last_bar.get("open"))


def _compute_rsi(closes: list[float], period: int) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    window = closes[-(period + 1):]
    gains = 0.0
    losses = 0.0
    for previous_close, current_close in zip(window, window[1:]):
        change = current_close - previous_close
        if change > 0:
            gains += change
        elif change < 0:
            losses -= change

    average_gain = gains / period
    average_loss = losses / period
    if average_gain == 0 and average_loss == 0:
        return 50.0
    if average_loss == 0:
        return 100.0
    if average_gain == 0:
        return 0.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _completed_bars_for_volatility(
    daily_bars: list[DailyBar],
    now: datetime,
) -> list[DailyBar]:
    if not daily_bars:
        return []
    last_bar = daily_bars[-1]
    if (
        _is_regular_market_session(now)
        and last_bar["date"] == now.astimezone(MARKET_TIMEZONE).date()
    ):
        return daily_bars[:-1]
    return daily_bars


def _compute_atr_14(completed_bars: list[DailyBar]) -> Optional[float]:
    period = 14
    if len(completed_bars) < period:
        return None
    start_index = len(completed_bars) - period
    true_ranges: list[float] = []

    for index in range(start_index, len(completed_bars)):
        bar = completed_bars[index]
        high = _to_float_or_none(bar.get("high"))
        low = _to_float_or_none(bar.get("low"))
        if high is None or low is None:
            return None
        components = [high - low]
        if index > 0:
            previous_close = _to_float_or_none(completed_bars[index - 1].get("close"))
            if previous_close is not None:
                components.extend([abs(high - previous_close), abs(low - previous_close)])
        true_ranges.append(max(components))

    if len(true_ranges) < period:
        return None
    return sum(true_ranges) / period


def _compute_technical_signals(
    daily_bars: list[DailyBar],
    now: datetime,
) -> TechnicalSignals:
    technical_signals = _empty_technical_signals()
    closes = [
        close
        for close in (_to_float_or_none(bar.get("close")) for bar in daily_bars)
        if close is not None
    ]
    technical_signals["momentum"]["rsi_14"] = _compute_rsi(closes, 14)
    technical_signals["momentum"]["rsi_3"] = _compute_rsi(closes, 3)

    completed_bars = _completed_bars_for_volatility(daily_bars, now)
    atr_14 = _compute_atr_14(completed_bars)
    technical_signals["volatility"]["atr_14"] = atr_14

    if completed_bars:
        reference_bar = completed_bars[-1]
        high = _to_float_or_none(reference_bar.get("high"))
        low = _to_float_or_none(reference_bar.get("low"))
        if high is not None and low is not None:
            yesterday_range = high - low
            technical_signals["volatility"]["yesterday_range"] = yesterday_range
            if atr_14 not in (None, 0):
                technical_signals["volatility"]["atr_multiple"] = yesterday_range / atr_14

    return technical_signals
