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
            if key == "gold_price":
                # FRED removed the historical IBA gold series upstream, so use the
                # existing GLD proxy path instead of logging a guaranteed 404 each run.
                indicators[key] = _empty_indicator("Gold Proxy (GLD ETF)", "ALPACA:GLD_PROXY", "USD/share")
                value, observed_on, previous_close = _unpack_observation(self._fetch_gold_proxy_from_market_data())
                _set_indicator_values(indicators[key], value=value, observed_on=observed_on, previous_close=previous_close)
                continue
            indicators[key] = _empty_indicator(
                metadata["label"], f"FRED:{metadata['series_id']}", metadata["unit"]
            )
            try:
                value, observed_on, previous_close = _unpack_observation(
                    self._fetch_latest_observation(metadata["series_id"], as_of)
                )
            except Exception as exc:
                logger.warning("global_context_fred_series_failed", series_id=metadata["series_id"], error=str(exc))
                value, observed_on, previous_close = None, None, None
            if key == "vix":
                value, observed_on, source, previous_close = self._prefer_live_vix_if_current_trade_date(
                    value=value,
                    observed_on=observed_on,
                    previous_close=previous_close,
                    as_of=as_of,
                    default_source=indicators[key]["source"],
                )
                indicators[key]["source"] = source
            _set_indicator_values(indicators[key], value=value, observed_on=observed_on, previous_close=previous_close)
        return indicators

    def _fetch_latest_observation(self, series_id: str, as_of: datetime) -> tuple[Optional[float], Optional[str], Optional[float]]:
        if self.api_key:
            value, observed_on, previous_close = self._fetch_from_api_with_previous(series_id, as_of)
            if observed_on is not None:
                return value, observed_on, previous_close
        return self._fetch_from_csv_with_previous(series_id)

    def _fetch_from_api(self, series_id: str, as_of: datetime) -> tuple[Optional[float], Optional[str]]:
        value, observed_on, _previous_close = self._fetch_from_api_with_previous(series_id, as_of)
        return value, observed_on

    def _fetch_from_api_with_previous(
        self, series_id: str, as_of: datetime
    ) -> tuple[Optional[float], Optional[str], Optional[float]]:
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
        values: list[tuple[float, str]] = []
        for row in payload.get("observations", []):
            if not isinstance(row, dict):
                continue
            value = row.get("value")
            if value in (None, "."):
                continue
            try:
                values.append((float(value), str(row.get("date") or "")))
            except (TypeError, ValueError):
                continue
            if len(values) >= 2:
                break
        if not values:
            return None, None, None
        previous_close = values[1][0] if len(values) > 1 else None
        return values[0][0], values[0][1], previous_close

    def _fetch_from_csv(self, series_id: str) -> tuple[Optional[float], Optional[str]]:
        value, observed_on, _previous_close = self._fetch_from_csv_with_previous(series_id)
        return value, observed_on

    def _fetch_from_csv_with_previous(self, series_id: str) -> tuple[Optional[float], Optional[str], Optional[float]]:
        response = self._client.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": series_id},
        )
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        last_value: Optional[float] = None
        last_date: Optional[str] = None
        previous_close: Optional[float] = None
        for row in reader:
            value = row.get(series_id)
            if value in (None, "."):
                continue
            try:
                parsed_value = float(value)
            except (TypeError, ValueError):
                continue
            if last_value is not None:
                previous_close = last_value
            last_value = parsed_value
            last_date = row.get("DATE") or row.get("observation_date")
        return last_value, last_date, previous_close

    def _prefer_live_vix_if_current_trade_date(
        self,
        *,
        value: Optional[float],
        observed_on: Optional[str],
        previous_close: Optional[float],
        as_of: datetime,
        default_source: str,
    ) -> tuple[Optional[float], Optional[str], str, Optional[float]]:
        target_trade_date = as_of.astimezone(MARKET_TIMEZONE).date().isoformat()
        if observed_on == target_trade_date:
            return value, observed_on, default_source, previous_close

        try:
            live_value, live_observed_on, live_previous_close = _unpack_observation(self._fetch_live_vix_from_yahoo(as_of))
        except Exception as exc:
            logger.warning("global_context_live_vix_failed", error=str(exc))
            return value, observed_on, default_source, previous_close

        if live_value is not None and live_observed_on == target_trade_date:
            return live_value, live_observed_on, "YAHOO:^VIX", live_previous_close
        return value, observed_on, default_source, previous_close

    def _fetch_live_vix_from_yahoo(
        self,
        as_of: datetime,
    ) -> tuple[Optional[float], Optional[str], Optional[float]]:
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
        previous_close: Optional[float] = None
        prior_value: Optional[float] = None
        for timestamp, close in zip(timestamps, closes):
            if close is None:
                continue
            observed_on = datetime.fromtimestamp(timestamp, tz).date().isoformat()
            parsed_close = float(close)
            if observed_on != target_trade_date:
                prior_value = parsed_close
                continue
            latest_value = parsed_close
            latest_date = observed_on
            previous_close = prior_value

        return latest_value, latest_date, previous_close

    def _fetch_gold_proxy_from_market_data(self) -> tuple[Optional[float], Optional[str], Optional[float]]:
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
            return None, None, None
        latest_bar = bars[-1]
        previous_bar = bars[-2] if len(bars) >= 2 else None
        observed_on = latest_bar.get("date")
        previous_close = previous_bar.get("close") if previous_bar else None
        return latest_bar.get("close"), observed_on.isoformat() if observed_on else None, previous_close

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _unpack_observation(result: tuple[object, ...]) -> tuple[Optional[float], Optional[str], Optional[float]]:
    value = result[0] if len(result) >= 1 else None
    observed_on = result[1] if len(result) >= 2 else None
    previous_close = result[2] if len(result) >= 3 else None
    return _to_float(value), str(observed_on) if observed_on else None, _to_float(previous_close)


def _set_indicator_values(
    indicator: MacroIndicatorValue,
    *,
    value: Optional[float],
    observed_on: Optional[str],
    previous_close: Optional[float],
) -> None:
    indicator["value"] = value
    indicator["observed_on"] = observed_on
    if previous_close is None:
        return
    indicator["previous_close"] = previous_close
    if value is not None and previous_close != 0.0:
        indicator["return_vs_previous_close"] = (value - previous_close) / previous_close


def _to_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
