"""Unit tests for the live tool smoke script helpers."""
from __future__ import annotations

import scripts.run_tool_smoke_test as smoke


def test_marketaux_smoke_skips_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("MARKETAUX_API_KEY", raising=False)

    result = smoke._smoke_marketaux_news_tool("AAPL", 3)

    assert result.name == "marketaux_recent_news"
    assert result.status == "skipped"
    assert "MARKETAUX_API_KEY" in result.details


def test_marketaux_smoke_passes_with_provider_results(monkeypatch):
    monkeypatch.setenv("MARKETAUX_API_KEY", "test-key")
    provider_instances: list[_StubMarketauxProvider] = []

    class _StubMarketauxProvider:
        def __init__(self, *args, **kwargs) -> None:
            self.closed = False
            provider_instances.append(self)

        def fetch_recent(self, ticker: str, limit: int):
            assert ticker == "AAPL"
            assert limit == 3
            return [
                {"title": "Headline", "summary": "Summary"},
                {"title": "Second", "summary": "Another summary"},
            ]

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(smoke, "MarketauxNewsProvider", _StubMarketauxProvider)

    result = smoke._smoke_marketaux_news_tool("AAPL", 3)

    assert result.name == "marketaux_recent_news"
    assert result.status == "passed"
    assert "Marketaux" in result.details
    assert result.preview == [
        {"title": "Headline", "summary": "Summary"},
        {"title": "Second", "summary": "Another summary"},
    ]
    assert len(provider_instances) == 1
    assert provider_instances[0].closed is True
