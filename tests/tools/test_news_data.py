"""Unit tests for news-data filtering and normalization."""
from __future__ import annotations

from src.providers.news_data import get_recent_news


def test_get_recent_news_filters_low_signal_headlines_and_preserves_metadata():
    class _StubProvider:
        def fetch_recent(self, ticker: str, limit: int):
            assert ticker == "AAPL"
            assert limit == 5
            return [
                {
                    "title": "Is It Too Late To Consider Buying Apple Stock?",
                    "summary": "A retail sentiment article with low information density.",
                    "published_at": "2026-03-24",
                    "source": "The Motley Fool",
                    "url": "https://example.com/retail-opinion",
                    "signal_type": "feature",
                },
                {
                    "title": "Apple raises March-quarter revenue guidance",
                    "summary": "Management increased guidance after stronger-than-expected demand.",
                    "published_at": "2026-03-24",
                    "source": "Business Wire",
                    "url": "https://example.com/guidance",
                    "signal_type": "earnings_guidance",
                },
                {
                    "title": "Morgan Stanley upgrades Apple to Overweight",
                    "summary": "The analyst raised the price target after channel checks improved.",
                    "published_at": "2026-03-24",
                    "source": "Dow Jones",
                    "url": "https://example.com/upgrade",
                    "signal_type": "analyst_rating",
                },
            ]

    items = get_recent_news("AAPL", limit=5, providers=[_StubProvider()])

    assert [item["title"] for item in items] == [
        "Apple raises March-quarter revenue guidance",
        "Morgan Stanley upgrades Apple to Overweight",
    ]
    assert items[0]["signal_type"] == "earnings_guidance"
    assert items[0]["source"] == "Business Wire"
    assert items[1]["signal_type"] == "analyst_rating"
    assert items[1]["url"] == "https://example.com/upgrade"
