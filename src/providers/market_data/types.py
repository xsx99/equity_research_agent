"""Shared types and protocol for the market data subsystem."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional, Protocol, TypedDict


class MarketSnapshot(TypedDict):
    """Market data passed as part of a research input payload."""

    last_price: Optional[float]
    return_1d: Optional[float]
    return_5d: Optional[float]
    return_since_market_open: Optional[float]
    session_volume: Optional[int]
    avg_volume_20d: Optional[float]
    relative_volume: Optional[float]
    sector: Optional[str]
    company_name: Optional[str]
    earnings_in_days: Optional[int]
    pe_ratio: Optional[float]
    ps_ratio: Optional[float]
    short_interest_pct_float: Optional[float]
    technical_signals: "TechnicalSignals"


class MomentumSignals(TypedDict):
    """Momentum-focused technical indicators."""

    rsi_14: Optional[float]
    rsi_3: Optional[float]


class VolatilitySignals(TypedDict):
    """Volatility-focused technical indicators."""

    atr_14: Optional[float]
    yesterday_range: Optional[float]
    atr_multiple: Optional[float]


class TechnicalSignals(TypedDict):
    """Replayable technical signals stored in the research input."""

    momentum: MomentumSignals
    volatility: VolatilitySignals


class DailyBar(TypedDict):
    """Normalized daily OHLC subset used by the market snapshot helper."""

    date: date
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: float
    volume: Optional[int]


class UniverseAssetPayload(TypedDict):
    """Provider-neutral universe/asset row."""

    symbol: str
    company_name: Optional[str]
    asset_type: str
    exchange: Optional[str]
    sector: Optional[str]
    industry: Optional[str]
    price: Optional[float]
    avg_dollar_volume: Optional[float]


class MarketDataProvider(Protocol):
    """Contract for pluggable market data providers."""

    def fetch_daily_bars(self, ticker: str, lookback_days: int) -> list[DailyBar]:
        """Return daily bars in ascending time order."""

    def fetch_daily_closes(self, ticker: str, lookback_days: int) -> list[float]:
        """Return close prices in ascending time order."""

    def fetch_daily_closes_range(self, ticker: str, start_date: date, end_date: date) -> list[float]:
        """Return close prices in ascending time order for bars within [start_date, end_date]."""

    def fetch_daily_bar_on_date(self, ticker: str, trading_date: date) -> Optional[DailyBar]:
        """Return the daily OHLC bar for *trading_date* if available."""

    def fetch_price_at_or_before(self, ticker: str, as_of: datetime) -> Optional[float]:
        """Return the latest observed price at or before *as_of*."""

    def fetch_context(self, ticker: str) -> dict[str, Any]:
        """Return optional context fields such as sector and earnings distance."""


class UniverseDataProvider(Protocol):
    """Contract for market providers that can list tradable assets."""

    def fetch_universe_assets(self) -> list[UniverseAssetPayload]:
        """Return provider-neutral tradable asset rows."""
