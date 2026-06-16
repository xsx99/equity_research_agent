from datetime import datetime, timedelta, timezone

from src.trading.signals.social_macro import build_social_macro_signals
from src.trading.signals.sources import SourceRecord


def _social_macro_record(
    *,
    source_record_id: str,
    category: str,
    published_at: datetime,
    importance_score: float,
    sentiment_direction: str | None,
    explicit_ticker_mention_flag: bool = False,
    explicit_theme_mention_flag: bool = False,
    policy_headwind_flag: bool = False,
    policy_tailwind_flag: bool = False,
) -> SourceRecord:
    return SourceRecord(
        ticker="NVDA",
        source_family="social_macro",
        source="fixture",
        source_table="social_macro_items",
        source_record_id=source_record_id,
        event_time=published_at,
        published_at=published_at,
        ingested_at=published_at,
        available_for_decision_at=published_at,
        payload={
            "category": category,
            "importance_score": importance_score,
            "sentiment_direction": sentiment_direction,
            "explicit_ticker_mention_flag": explicit_ticker_mention_flag,
            "explicit_theme_mention_flag": explicit_theme_mention_flag,
            "policy_headwind_flag": policy_headwind_flag,
            "policy_tailwind_flag": policy_tailwind_flag,
        },
    )


def test_build_social_macro_signals_aggregates_ticker_and_theme_mentions():
    decision_time = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)
    two_hours_ago = decision_time - timedelta(hours=2)
    five_hours_ago = decision_time - timedelta(hours=5)
    thirty_hours_ago = decision_time - timedelta(hours=30)

    signals = build_social_macro_signals(
        (
            _social_macro_record(
                source_record_id="trump",
                category="trump_update",
                published_at=two_hours_ago,
                importance_score=0.9,
                sentiment_direction="negative",
                explicit_ticker_mention_flag=True,
                policy_headwind_flag=True,
            ),
            _social_macro_record(
                source_record_id="official",
                category="official_update",
                published_at=five_hours_ago,
                importance_score=0.7,
                sentiment_direction="positive",
                explicit_theme_mention_flag=True,
                policy_tailwind_flag=True,
            ),
            _social_macro_record(
                source_record_id="geo-old",
                category="geopolitical_news",
                published_at=thirty_hours_ago,
                importance_score=0.6,
                sentiment_direction="negative",
                policy_headwind_flag=True,
            ),
        ),
        decision_time=decision_time,
    )

    assert signals.values["trump_update_count_24h"] == 1
    assert signals.values["official_update_count_24h"] == 1
    assert signals.values["geopolitical_risk_count_24h"] == 0
    assert signals.values["social_macro_sentiment_direction"] == "neutral"
    assert signals.values["policy_headwind_flag"] is True
    assert signals.values["policy_tailwind_flag"] is True
    assert signals.values["explicit_ticker_mention_flag"] is True
    assert signals.values["explicit_theme_mention_flag"] is True
    assert signals.values["social_macro_importance_score"] == 0.9
    assert signals.values["latest_social_macro_category"] == "trump_update"
    assert signals.values["latest_social_macro_published_at"] == two_hours_ago.isoformat()

