"""yfinance-backed fundamentals provider.

Backfills fundamental metrics Finnhub's free tier may not return. Yahoo
Finance ratios such as margins, growth, and short interest are reported as
fractions, so this module converts them to percentages before Alpaca provider
normalization.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from src.providers.market_data.helpers import _to_float_or_none


class YFinanceFundamentalsProvider:
    """Fetch a normalized fundamentals payload for one ticker from Yahoo."""

    def __init__(
        self,
        *,
        info_fetcher: Optional[Callable[[str], dict[str, Any]]] = None,
    ) -> None:
        self._info_fetcher = info_fetcher

    def fetch(self, ticker: str) -> dict[str, Any]:
        symbol = ticker.upper()
        info = self._load_info(symbol)
        if not isinstance(info, dict):
            info = {}

        short_float = _to_float_or_none(info.get("shortPercentOfFloat"))
        short_interest_pct = short_float * 100.0 if short_float is not None else None

        fcf = _to_float_or_none(info.get("freeCashflow"))
        revenue = _to_float_or_none(info.get("totalRevenue"))
        fcf_margin_pct = (
            fcf / revenue * 100.0
            if fcf is not None and revenue not in (None, 0)
            else None
        )

        return {
            "sector": self._clean_str(info.get("sector")),
            "company_name": self._clean_str(info.get("shortName") or info.get("longName")),
            "market_cap": _to_float_or_none(info.get("marketCap")),
            "pe_ratio": _to_float_or_none(info.get("trailingPE")),
            "ps_ratio": _to_float_or_none(info.get("priceToSalesTrailing12Months")),
            "ev_sales_multiple": _to_float_or_none(info.get("enterpriseToRevenue")),
            "fcf_margin_pct": fcf_margin_pct,
            "short_interest_pct_float": short_interest_pct,
            "revenue_growth_pct": self._as_pct(info.get("revenueGrowth")),
            "operating_margin_pct": self._as_pct(info.get("operatingMargins")),
            "roe_pct": self._as_pct(info.get("returnOnEquity")),
            "roa_pct": self._as_pct(info.get("returnOnAssets")),
        }

    def _load_info(self, symbol: str) -> dict[str, Any]:
        if self._info_fetcher is not None:
            try:
                return self._info_fetcher(symbol)
            except Exception:
                return {}
        try:
            import yfinance as yf
        except ImportError:
            return {}
        try:
            info = yf.Ticker(symbol).info
        except Exception:
            return {}
        return info if isinstance(info, dict) else {}

    @staticmethod
    def _as_pct(value: Any) -> Optional[float]:
        parsed = _to_float_or_none(value)
        return parsed * 100.0 if parsed is not None else None

    @staticmethod
    def _clean_str(value: Any) -> Optional[str]:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None
