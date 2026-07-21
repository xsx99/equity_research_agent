"""Shared types, protocols, keyword lists, and FRED series config for global context."""
from __future__ import annotations

from datetime import datetime
from typing import NotRequired, Optional, Protocol, TypedDict


class MacroIndicatorValue(TypedDict):
    label: str
    source: str
    unit: str
    value: Optional[float]
    observed_on: Optional[str]
    previous_close: NotRequired[Optional[float]]
    return_vs_previous_close: NotRequired[Optional[float]]


class GlobalNewsItem(TypedDict):
    source: str
    title: str
    summary: str
    published_at: Optional[str]
    url: Optional[str]


class GlobalContextSnapshot(TypedDict):
    as_of: str
    indicators: dict[str, MacroIndicatorValue]
    official_updates: list[GlobalNewsItem]
    trump_updates: list[GlobalNewsItem]
    geopolitical_news: list[GlobalNewsItem]


class MacroIndicatorProvider(Protocol):
    def fetch_indicators(self, as_of: datetime) -> dict[str, MacroIndicatorValue]:
        """Fetch the configured macro indicator set."""


class NewsFeedProvider(Protocol):
    def fetch_recent(self, limit: int) -> list[GlobalNewsItem]:
        """Fetch normalized official/geopolitical updates."""


_TRUMP_KEYWORDS = (
    "trump",
    "president donald j. trump",
    "president trump",
    "donald j. trump",
)

_MARKET_IMPACT_KEYWORDS = (
    "tariff", "tariffs", "sanction", "sanctions", "treasury", "commerce",
    "export control", "export controls", "chip", "chips", "semiconductor",
    "ai", "artificial intelligence", "antitrust", "economy", "economic",
    "trade", "market", "markets", "oil", "energy", "iran", "china",
    "rates", "treasury yield", "credit",
)

_GEOPOLITICAL_KEYWORDS = (
    "war", "military", "troops", "missile", "airstrike", "airstrikes",
    "diplomatic", "ceasefire", "sanction", "tariff", "iran", "israel",
    "gaza", "ukraine", "russia", "china", "taiwan", "nato", "embassy",
    "mideast", "middle east", "oil", "energy", "shipping", "refinery", "defense",
)

_FRED_SERIES: dict[str, dict[str, str]] = {
    "oil_price":       {"series_id": "DCOILWTICO",        "label": "WTI Crude Oil Spot Price",    "unit": "USD/bbl"},
    "gold_price":      {"series_id": "GOLDAMGBD228NLBM",  "label": "Gold Fixing Price",           "unit": "USD/troy_oz"},
    "us_treasury_2y":  {"series_id": "DGS2",              "label": "US Treasury 2Y",              "unit": "pct"},
    "us_treasury_10y": {"series_id": "DGS10",             "label": "US Treasury 10Y",             "unit": "pct"},
    "us_treasury_20y": {"series_id": "DGS20",             "label": "US Treasury 20Y",             "unit": "pct"},
    "credit_spread":   {"series_id": "BAMLH0A0HYM2",      "label": "ICE BofA US High Yield OAS",  "unit": "pct"},
    "vix":             {"series_id": "VIXCLS",             "label": "CBOE Volatility Index",       "unit": "index"},
}
