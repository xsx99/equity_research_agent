"""Market data providers and tool for the research pipeline."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import os
from typing import Any, Optional, Protocol, TypedDict
from zoneinfo import ZoneInfo

import httpx

from src.core.logging import get_logger
from src.tools.base import BaseTool, ToolError
from src.tools.context import ToolContext

logger = get_logger(__name__)
DEFAULT_ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"
MARKET_TIMEZONE = ZoneInfo("America/New_York")
REGULAR_MARKET_OPEN = time(9, 30)
REGULAR_MARKET_CLOSE = time(16, 0)


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


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


def _compute_return(
    last_price: Optional[float], anchor_price: Optional[float]
) -> Optional[float]:
    if last_price is None or anchor_price in (None, 0):
        return None
    return (last_price / anchor_price) - 1


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


def _resolve_alpaca_data_base_url(data_base_url: Optional[str]) -> str:
    raw_url = (
        data_base_url or os.getenv("ALPACA_DATA_BASE_URL") or DEFAULT_ALPACA_DATA_BASE_URL
    ).rstrip("/")
    normalized_url = raw_url.removesuffix("/v2")
    if normalized_url in {
        "https://api.alpaca.markets",
        "https://paper-api.alpaca.markets",
    }:
        return DEFAULT_ALPACA_DATA_BASE_URL
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


# ---------------------------------------------------------------------------
# Alpaca + Finnhub provider
# ---------------------------------------------------------------------------


class AlpacaMarketDataProvider:
    """Market data provider backed by Alpaca (with optional Finnhub enrichment)."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        data_base_url: Optional[str] = None,
        finnhub_api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = (
            secret_key or os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")
        )
        self.data_base_url = _resolve_alpaca_data_base_url(data_base_url)
        self.finnhub_api_key = finnhub_api_key or os.getenv("FINNHUB_API_KEY")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def _auth_headers(self) -> dict[str, str]:
        if not self.api_key or not self.secret_key:
            raise RuntimeError("missing_alpaca_credentials")
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

    def fetch_daily_bars(self, ticker: str, lookback_days: int) -> list[DailyBar]:
        symbol = ticker.upper()
        end = datetime.now(timezone.utc).replace(microsecond=0)
        start = end - timedelta(days=max(lookback_days * 3, 10))
        response = self._client.get(
            f"{self.data_base_url}/v2/stocks/bars",
            params={
                "symbols": symbol,
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": max(lookback_days, 2),
                "sort": "desc",
                "adjustment": "split",
                "feed": "iex",
            },
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()

        bars_payload = payload.get("bars", {})
        if isinstance(bars_payload, dict):
            bars = bars_payload.get(symbol, [])
        elif isinstance(bars_payload, list):
            bars = bars_payload
        else:
            bars = []

        if not bars:
            raise ValueError(f"no_daily_bars_for_{symbol}")

        bars = sorted(bars, key=lambda item: str(item.get("t", "")))
        daily_bars: list[DailyBar] = []
        for item in bars:
            close_raw = item.get("c")
            bar_date = _parse_bar_date(item.get("t"))
            if close_raw is None or bar_date is None:
                continue
            open_raw = item.get("o")
            high_raw = item.get("h")
            low_raw = item.get("l")
            volume_raw = item.get("v")
            daily_bars.append(
                {
                    "date": bar_date,
                    "open": float(open_raw) if open_raw is not None else None,
                    "high": float(high_raw) if high_raw is not None else None,
                    "low": float(low_raw) if low_raw is not None else None,
                    "close": float(close_raw),
                    "volume": _to_int_or_none(volume_raw),
                }
            )

        if not daily_bars:
            raise ValueError(f"no_close_prices_for_{symbol}")
        return daily_bars

    def fetch_daily_closes(self, ticker: str, lookback_days: int) -> list[float]:
        return [bar["close"] for bar in self.fetch_daily_bars(ticker, lookback_days)]

    def fetch_daily_closes_range(self, ticker: str, start_date: date, end_date: date) -> list[float]:
        """Return close prices in ascending time order for bars within [start_date, end_date].

        Returns an empty list if no bars are available in the range (not an error).
        Callers should handle the empty case explicitly.
        """
        symbol = ticker.upper()
        response = self._client.get(
            f"{self.data_base_url}/v2/stocks/bars",
            params={
                "symbols": symbol,
                "timeframe": "1Day",
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "sort": "asc",
                "adjustment": "split",
                "feed": "iex",
            },
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        bars_payload = payload.get("bars", {})
        if isinstance(bars_payload, dict):
            bars = bars_payload.get(symbol, [])
        elif isinstance(bars_payload, list):
            bars = bars_payload
        else:
            bars = []
        bars = sorted(bars, key=lambda item: str(item.get("t", "")))
        return [float(item["c"]) for item in bars if item.get("c") is not None]

    def fetch_daily_bar_on_date(self, ticker: str, trading_date: date) -> Optional[DailyBar]:
        symbol = ticker.upper()
        response = self._client.get(
            f"{self.data_base_url}/v2/stocks/bars",
            params={
                "symbols": symbol,
                "timeframe": "1Day",
                "start": trading_date.isoformat(),
                "end": trading_date.isoformat(),
                "sort": "asc",
                "adjustment": "split",
                "feed": "iex",
            },
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        bars_payload = payload.get("bars", {})
        if isinstance(bars_payload, dict):
            bars = bars_payload.get(symbol, [])
        elif isinstance(bars_payload, list):
            bars = bars_payload
        else:
            bars = []
        for item in sorted(bars, key=lambda bar: str(bar.get("t", ""))):
            close_raw = item.get("c")
            bar_date = _parse_bar_date(item.get("t"))
            if close_raw is None or bar_date != trading_date:
                continue
            open_raw = item.get("o")
            high_raw = item.get("h")
            low_raw = item.get("l")
            return {
                "date": bar_date,
                "open": float(open_raw) if open_raw is not None else None,
                "high": float(high_raw) if high_raw is not None else None,
                "low": float(low_raw) if low_raw is not None else None,
                "close": float(close_raw),
                "volume": _to_int_or_none(item.get("v")),
            }
        return None

    def fetch_price_at_or_before(self, ticker: str, as_of: datetime) -> Optional[float]:
        symbol = ticker.upper()
        cutoff = _normalized_now(as_of)
        session_open = datetime.combine(
            cutoff.astimezone(MARKET_TIMEZONE).date(),
            REGULAR_MARKET_OPEN,
            tzinfo=MARKET_TIMEZONE,
        ).astimezone(timezone.utc)
        response = self._client.get(
            f"{self.data_base_url}/v2/stocks/bars",
            params={
                "symbols": symbol,
                "timeframe": "1Min",
                "start": session_open.isoformat(),
                "end": cutoff.isoformat(),
                "sort": "asc",
                "adjustment": "split",
                "feed": "iex",
            },
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        bars_payload = payload.get("bars", {})
        if isinstance(bars_payload, dict):
            bars = bars_payload.get(symbol, [])
        elif isinstance(bars_payload, list):
            bars = bars_payload
        else:
            bars = []

        latest_price: Optional[float] = None
        for item in sorted(bars, key=lambda bar: str(bar.get("t", ""))):
            bar_time = _parse_bar_timestamp(item.get("t"))
            close_raw = item.get("c")
            if bar_time is None or close_raw is None or bar_time > cutoff:
                continue
            latest_price = float(close_raw)
        return latest_price

    def fetch_context(self, ticker: str) -> dict[str, Any]:
        sector: Optional[str] = None
        company_name: Optional[str] = None
        metrics: dict[str, Any] = {}
        if self.finnhub_api_key:
            profile = self._fetch_profile_from_finnhub(ticker)
            sector = self._extract_sector_from_profile(profile)
            raw_name = profile.get("name")
            if isinstance(raw_name, str) and raw_name.strip():
                company_name = raw_name.strip()
            metrics = self._fetch_metrics_from_finnhub(ticker)
        return {
            "sector": sector,
            "company_name": company_name,
            "earnings_in_days": self._fetch_earnings_in_days_from_finnhub(ticker),
            "pe_ratio": self._extract_metric_value(
                metrics,
                "peBasicExclExtraTTM",
                "peTTM",
                "peNormalizedAnnual",
            ),
            "ps_ratio": self._extract_metric_value(
                metrics,
                "psTTM",
                "psAnnual",
                "priceToSalesAnnual",
            ),
            "short_interest_pct_float": self._extract_metric_value(
                metrics,
                "shortPercentOfFloat",
                "shortInterestPercent",
                "shortRatio",
            ),
        }

    def _fetch_profile_from_finnhub(self, ticker: str) -> dict[str, Any]:
        if not self.finnhub_api_key:
            return {}
        response = self._client.get(
            "https://finnhub.io/api/v1/stock/profile2",
            params={"symbol": ticker.upper(), "token": self.finnhub_api_key},
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _fetch_sector_from_finnhub(self, ticker: str) -> Optional[str]:
        """Compatibility helper for smoke checks."""
        return self._extract_sector_from_profile(self._fetch_profile_from_finnhub(ticker))

    @staticmethod
    def _extract_sector_from_profile(profile: dict[str, Any]) -> Optional[str]:
        raw_sector = profile.get("finnhubIndustry")
        if isinstance(raw_sector, str) and raw_sector.strip():
            return raw_sector.strip()
        return None

    def _fetch_metrics_from_finnhub(self, ticker: str) -> dict[str, Any]:
        if not self.finnhub_api_key:
            return {}
        response = self._client.get(
            "https://finnhub.io/api/v1/stock/metric",
            params={"symbol": ticker.upper(), "metric": "all", "token": self.finnhub_api_key},
        )
        response.raise_for_status()
        payload = response.json()
        metrics = payload.get("metric") if isinstance(payload, dict) else None
        return metrics if isinstance(metrics, dict) else {}

    @staticmethod
    def _extract_metric_value(metrics: dict[str, Any], *keys: str) -> Optional[float]:
        for key in keys:
            value = _to_float_or_none(metrics.get(key))
            if value is not None:
                return value
        return None

    def _fetch_earnings_in_days_from_finnhub(self, ticker: str) -> Optional[int]:
        if not self.finnhub_api_key:
            return None
        today = datetime.now(timezone.utc).date()
        response = self._client.get(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={
                "symbol": ticker.upper(),
                "from": today.isoformat(),
                "to": (today + timedelta(days=45)).isoformat(),
                "token": self.finnhub_api_key,
            },
        )
        response.raise_for_status()
        payload = response.json()
        events = payload.get("earningsCalendar", [])
        if not isinstance(events, list):
            return None

        nearest_delta: Optional[int] = None
        for event in events:
            if not isinstance(event, dict):
                continue
            event_date_raw = event.get("date")
            if not isinstance(event_date_raw, str):
                continue
            try:
                event_date = datetime.fromisoformat(event_date_raw).date()
            except ValueError:
                continue
            delta = (event_date - today).days
            if delta < 0:
                continue
            if nearest_delta is None or delta < nearest_delta:
                nearest_delta = delta
        return nearest_delta

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


# ---------------------------------------------------------------------------
# get_market_snapshot helper
# ---------------------------------------------------------------------------


def get_market_snapshot(
    ticker: str,
    provider: Optional[MarketDataProvider] = None,
    now: Optional[datetime] = None,
) -> MarketSnapshot:
    """Fetch a market snapshot with resilient fallback on provider errors."""
    created_default = provider is None
    provider_instance = provider or AlpacaMarketDataProvider()
    snapshot = _empty_snapshot()
    current_time = _normalized_now(now)

    try:
        if hasattr(provider_instance, "fetch_daily_bars"):
            daily_bars = provider_instance.fetch_daily_bars(ticker, lookback_days=25)
            closes = [bar["close"] for bar in daily_bars]
        else:
            closes = provider_instance.fetch_daily_closes(ticker, lookback_days=6)
            daily_bars = [
                {"date": date.min, "open": None, "close": close}
                for close in closes
            ]

        last_bar = daily_bars[-1] if daily_bars else None
        last_price = closes[-1] if closes else None
        one_day_anchor = closes[-2] if len(closes) >= 2 else None
        five_day_anchor = closes[-6] if len(closes) >= 6 else None

        snapshot["last_price"] = last_price
        snapshot["return_1d"] = _compute_return(last_price, one_day_anchor)
        snapshot["return_5d"] = _compute_return(last_price, five_day_anchor)
        snapshot["return_since_market_open"] = _compute_return_since_market_open(
            last_bar, current_time
        )
        session_volume = _to_int_or_none(last_bar.get("volume")) if last_bar else None
        prior_volumes = [
            volume
            for volume in (
                _to_float_or_none(bar.get("volume")) for bar in daily_bars[:-1][-20:]
            )
            if volume is not None
        ]
        avg_volume_20d = (
            sum(prior_volumes) / len(prior_volumes) if prior_volumes else None
        )
        snapshot["session_volume"] = session_volume
        snapshot["avg_volume_20d"] = avg_volume_20d
        if session_volume is None or avg_volume_20d in (None, 0):
            snapshot["relative_volume"] = None
        else:
            snapshot["relative_volume"] = float(session_volume) / avg_volume_20d
        snapshot["technical_signals"] = _compute_technical_signals(
            daily_bars,
            current_time,
        )

        try:
            context = provider_instance.fetch_context(ticker)
        except Exception as exc:
            logger.warning("market_context_fetch_failed", ticker=ticker, error=str(exc))
            context = {}
        if not isinstance(context, dict):
            context = {}

        snapshot["sector"] = context.get("sector")
        snapshot["company_name"] = context.get("company_name")
        snapshot["earnings_in_days"] = _to_int_or_none(context.get("earnings_in_days"))
        snapshot["pe_ratio"] = _to_float_or_none(context.get("pe_ratio"))
        snapshot["ps_ratio"] = _to_float_or_none(context.get("ps_ratio"))
        snapshot["short_interest_pct_float"] = _to_float_or_none(
            context.get("short_interest_pct_float")
        )
        return snapshot
    except Exception as exc:
        logger.error("market_snapshot_failed", ticker=ticker, error=str(exc), exc_info=True)
        return snapshot
    finally:
        if created_default and hasattr(provider_instance, "close"):
            try:
                provider_instance.close()  # type: ignore[attr-defined]
            except Exception:
                logger.warning("market_provider_close_failed", ticker=ticker)


def fetch_return_over_range(
    ticker: str,
    start_date: date,
    end_date: date,
    provider: Optional[MarketDataProvider] = None,
) -> Optional[float]:
    """Return (end_close / start_close) - 1 using daily close prices.

    - start_close: close of the first available trading day on or after start_date
    - end_close:   close of the last available trading day on or before end_date
    - Returns None if fewer than 2 bars are available or on any provider error.
    - Weekend/holiday MVP: if end_date falls on a non-trading day, the last
      available bar before it is used; returns None if fewer than 2 bars result.
    """
    created_default = provider is None
    provider_instance = provider or AlpacaMarketDataProvider()
    try:
        closes = provider_instance.fetch_daily_closes_range(ticker, start_date, end_date)
        if len(closes) < 2:
            logger.warning(
                "fetch_return_over_range_insufficient_bars",
                ticker=ticker,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                bar_count=len(closes),
            )
            return None
        start_close = closes[0]
        end_close = closes[-1]
        if start_close == 0:
            return None
        return (end_close / start_close) - 1
    except Exception as exc:
        logger.error(
            "fetch_return_over_range_failed",
            ticker=ticker,
            error=str(exc),
            exc_info=True,
        )
        return None
    finally:
        if created_default and hasattr(provider_instance, "close"):
            try:
                provider_instance.close()  # type: ignore[attr-defined]
            except Exception:
                logger.warning("market_provider_close_failed", ticker=ticker)


def fetch_close_price_on_date(
    ticker: str,
    trading_date: date,
    provider: Optional[MarketDataProvider] = None,
) -> Optional[float]:
    created_default = provider is None
    provider_instance = provider or AlpacaMarketDataProvider()
    try:
        bar = provider_instance.fetch_daily_bar_on_date(ticker, trading_date)
        if not bar:
            return None
        return bar.get("close")
    except Exception as exc:
        logger.error(
            "fetch_close_price_on_date_failed",
            ticker=ticker,
            trading_date=trading_date.isoformat(),
            error=str(exc),
            exc_info=True,
        )
        return None
    finally:
        if created_default and hasattr(provider_instance, "close"):
            try:
                provider_instance.close()  # type: ignore[attr-defined]
            except Exception:
                logger.warning("market_provider_close_failed", ticker=ticker)


def fetch_open_to_close_return(
    ticker: str,
    trading_date: date,
    provider: Optional[MarketDataProvider] = None,
) -> Optional[float]:
    created_default = provider is None
    provider_instance = provider or AlpacaMarketDataProvider()
    try:
        bar = provider_instance.fetch_daily_bar_on_date(ticker, trading_date)
        if not bar:
            return None
        return _compute_return(bar.get("close"), bar.get("open"))
    except Exception as exc:
        logger.error(
            "fetch_open_to_close_return_failed",
            ticker=ticker,
            trading_date=trading_date.isoformat(),
            error=str(exc),
            exc_info=True,
        )
        return None
    finally:
        if created_default and hasattr(provider_instance, "close"):
            try:
                provider_instance.close()  # type: ignore[attr-defined]
            except Exception:
                logger.warning("market_provider_close_failed", ticker=ticker)


def fetch_price_at_or_before(
    ticker: str,
    as_of: datetime,
    provider: Optional[MarketDataProvider] = None,
) -> Optional[float]:
    created_default = provider is None
    provider_instance = provider or AlpacaMarketDataProvider()
    try:
        return provider_instance.fetch_price_at_or_before(ticker, as_of)
    except Exception as exc:
        logger.error(
            "fetch_price_at_or_before_failed",
            ticker=ticker,
            as_of=_normalized_now(as_of).isoformat(),
            error=str(exc),
            exc_info=True,
        )
        return None
    finally:
        if created_default and hasattr(provider_instance, "close"):
            try:
                provider_instance.close()  # type: ignore[attr-defined]
            except Exception:
                logger.warning("market_provider_close_failed", ticker=ticker)


# ---------------------------------------------------------------------------
# BaseTool implementation
# ---------------------------------------------------------------------------


class MarketDataTool(BaseTool):
    """
    Fetches the latest price snapshot for a stock ticker.

    Uses :class:`AlpacaMarketDataProvider` for price bars and Finnhub for
    sector / earnings context.
    """

    name = "get_market_snapshot"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Fetch the latest market data snapshot for a stock ticker. "
                "Returns last_price, 1-day return, 5-day return, return since "
                "market open during the current regular session, session volume, "
                "20-day average volume, relative volume, sector, days until the "
                "next earnings announcement, basic valuation / short-interest metrics, "
                "plus replayable technical signals such as RSI and ATR-derived volatility."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol, e.g. 'AAPL'",
                    }
                },
                "required": ["ticker"],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        ticker = input.get("ticker")
        if not ticker:
            raise ToolError("ticker is required", tool_name=self.name)
        return dict(get_market_snapshot(str(ticker).upper()))
