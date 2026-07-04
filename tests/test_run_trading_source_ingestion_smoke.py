from datetime import date, datetime, timezone

from scripts.run_trading_source_ingestion_smoke import run_smoke


class _FakeMarketProvider:
    def fetch_daily_bars(self, ticker, lookback_days):
        return [
            {"date": date(2026, 5, 29), "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0, "volume": 1_000_000},
            {"date": date(2026, 5, 30), "open": 100.0, "high": 104.0, "low": 99.0, "close": 103.0, "volume": 2_000_000},
        ]

    def fetch_context(self, ticker):
        return {"market_cap": 3_000_000_000_000, "quality_score": 0.8}


class _FakeNewsProvider:
    def fetch_recent(self, ticker, limit):
        return [
            {
                "title": "Apple upgraded after demand check",
                "summary": "Analyst raises rating.",
                "published_at": "2026-06-01T10:30:00+00:00",
                "source": "fixture",
                "signal_type": "analyst_rating",
            }
        ]


class _DuplicateNewsProvider:
    def fetch_recent(self, ticker, limit):
        return [
            {
                "title": "Is It Too Late To Buy Apple Stock?",
                "summary": "Retail commentary without a concrete catalyst.",
                "published_at": "2026-06-01T09:00:00+00:00",
                "source": "Retail Blog",
                "url": "https://example.test/retail-opinion",
                "signal_type": "general_news",
            },
            {
                "title": "Morgan Stanley upgrades Apple to Overweight, target to $180",
                "summary": "The analyst cited stronger iPhone demand.",
                "published_at": "2026-06-01T10:00:00+00:00",
                "source": "Reuters",
                "url": "https://example.test/reuters-upgrade",
                "signal_type": "analyst_rating",
            },
            {
                "title": "Apple upgraded to Overweight at Morgan Stanley; PT raised to $180",
                "summary": "Demand checks improved and the broker lifted its target.",
                "published_at": "2026-06-01T10:05:00+00:00",
                "source": "Dow Jones",
                "url": "https://example.test/dj-upgrade",
                "signal_type": "analyst_rating",
            },
            {
                "title": "Morgan Stanley lifts Apple target to $190 and keeps Overweight",
                "summary": "The revised target reflects stronger services momentum.",
                "published_at": "2026-06-01T11:00:00+00:00",
                "source": "Reuters",
                "url": "https://example.test/reuters-upgrade-190",
                "signal_type": "analyst_rating",
            },
        ]


def test_run_trading_source_ingestion_smoke_uses_fake_providers_without_network():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    result = run_smoke(
        ticker="aapl",
        families=("technical", "fundamental", "events_news"),
        market_provider=_FakeMarketProvider(),
        news_provider=_FakeNewsProvider(),
        provider_name="fixture",
        as_of=now,
        now=lambda: now,
        sleeper=lambda seconds: None,
    )

    assert result["status"] == "passed"
    assert result["source_records_by_family"] == {
        "events_news": 1,
        "fundamental": 1,
        "technical": 1,
    }
    assert result["provider_request_statuses"] == [
        "succeeded",
        "succeeded",
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    assert result["technical_preview"]["bar_count"] == 2
    assert result["technical_preview"]["benchmark_returns"] == {"QQQ": 0.03, "SPY": 0.03}
    assert result["technical_preview"]["premarket_gap_pct"] is None
    assert "source_records" not in result
    assert result["event_news_preview"] == [
        {
            "event_type": "analyst_upgrade",
            "headline": "Apple upgraded after demand check",
            "importance": "high",
            "published_at": "2026-06-01T10:30:00+00:00",
            "sentiment": "positive",
            "source": "fixture",
            "summary": "Analyst raises rating.",
        }
    ]
    assert result["provider_requests"][0]["started_at"] == "2026-06-01T12:00:00+00:00"
    assert result["provider_requests"][0]["completed_at"] == "2026-06-01T12:00:00+00:00"


def test_run_trading_source_ingestion_smoke_can_include_normalized_source_records():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    result = run_smoke(
        ticker="aapl",
        families=("events_news",),
        market_provider=_FakeMarketProvider(),
        news_provider=_FakeNewsProvider(),
        provider_name="fixture",
        as_of=now,
        now=lambda: now,
        include_records=True,
        sleeper=lambda seconds: None,
    )

    assert len(result["source_records"]) == 1
    record = result["source_records"][0]
    assert record["ticker"] == "AAPL"
    assert record["source_family"] == "events_news"
    assert record["source"] == "fixture"
    assert record["source_table"] == "event_news_items"
    assert record["event_time"] == "2026-06-01T10:30:00+00:00"
    assert record["published_at"] == "2026-06-01T10:30:00+00:00"
    assert record["ingested_at"] == "2026-06-01T12:00:00+00:00"
    assert record["available_for_decision_at"] == "2026-06-01T12:00:00+00:00"
    assert record["payload"]["event_type"] == "analyst_upgrade"
    assert record["payload"]["direction"] == "positive"
    assert record["payload"]["sentiment"] == "positive"
    assert record["payload"]["importance"] == "high"
    assert record["payload"]["signal_type"] == "analyst_rating"
    assert record["payload"]["compression_status"] == "kept"
    assert record["payload"]["compression_reason"] == "unique_item"
    assert record["payload"]["duplicate_count"] == 1
    assert record["payload"]["retained_rank_reason"] == "earliest_available_then_specificity"


def test_run_trading_source_ingestion_smoke_reports_news_condensation_summary():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    result = run_smoke(
        ticker="aapl",
        families=("events_news",),
        market_provider=_FakeMarketProvider(),
        news_provider=_DuplicateNewsProvider(),
        provider_name="fixture",
        as_of=now,
        now=lambda: now,
        sleeper=lambda seconds: None,
    )

    assert result["status"] == "passed"
    assert result["event_news_items"] == 2
    assert result["news_condensation"] == {
        "raw_news_item_count": 4,
        "kept_news_item_count": 2,
        "dropped_low_signal_count": 1,
        "dropped_duplicate_count": 1,
        "dropped_irrelevant_count": 0,
    }
    assert [item["headline"] for item in result["event_news_preview"]] == [
        "Morgan Stanley upgrades Apple to Overweight, target to $180",
        "Morgan Stanley lifts Apple target to $190 and keeps Overweight",
    ]
