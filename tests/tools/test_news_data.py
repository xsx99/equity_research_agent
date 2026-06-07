"""Unit tests for news-data filtering and normalization."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from src.providers.news_data import AlpacaNewsProvider, FinnhubNewsProvider, MarketauxNewsProvider, get_recent_news
from src.providers.news_data.helpers import condense_news_items


def _json_client(payload):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


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


def test_provider_adapters_preserve_full_iso_timestamps():
    finnhub = FinnhubNewsProvider(
        api_key="test",
        client=_json_client(
            [
                {
                    "headline": "Apple raises guidance",
                    "summary": "Management raised the outlook.",
                    "datetime": 1780309800,
                    "source": "Finnhub Wire",
                    "url": "https://example.com/finnhub-guidance",
                }
            ]
        ),
    )
    marketaux = MarketauxNewsProvider(
        api_key="test",
        client=_json_client(
            {
                "data": [
                    {
                        "title": "Apple wins another large customer order",
                        "description": "The company disclosed a multi-year agreement.",
                        "published_at": "2026-06-01T10:45:00+00:00",
                        "source": {"name": "Marketaux Wire"},
                        "url": "https://example.com/marketaux-order",
                    }
                ]
            }
        ),
    )
    alpaca = AlpacaNewsProvider(
        api_key="test",
        secret_key="secret",
        data_base_url="https://data.example.test",
        client=_json_client(
            {
                "news": [
                    {
                        "headline": "Apple launches a new product line",
                        "summary": "The launch broadens the company's AI device push.",
                        "created_at": "2026-06-01T11:15:00+00:00",
                        "source": "Alpaca Wire",
                        "url": "https://example.com/alpaca-launch",
                    }
                ]
            }
        ),
    )

    try:
        assert finnhub.fetch_recent("AAPL", limit=1)[0]["published_at"] == "2026-06-01T10:30:00+00:00"
        assert marketaux.fetch_recent("AAPL", limit=1)[0]["published_at"] == "2026-06-01T10:45:00+00:00"
        assert alpaca.fetch_recent("AAPL", limit=1)[0]["published_at"] == "2026-06-01T11:15:00+00:00"
    finally:
        finnhub.close()
        marketaux.close()
        alpaca.close()


def test_condense_news_items_drops_low_signal_duplicates_and_keeps_new_facts():
    as_of = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    result = condense_news_items(
        ticker="AAPL",
        items=[
            {
                "title": "Is It Too Late To Buy Apple Stock?",
                "summary": "Retail commentary without a concrete catalyst.",
                "published_at": "2026-06-01T09:00:00+00:00",
                "source": "Retail Blog",
                "url": "https://example.com/retail",
                "signal_type": "general_news",
            },
            {
                "title": "Morgan Stanley upgrades Apple to Overweight, target to $180",
                "summary": "The analyst cited stronger iPhone demand.",
                "published_at": "2026-06-01T10:00:00+00:00",
                "source": "Reuters",
                "url": "https://example.com/reuters-upgrade",
                "signal_type": "analyst_rating",
            },
            {
                "title": "Apple upgraded to Overweight at Morgan Stanley; PT raised to $180",
                "summary": "Demand checks improved and the broker lifted its target.",
                "published_at": "2026-06-01T10:05:00+00:00",
                "source": "Dow Jones",
                "url": "https://example.com/dj-upgrade",
                "signal_type": "analyst_rating",
            },
            {
                "title": "Morgan Stanley lifts Apple target to $190 and keeps Overweight",
                "summary": "The revised target reflects stronger services momentum.",
                "published_at": "2026-06-01T11:00:00+00:00",
                "source": "Reuters",
                "url": "https://example.com/reuters-upgrade-190",
                "signal_type": "analyst_rating",
            },
        ],
        as_of=as_of,
    )

    assert result.raw_news_item_count == 4
    assert result.kept_news_item_count == 2
    assert result.dropped_low_signal_count == 1
    assert result.dropped_duplicate_count == 1
    assert result.dropped_irrelevant_count == 0
    assert [item.title for item in result.kept_items] == [
        "Morgan Stanley upgrades Apple to Overweight, target to $180",
        "Morgan Stanley lifts Apple target to $190 and keeps Overweight",
    ]
    assert result.kept_items[0].event_type == "analyst_upgrade"
    assert result.kept_items[0].duplicate_count == 2
    assert result.kept_items[0].duplicate_group_key != result.kept_items[1].duplicate_group_key
    assert result.kept_items[0].dropped_sources == ("Dow Jones",)


def test_condense_news_items_prefers_earlier_report_and_emits_metadata():
    as_of = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    result = condense_news_items(
        ticker="AAPL",
        items=[
            {
                "title": "Apple files Form 8-K after product launch",
                "summary": "The filing disclosed launch timing.",
                "published_at": "2026-06-01T09:30:00+00:00",
                "source": "SEC Feed",
                "url": "https://example.com/sec-1",
                "signal_type": "sec_filing",
            },
            {
                "title": "Apple files Form 8-K after product launch",
                "summary": "The company disclosed launch timing and included more descriptive text.",
                "published_at": "2026-06-01T09:45:00+00:00",
                "source": "Newswire",
                "url": "https://example.com/sec-2",
                "signal_type": "sec_filing",
            },
        ],
        as_of=as_of,
    )

    assert result.kept_news_item_count == 1
    kept = result.kept_items[0]
    assert kept.title == "Apple files Form 8-K after product launch"
    assert kept.event_type == "form_8k"
    assert kept.metadata["compression_status"] == "kept"
    assert kept.metadata["compression_reason"] == "deduped_representative"
    assert kept.metadata["retained_rank_reason"] == "earliest_available_then_specificity"
    assert kept.metadata["duplicate_count"] == 2
    assert kept.metadata["dropped_sources"] == ["Newswire"]


def test_condense_news_items_keeps_stage_change_as_new_fact():
    as_of = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    result = condense_news_items(
        ticker="AAPL",
        items=[
            {
                "title": "FDA announced review of Apple's cardiac feature filing",
                "summary": "The company said the submission entered formal review.",
                "published_at": "2026-06-01T08:00:00+00:00",
                "source": "Reuters",
                "url": "https://example.com/fda-review",
                "signal_type": "company_update",
            },
            {
                "title": "FDA approves Apple's cardiac feature filing",
                "summary": "The approval clears the product for launch.",
                "published_at": "2026-06-01T10:00:00+00:00",
                "source": "Reuters",
                "url": "https://example.com/fda-approval",
                "signal_type": "company_update",
            },
        ],
        as_of=as_of,
    )

    assert result.kept_news_item_count == 2
    assert [item.duplicate_group_key for item in result.kept_items][0] != [item.duplicate_group_key for item in result.kept_items][1]


def test_condense_news_items_keeps_later_negative_fact_as_distinct_event():
    as_of = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    result = condense_news_items(
        ticker="AAPL",
        items=[
            {
                "title": "Apple launches new device lineup",
                "summary": "The launch expands the company product family.",
                "published_at": "2026-06-01T09:00:00+00:00",
                "source": "Reuters",
                "url": "https://example.com/launch",
                "signal_type": "company_update",
            },
            {
                "title": "Apple launches new device lineup after resolving recall issue",
                "summary": "The company said it resolved a recall affecting the prior model.",
                "published_at": "2026-06-01T10:00:00+00:00",
                "source": "Reuters",
                "url": "https://example.com/launch-recall",
                "signal_type": "company_update",
            },
        ],
        as_of=as_of,
    )

    assert result.kept_news_item_count == 2
    assert result.kept_items[1].event_type == "recall"
