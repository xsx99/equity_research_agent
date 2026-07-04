"""Market data providers and helper functions."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from src.core.logging import get_logger
from src.providers.market_data.alpaca_provider import AlpacaMarketDataProvider, DEFAULT_ALPACA_DATA_BASE_URL
from src.providers.market_data.fmp_economic_calendar import FMPEconomicCalendar
from src.providers.market_data.helpers import (
    MARKET_TIMEZONE,
    REGULAR_MARKET_CLOSE,
    REGULAR_MARKET_OPEN,
    _compute_return,
    _compute_return_since_market_open,
    _compute_technical_signals,
    _normalized_now,
    _to_float_or_none,
    _to_int_or_none,
)
from src.providers.market_data.types import (
    DailyBar,
    MarketDataProvider,
    MarketSnapshot,
    MomentumSignals,
    TechnicalSignals,
    VolatilitySignals,
)

__all__ = [
    "AlpacaMarketDataProvider",
    "DailyBar",
    "DEFAULT_ALPACA_DATA_BASE_URL",
    "MarketDataProvider",
    "MarketSnapshot",
    "MARKET_TIMEZONE",
    "MomentumSignals",
    "REGULAR_MARKET_CLOSE",
    "REGULAR_MARKET_OPEN",
    "TechnicalSignals",
    "VolatilitySignals",
    "fetch_close_price_on_date",
    "fetch_open_to_close_return",
    "fetch_price_at_or_before",
    "fetch_return_over_range",
    "FMPEconomicCalendar",
    "get_market_snapshot",
]

logger = get_logger(__name__)


def get_market_snapshot(
    ticker: str,
    provider: Optional[MarketDataProvider] = None,
    now: Optional[datetime] = None,
) -> MarketSnapshot:
    """Fetch a market snapshot with resilient fallback on provider errors."""
    created_default = provider is None
    provider_instance = provider or AlpacaMarketDataProvider()
    snapshot: MarketSnapshot = {
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
        "earnings_date": None,
        "pe_ratio": None,
        "ps_ratio": None,
        "short_interest_pct_float": None,
        "technical_signals": {
            "momentum": {"rsi_14": None, "rsi_3": None},
            "volatility": {"atr_14": None, "yesterday_range": None, "atr_multiple": None},
        },
    }
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
        snapshot["return_since_market_open"] = _compute_return_since_market_open(last_bar, current_time)

        session_volume = _to_int_or_none(last_bar.get("volume")) if last_bar else None
        prior_volumes = [
            v for v in (_to_float_or_none(bar.get("volume")) for bar in daily_bars[:-1][-20:])
            if v is not None
        ]
        avg_volume_20d = sum(prior_volumes) / len(prior_volumes) if prior_volumes else None
        snapshot["session_volume"] = session_volume
        snapshot["avg_volume_20d"] = avg_volume_20d
        snapshot["relative_volume"] = (
            None if session_volume is None or avg_volume_20d in (None, 0)
            else float(session_volume) / avg_volume_20d
        )
        snapshot["technical_signals"] = _compute_technical_signals(daily_bars, current_time)

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
        snapshot["earnings_date"] = context.get("earnings_date") if isinstance(context.get("earnings_date"), date) else None
        snapshot["pe_ratio"] = _to_float_or_none(context.get("pe_ratio"))
        snapshot["ps_ratio"] = _to_float_or_none(context.get("ps_ratio"))
        snapshot["short_interest_pct_float"] = _to_float_or_none(context.get("short_interest_pct_float"))
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
    """Return (end_close / start_close) - 1 using daily close prices."""
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
        logger.error("fetch_return_over_range_failed", ticker=ticker, error=str(exc), exc_info=True)
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
        return bar.get("close") if bar else None
    except Exception as exc:
        logger.error("fetch_close_price_on_date_failed", ticker=ticker, trading_date=trading_date.isoformat(), error=str(exc), exc_info=True)
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
        return _compute_return(bar.get("close"), bar.get("open")) if bar else None
    except Exception as exc:
        logger.error("fetch_open_to_close_return_failed", ticker=ticker, trading_date=trading_date.isoformat(), error=str(exc), exc_info=True)
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
        logger.error("fetch_price_at_or_before_failed", ticker=ticker, as_of=_normalized_now(as_of).isoformat(), error=str(exc), exc_info=True)
        return None
    finally:
        if created_default and hasattr(provider_instance, "close"):
            try:
                provider_instance.close()  # type: ignore[attr-defined]
            except Exception:
                logger.warning("market_provider_close_failed", ticker=ticker)
