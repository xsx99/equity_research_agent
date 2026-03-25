"""Alpaca + Finnhub market data provider."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from src.tools.market_data.helpers import (
    MARKET_TIMEZONE,
    REGULAR_MARKET_OPEN,
    _normalized_now,
    _parse_bar_date,
    _parse_bar_timestamp,
    _resolve_alpaca_data_base_url,
    _to_float_or_none,
    _to_int_or_none,
)
from src.tools.market_data.types import DailyBar

DEFAULT_ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"


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
        self.data_base_url = _resolve_alpaca_data_base_url(data_base_url, DEFAULT_ALPACA_DATA_BASE_URL)
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
            daily_bars.append({
                "date": bar_date,
                "open": float(item["o"]) if item.get("o") is not None else None,
                "high": float(item["h"]) if item.get("h") is not None else None,
                "low": float(item["l"]) if item.get("l") is not None else None,
                "close": float(close_raw),
                "volume": _to_int_or_none(item.get("v")),
            })

        if not daily_bars:
            raise ValueError(f"no_close_prices_for_{symbol}")
        return daily_bars

    def fetch_daily_closes(self, ticker: str, lookback_days: int) -> list[float]:
        return [bar["close"] for bar in self.fetch_daily_bars(ticker, lookback_days)]

    def fetch_daily_closes_range(self, ticker: str, start_date: date, end_date: date) -> list[float]:
        """Return close prices in ascending time order for bars within [start_date, end_date].

        Returns an empty list if no bars are available (not an error).
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
            return {
                "date": bar_date,
                "open": float(item["o"]) if item.get("o") is not None else None,
                "high": float(item["h"]) if item.get("h") is not None else None,
                "low": float(item["l"]) if item.get("l") is not None else None,
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
            "pe_ratio": self._extract_metric_value(metrics, "peBasicExclExtraTTM", "peTTM", "peNormalizedAnnual"),
            "ps_ratio": self._extract_metric_value(metrics, "psTTM", "psAnnual", "priceToSalesAnnual"),
            "short_interest_pct_float": self._extract_metric_value(metrics, "shortPercentOfFloat", "shortInterestPercent", "shortRatio"),
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
