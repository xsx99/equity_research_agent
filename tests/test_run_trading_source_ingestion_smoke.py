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
    assert result["provider_request_statuses"] == ["succeeded", "succeeded", "succeeded"]
    assert result["technical_preview"]["bar_count"] == 2
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

    assert result["source_records"] == [
        {
            "ticker": "AAPL",
            "source_family": "events_news",
            "source": "fixture",
            "source_table": "event_news_items",
            "source_record_id": result["source_records"][0]["source_record_id"],
            "event_time": "2026-06-01T10:30:00+00:00",
            "published_at": "2026-06-01T10:30:00+00:00",
            "ingested_at": "2026-06-01T12:00:00+00:00",
            "available_for_decision_at": "2026-06-01T12:00:00+00:00",
            "payload": {
                "direction": "positive",
                "event_type": "analyst_upgrade",
                "headline": "Apple upgraded after demand check",
                "importance": "high",
                "sentiment": "positive",
                "signal_type": "analyst_rating",
                "source_ticker": "AAPL",
                "summary": "Analyst raises rating.",
            },
        }
    ]
