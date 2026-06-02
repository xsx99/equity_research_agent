"""FRED macro data provider."""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from src.core.logging import get_logger
from src.providers.global_context.helpers import _empty_indicator
from src.providers.global_context.types import MacroIndicatorValue, _FRED_SERIES
from src.providers.market_data.helpers import MARKET_TIMEZONE

logger = get_logger(__name__)


class FredMacroDataProvider:
    """Fetch macro indicators from FRED, falling back to the official CSV export."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def fetch_indicators(self, as_of: datetime) -> dict[str, MacroIndicatorValue]:
        indicators: dict[str, MacroIndicatorValue] = {}
        for key, metadata in _FRED_SERIES.items():
            indicators[key] = _empty_indicator(
                metadata["label"], f"FRED:{metadata['series_id']}", metadata["unit"]
            )
            try:
                value, observed_on = self._fetch_latest_observation(metadata["series_id"], as_of)
            except Exception as exc:
                logger.warning("global_context_fred_series_failed", series_id=metadata["series_id"], error=str(exc))
                value, observed_on = None, None
            if key == "vix":
                value, observed_on, source = self._prefer_live_vix_if_current_trade_date(
                    value=value,
                    observed_on=observed_on,
                    as_of=as_of,
                    default_source=indicators[key]["source"],
                )
                indicators[key]["source"] = source
            if value is None and key == "gold_price":
                value, observed_on = self._fetch_gold_proxy_from_market_data()
                if value is not None:
                    indicators[key]["label"] = "Gold Proxy (GLD ETF)"
                    indicators[key]["source"] = "ALPACA:GLD_PROXY"
                    indicators[key]["unit"] = "USD/share"
            indicators[key]["value"] = value
            indicators[key]["observed_on"] = observed_on
        return indicators

    def _fetch_latest_observation(self, series_id: str, as_of: datetime) -> tuple[Optional[float], Optional[str]]:
        if self.api_key:
            value, observed_on = self._fetch_from_api(series_id, as_of)
            if observed_on is not None:
                return value, observed_on
        return self._fetch_from_csv(series_id)

    def _fetch_from_api(self, series_id: str, as_of: datetime) -> tuple[Optional[float], Optional[str]]:
        response = self._client.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_end": as_of.date().isoformat(),
                "sort_order": "desc",
                "limit": 10,
            },
        )
        response.raise_for_status()
        payload = response.json()
        for row in payload.get("observations", []):
            if not isinstance(row, dict):
                continue
            value = row.get("value")
            if value in (None, "."):
                continue
            try:
                return float(value), str(row.get("date") or "")
            except (TypeError, ValueError):
                continue
        return None, None

    def _fetch_from_csv(self, series_id: str) -> tuple[Optional[float], Optional[str]]:
        response = self._client.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": series_id},
        )
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        last_value: Optional[float] = None
        last_date: Optional[str] = None
        for row in reader:
            value = row.get(series_id)
            if value in (None, "."):
                continue
            try:
                last_value = float(value)
            except (TypeError, ValueError):
                continue
            last_date = row.get("DATE") or row.get("observation_date")
        return last_value, last_date

    def _prefer_live_vix_if_current_trade_date(
        self,
        *,
        value: Optional[float],
        observed_on: Optional[str],
        as_of: datetime,
        default_source: str,
    ) -> tuple[Optional[float], Optional[str], str]:
        target_trade_date = as_of.astimezone(MARKET_TIMEZONE).date().isoformat()
        if observed_on == target_trade_date:
            return value, observed_on, default_source

        try:
            live_value, live_observed_on = self._fetch_live_vix_from_yahoo(as_of)
        except Exception as exc:
            logger.warning("global_context_live_vix_failed", error=str(exc))
            return value, observed_on, default_source

        if live_value is not None and live_observed_on == target_trade_date:
            return live_value, live_observed_on, "YAHOO:^VIX"
        return value, observed_on, default_source

    def _fetch_live_vix_from_yahoo(
        self,
        as_of: datetime,
    ) -> tuple[Optional[float], Optional[str]]:
        response = self._client.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",
            params={
                "range": "10d",
                "interval": "1d",
            },
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        payload = response.json()
        result = (payload.get("chart") or {}).get("result") or []
        if not result or not isinstance(result[0], dict):
            return None, None

        chart = result[0]
        timestamps = chart.get("timestamp") or []
        quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        meta = chart.get("meta") or {}
        exchange_timezone = meta.get("exchangeTimezoneName") or str(MARKET_TIMEZONE)
        tz = ZoneInfo(exchange_timezone)

        target_trade_date = as_of.astimezone(MARKET_TIMEZONE).date().isoformat()
        latest_value: Optional[float] = None
        latest_date: Optional[str] = None
        for timestamp, close in zip(timestamps, closes):
            if close is None:
                continue
            observed_on = datetime.fromtimestamp(timestamp, tz).date().isoformat()
            if observed_on != target_trade_date:
                continue
            latest_value = float(close)
            latest_date = observed_on

        return latest_value, latest_date

    def _fetch_gold_proxy_from_market_data(self) -> tuple[Optional[float], Optional[str]]:
        from src.providers.market_data import AlpacaMarketDataProvider
        provider = AlpacaMarketDataProvider()
        try:
            bars = provider.fetch_daily_bars("GLD", lookback_days=3)
        except Exception as exc:
            logger.warning("global_context_gold_proxy_failed", error=str(exc))
            return None, None
        finally:
            try:
                provider.close()
            except Exception:
                logger.warning("global_context_gold_proxy_close_failed")
        if not bars:
            return None, None
        latest_bar = bars[-1]
        observed_on = latest_bar.get("date")
        return latest_bar.get("close"), observed_on.isoformat() if observed_on else None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
