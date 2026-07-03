"""Unit tests for yfinance-backed fundamental normalization."""
from __future__ import annotations

import pytest

from src.providers.market_data.yfinance_fundamentals import YFinanceFundamentalsProvider


def test_yfinance_fundamentals_fetch_normalizes_ratio_units_and_names():
    seen_symbols: list[str] = []

    def _info_fetcher(symbol: str) -> dict[str, object]:
        seen_symbols.append(symbol)
        return {
            "sector": " Technology ",
            "shortName": " Example Inc. ",
            "longName": "Example Incorporated",
            "marketCap": "123456789",
            "trailingPE": "29.0",
            "priceToSalesTrailing12Months": 7.0,
            "enterpriseToRevenue": 7.5,
            "freeCashflow": 240.0,
            "totalRevenue": 1000.0,
            "shortPercentOfFloat": 0.035,
            "revenueGrowth": 0.18,
            "operatingMargins": 0.31,
            "returnOnEquity": 0.15,
            "returnOnAssets": 0.06,
        }

    payload = YFinanceFundamentalsProvider(info_fetcher=_info_fetcher).fetch("aapl")

    assert seen_symbols == ["AAPL"]
    assert payload == {
        "sector": "Technology",
        "company_name": "Example Inc.",
        "market_cap": 123456789.0,
        "pe_ratio": 29.0,
        "ps_ratio": 7.0,
        "ev_sales_multiple": 7.5,
        "fcf_margin_pct": pytest.approx(24.0),
        "short_interest_pct_float": pytest.approx(3.5),
        "revenue_growth_pct": pytest.approx(18.0),
        "operating_margin_pct": pytest.approx(31.0),
        "roe_pct": pytest.approx(15.0),
        "roa_pct": pytest.approx(6.0),
    }
    assert "earnings_in_days" not in payload
    assert "earnings_date" not in payload
    assert "known_event_date" not in payload


def test_yfinance_fundamentals_fetch_degrades_to_empty_payload_on_fetch_error():
    def _info_fetcher(symbol: str) -> dict[str, object]:
        raise RuntimeError("provider unavailable")

    payload = YFinanceFundamentalsProvider(info_fetcher=_info_fetcher).fetch("AAPL")

    assert payload == {
        "sector": None,
        "company_name": None,
        "market_cap": None,
        "pe_ratio": None,
        "ps_ratio": None,
        "ev_sales_multiple": None,
        "fcf_margin_pct": None,
        "short_interest_pct_float": None,
        "revenue_growth_pct": None,
        "operating_margin_pct": None,
        "roe_pct": None,
        "roa_pct": None,
    }


def test_yfinance_fundamentals_fetch_handles_zero_revenue_without_margin():
    payload = YFinanceFundamentalsProvider(
        info_fetcher=lambda symbol: {"freeCashflow": 25.0, "totalRevenue": 0}
    ).fetch("AAPL")

    assert payload["fcf_margin_pct"] is None
