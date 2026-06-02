"""Navigation tests for provider import paths."""
from __future__ import annotations


def test_market_data_provider_path_exports_runtime_contracts():
    from src.providers.market_data import AlpacaMarketDataProvider, MarketDataProvider, get_market_snapshot

    assert AlpacaMarketDataProvider.__name__ == "AlpacaMarketDataProvider"
    assert MarketDataProvider.__name__ == "MarketDataProvider"
    assert callable(get_market_snapshot)


def test_news_provider_path_exports_runtime_contracts():
    from src.providers.news_data import FinnhubNewsProvider, NewsProvider, get_recent_news

    assert FinnhubNewsProvider.__name__ == "FinnhubNewsProvider"
    assert NewsProvider.__name__ == "NewsProvider"
    assert callable(get_recent_news)


def test_global_context_provider_path_exports_runtime_contracts():
    from src.providers.global_context import FredMacroDataProvider, get_global_context

    assert FredMacroDataProvider.__name__ == "FredMacroDataProvider"
    assert callable(get_global_context)

