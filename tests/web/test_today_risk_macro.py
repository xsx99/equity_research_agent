from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.trading.events.calendar import CalendarEventRecord
from src.trading.events.risk import PortfolioEventRiskAssessmentRecord
from src.trading.macro.context import MacroSnapshotRecord
from src.trading.signals.sources import EventNewsItemRecord, SocialMacroItemRecord
from src.web.presenters.today_risk_macro import build_today_risk_macro_payload


def _calendar_event(
    *,
    event_id: str,
    event_type: str,
    ticker: str | None,
    event_time: datetime,
    as_of: datetime,
    title: str,
    severity: str = "high",
) -> CalendarEventRecord:
    event_key_ticker = ticker or "macro"
    return CalendarEventRecord(
        calendar_event_id=event_id,
        event_key=f"{event_type}:{event_key_ticker}:{event_time.date().isoformat()}:{event_id}",
        event_type=event_type,
        ticker=ticker,
        event_time=event_time,
        published_at=as_of,
        available_for_decision_at=as_of,
        title=title,
        severity_hint=severity,
        source="fixture",
        metadata_json={},
    )


def _macro_news_item(
    *,
    item_id: str,
    ticker: str,
    title: str,
    summary: str,
    available_at: datetime,
    provider: str = "alpaca_live",
) -> SocialMacroItemRecord:
    return SocialMacroItemRecord(
        social_macro_item_id=item_id,
        ticker=ticker,
        category="geopolitical_news",
        source_type="news",
        source_key="geopolitical_news",
        provider=provider,
        title=title,
        summary=summary,
        direction=None,
        sentiment_direction=None,
        importance_score=0.5,
        importance_label="medium",
        policy_headwind_flag=False,
        policy_tailwind_flag=False,
        explicit_ticker_mention_flag=True,
        explicit_theme_mention_flag=False,
        theme_tags_json=[],
        company_name_mentions_json=[],
        source_refs_json=[],
        dedupe_key=f"{item_id}:{ticker}",
        event_time=available_at,
        published_at=available_at,
        ingested_at=available_at,
        available_for_decision_at=available_at,
        raw_payload_ref=None,
        metadata_json={},
    )


def _event_news_item(
    *,
    item_id: str,
    ticker: str,
    headline: str,
    summary: str,
    available_at: datetime,
    provider: str = "alpaca_live",
) -> EventNewsItemRecord:
    return EventNewsItemRecord(
        event_news_item_id=item_id,
        ticker=ticker,
        source_ticker=None,
        event_type="company_specific",
        direction=None,
        sentiment=None,
        importance="high",
        headline=headline,
        summary=summary,
        provider=provider,
        source_refs_json=[],
        dedupe_key=f"{item_id}:{ticker}",
        event_time=available_at,
        published_at=available_at,
        ingested_at=available_at,
        available_for_decision_at=available_at,
        raw_payload_ref=None,
        metadata_json={},
    )


def test_today_risk_macro_presenter_builds_command_center_from_canonical_rows():
    decision_time = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    macro_snapshot = MacroSnapshotRecord(
        macro_snapshot_id="macro-1",
        snapshot_time=decision_time,
        trade_date=date(2026, 6, 16),
        regime="risk_off",
        risk_budget_multiplier=0.5,
        volatility_state="elevated",
        rates_state="stable",
        liquidity_state="ample",
        blocked_strategy_tags=("gap_and_go_v1",),
        invalidators=("macro_risk_off",),
        source_freshness={"global_context": {"status": "fresh"}},
        metadata_json={
            "basis_note": "risk_off, volatility=elevated",
            "favored_exposures": ["defensive_quality"],
            "availability_issues": [],
            "indicators": {
                "vix": {
                    "label": "CBOE Volatility Index",
                    "unit": "index",
                    "value": 17.01,
                    "previous_close": 16.5,
                    "return_vs_previous_close": 0.030909,
                    "observed_on": "2026-07-21",
                },
                "oil_price": {
                    "label": "WTI Crude Oil Spot Price",
                    "unit": "USD/bbl",
                    "value": 79.2,
                    "previous_close": 78.4,
                    "return_vs_previous_close": 0.010204,
                    "observed_on": "2026-07-13",
                },
                "gold_price": {
                    "label": "Gold Proxy (GLD ETF)",
                    "unit": "USD/share",
                    "value": 374.42,
                    "previous_close": 370.0,
                    "return_vs_previous_close": 0.011946,
                    "observed_on": "2026-07-21",
                },
                "us_treasury_10y": {
                    "label": "US Treasury 10Y",
                    "unit": "pct",
                    "value": 4.55,
                    "previous_close": 4.5,
                    "return_vs_previous_close": 0.011111,
                    "observed_on": "2026-07-17",
                },
            },
        },
    )
    event = CalendarEventRecord(
        calendar_event_id="event-1",
        event_key="earnings:AAPL:2026-06-16",
        event_type="earnings",
        ticker="AAPL",
        event_time=decision_time,
        published_at=decision_time,
        available_for_decision_at=decision_time,
        title="AAPL earnings",
        severity_hint="high",
        source="fixture",
        metadata_json={},
    )
    assessment = PortfolioEventRiskAssessmentRecord(
        portfolio_event_risk_assessment_id="assessment-1",
        calendar_event_id="event-1",
        portfolio_risk_snapshot_id="risk-1",
        decision_time=decision_time,
        available_for_decision_at=decision_time,
        ticker="AAPL",
        risk_source="own_event",
        severity="high",
        event_type="earnings",
        days_until_event=0,
        affects_existing_position=False,
        affects_pending_trade=True,
        recommended_action="block_open",
        rationale="AAPL earnings maps to own_event risk within 0 day(s).",
        metadata_json={"why_visible": "pending_trade", "summary_bucket": "own_event"},
    )
    latest_intent = SimpleNamespace(
        aggregate_risk_state="macro_high_risk",
        binding_constraints=("own_event_block", "macro_high_overlay"),
        metadata_json={
            "top_risk_sources": ("own_event", "macro"),
            "hedge_posture": {
                "action": "open_hedge",
                "risk_source": "macro",
                "target_underlier": "QQQ",
                "coverage_ratio": 0.5,
                "severity": "high",
            },
            "data_availability_issues": (),
        },
    )
    latest_risk = SimpleNamespace(
        risk_appetite="balanced",
        resolver_version="risk_config_resolver_v1",
        gross_exposure=0.42,
        decision_time=decision_time,
    )

    payload = build_today_risk_macro_payload(
        latest_risk=latest_risk,
        latest_intent=latest_intent,
        risk_macro_context={
            "macro_snapshot": macro_snapshot,
            "calendar_events": (event,),
            "portfolio_event_risk_assessments": (assessment,),
        },
        exposures=({"factor_type": "sector", "factor_name": "Technology", "exposure": 5.2757},),
    )

    assert payload["command_center"]["regime"] == "Risk Off"
    assert payload["command_center"]["risk_appetite_label"] == "Balanced"
    assert payload["command_center"]["event_risk_level"] == "High"
    assert payload["command_center"]["hedge_posture"]["target_underlier"] == "QQQ"
    assert payload["summary"]["risk_status"] == "Macro High Risk"
    assert payload["summary"]["top_risk_sources"][0]["label"] == "Technology event risk"
    assert payload["summary"]["top_risk_sources"][0]["summary"] == (
        "High-impact portfolio events are driving tactical caution."
    )
    assert payload["macro"]["blocked_strategy_tags"] == ("gap_and_go_v1",)
    assert payload["events"][0]["affected_ticker"] == "AAPL"
    assert payload["events"][0]["scheduled_at"] == decision_time
    assert payload["events"][0]["scheduled_at_label"] == "Jun 16, 2026"
    assert payload["risk_sources"][0]["recommended_action_label"] == "Block New Entry"
    assert payload["command_center"]["exposure_usage_pct"] == 42.0
    assert tuple(row["key"] for row in payload["macro_indicators"]) == (
        "vix",
        "oil_price",
        "gold_price",
        "us_treasury_10y",
    )
    assert payload["macro_indicators"][0]["display_value"] == "17.01 index"
    assert payload["macro_indicators"][0]["return_label"] == "+3.09% vs prev close"
    assert payload["macro_indicators"][2]["return_label"] == "+1.19% vs prev close"
    assert payload["macro_indicators"][3]["return_label"] is None


def test_today_risk_macro_presenter_formats_event_dates_without_raw_timestamps():
    decision_time = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    event = CalendarEventRecord(
        calendar_event_id="event-earnings",
        event_key="earnings:AAPL:2026-07-31",
        event_type="earnings",
        ticker="AAPL",
        event_time=datetime(2026, 7, 31, 20, 0, 12, 123456, tzinfo=timezone.utc),
        published_at=decision_time,
        available_for_decision_at=decision_time,
        title="AAPL earnings",
        severity_hint="high",
        source="fixture",
        metadata_json={},
    )

    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=None,
        risk_macro_context={"calendar_events": (event,)},
        exposures=(),
    )

    assert payload["events"][0]["scheduled_at"] == datetime(2026, 7, 31, 20, 0, 12, 123456, tzinfo=timezone.utc)
    assert payload["events"][0]["scheduled_at_label"] == "Jul 31, 2026"


def test_today_risk_macro_presenter_formats_decision_visible_news_rows():
    decision_time = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    macro_news = SocialMacroItemRecord(
        social_macro_item_id="macro-news-1",
        ticker="NVDA",
        category="geopolitical_news",
        source_type="news",
        source_key="geopolitical_news",
        provider="global_context",
        title="Export-control update hits semis",
        summary="Policy risk is fresh for chip names.",
        direction="negative",
        sentiment_direction="negative",
        importance_score=0.8,
        importance_label="high",
        policy_headwind_flag=True,
        policy_tailwind_flag=False,
        explicit_ticker_mention_flag=True,
        explicit_theme_mention_flag=True,
        theme_tags_json=["semiconductors"],
        company_name_mentions_json=["NVIDIA"],
        source_refs_json=[],
        dedupe_key="macro-visible",
        event_time=decision_time,
        published_at=decision_time,
        ingested_at=decision_time,
        available_for_decision_at=decision_time,
        raw_payload_ref=None,
        metadata_json={},
    )
    event_news = EventNewsItemRecord(
        event_news_item_id="event-news-1",
        ticker="NVDA",
        source_ticker=None,
        event_type="company_specific",
        direction="negative",
        sentiment="negative",
        importance="high",
        headline="NVIDIA export restriction update",
        summary="Fresh headline raises event risk.",
        provider="alpaca",
        source_refs_json=[],
        dedupe_key="event-visible",
        event_time=decision_time,
        published_at=decision_time,
        ingested_at=decision_time,
        available_for_decision_at=decision_time,
        raw_payload_ref=None,
        metadata_json={},
    )

    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=None,
        risk_macro_context={"macro_news": (macro_news,), "event_news": (event_news,)},
        exposures=(),
    )

    assert payload["macro_news"] == (
        {
            "news_id": "macro-news-1",
            "ticker": "NVDA",
            "category": "Geopolitical News",
            "title": "Export-control update hits semis",
            "headline": "Export-control update hits semis",
            "summary": "Policy risk is fresh for chip names.",
            "source": "global_context",
            "sentiment": "negative",
            "importance": "high",
            "time": decision_time,
        },
    )
    assert payload["event_news"][0]["news_id"] == "event-news-1"
    assert payload["event_news"][0]["headline"] == "NVIDIA export restriction update"
    assert payload["event_news"][0]["category"] == "Company Specific"


def test_today_risk_macro_presenter_filters_dedupes_and_sorts_recent_news_by_as_of_date():
    as_of = datetime(2026, 7, 18, 17, 0, tzinfo=timezone.utc)
    repeated_title = "Russian strikes kill 4 in Ukraine as Zelenskyy's defense shake-up sparks anger"
    repeated_summary = "Russian attacks overnight on Ukraine killed at least four civilians and wounded 20."

    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=None,
        risk_macro_context={
            "macro_news": (
                _macro_news_item(
                    item_id="old-macro",
                    ticker="XOM",
                    title="Four-day-old macro item",
                    summary="Outside the requested display window.",
                    available_at=datetime(2026, 7, 14, 23, 0, tzinfo=timezone.utc),
                ),
                _macro_news_item(
                    item_id="duplicate-older",
                    ticker="XOM",
                    title=repeated_title,
                    summary=repeated_summary,
                    available_at=datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
                ),
                _macro_news_item(
                    item_id="today",
                    ticker="SPY",
                    title="Fed official flags patient policy path",
                    summary="Today macro headline should lead the list.",
                    available_at=datetime(2026, 7, 18, 9, 0, tzinfo=timezone.utc),
                ),
                _macro_news_item(
                    item_id="duplicate-newer",
                    ticker="XLY",
                    title=repeated_title,
                    summary=repeated_summary,
                    available_at=datetime(2026, 7, 17, 13, 0, tzinfo=timezone.utc),
                ),
                _macro_news_item(
                    item_id="boundary",
                    ticker="QQQ",
                    title="Three-day boundary macro item",
                    summary="This row is still in the requested window.",
                    available_at=datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc),
                ),
            ),
            "event_news": (
                _event_news_item(
                    item_id="old-event",
                    ticker="IBM",
                    headline="Outdated event headline",
                    summary="Outside the requested display window.",
                    available_at=datetime(2026, 7, 14, 20, 0, tzinfo=timezone.utc),
                ),
                _event_news_item(
                    item_id="event-duplicate-older",
                    ticker="IBM",
                    headline="Dividend story repeats across tickers",
                    summary="The same event story should collapse across symbols.",
                    available_at=datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc),
                ),
                _event_news_item(
                    item_id="event-today",
                    ticker="AAPL",
                    headline="Today company headline",
                    summary="Fresh event headline should lead the event list.",
                    available_at=datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc),
                ),
                _event_news_item(
                    item_id="event-duplicate-newer",
                    ticker="D",
                    headline="Dividend story repeats across tickers",
                    summary="The same event story should collapse across symbols.",
                    available_at=datetime(2026, 7, 17, 11, 0, tzinfo=timezone.utc),
                ),
            ),
        },
        exposures=(),
        as_of=as_of,
    )

    assert [row["title"] for row in payload["macro_news"]] == [
        "Fed official flags patient policy path",
        repeated_title,
        "Three-day boundary macro item",
    ]
    assert payload["macro_news"][1]["ticker"] == "XLY"
    assert "Four-day-old macro item" not in {row["title"] for row in payload["macro_news"]}
    assert [row["headline"] for row in payload["event_news"]] == [
        "Today company headline",
        "Dividend story repeats across tickers",
    ]
    assert payload["event_news"][1]["ticker"] == "D"
    assert "Outdated event headline" not in {row["headline"] for row in payload["event_news"]}


def test_today_risk_macro_presenter_keeps_latest_refreshed_earnings_per_ticker():
    as_of = datetime(2026, 7, 24, 20, 0, tzinfo=timezone.utc)
    stale_near_event = CalendarEventRecord(
        calendar_event_id="event-stale-near",
        event_key="earnings:AAPL:2026-07-29",
        event_type="earnings",
        ticker="AAPL",
        event_time=datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc),
        published_at=as_of.replace(hour=19),
        available_for_decision_at=as_of.replace(hour=19),
        title="AAPL earnings",
        severity_hint="high",
        source="fixture",
        metadata_json={},
    )
    latest_event = CalendarEventRecord(
        calendar_event_id="event-latest",
        event_key="earnings:AAPL:2026-07-30",
        event_type="earnings",
        ticker="AAPL",
        event_time=datetime(2026, 7, 30, 20, 0, tzinfo=timezone.utc),
        published_at=as_of,
        available_for_decision_at=as_of,
        title="AAPL earnings",
        severity_hint="high",
        source="fixture",
        metadata_json={},
    )

    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=None,
        risk_macro_context={"calendar_events": (stale_near_event, latest_event)},
        exposures=(),
        as_of=as_of,
    )

    assert [event["scheduled_at_label"] for event in payload["events"]] == ["Jul 30, 2026"]


def test_today_risk_macro_presenter_sorts_visible_events_by_date():
    as_of = datetime(2026, 7, 4, 20, 0, tzinfo=timezone.utc)
    later_event = CalendarEventRecord(
        calendar_event_id="event-later",
        event_key="earnings:AMD:2026-07-10",
        event_type="earnings",
        ticker="AMD",
        event_time=datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc),
        published_at=as_of,
        available_for_decision_at=as_of,
        title="AMD earnings",
        severity_hint="high",
        source="fixture",
        metadata_json={},
    )
    earlier_event = CalendarEventRecord(
        calendar_event_id="event-earlier",
        event_key="earnings:GOOGL:2026-07-06",
        event_type="earnings",
        ticker="GOOGL",
        event_time=datetime(2026, 7, 6, 20, 0, tzinfo=timezone.utc),
        published_at=as_of,
        available_for_decision_at=as_of,
        title="GOOGL earnings",
        severity_hint="high",
        source="fixture",
        metadata_json={},
    )

    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=None,
        risk_macro_context={"calendar_events": (later_event, earlier_event)},
        exposures=(),
        as_of=as_of,
    )

    assert [event["affected_ticker"] for event in payload["events"]] == ["GOOGL", "AMD"]


def test_today_risk_macro_presenter_limits_earnings_to_one_week_from_as_of():
    as_of = datetime(2026, 7, 18, 20, 0, tzinfo=timezone.utc)
    today_earnings = _calendar_event(
        event_id="event-fitb",
        event_type="earnings",
        ticker="FITB",
        event_time=datetime(2026, 7, 18, 20, 0, tzinfo=timezone.utc),
        as_of=as_of,
        title="FITB earnings",
    )
    one_week_earnings = _calendar_event(
        event_id="event-cof",
        event_type="earnings",
        ticker="COF",
        event_time=datetime(2026, 7, 25, 20, 0, tzinfo=timezone.utc),
        as_of=as_of,
        title="COF earnings",
    )
    later_earnings = _calendar_event(
        event_id="event-bkr",
        event_type="earnings",
        ticker="BKR",
        event_time=datetime(2026, 7, 26, 20, 0, tzinfo=timezone.utc),
        as_of=as_of,
        title="BKR earnings",
    )
    later_macro_event = _calendar_event(
        event_id="event-cpi",
        event_type="macro",
        ticker=None,
        event_time=datetime(2026, 8, 3, 13, 30, tzinfo=timezone.utc),
        as_of=as_of,
        title="US CPI",
        severity="medium",
    )

    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=None,
        risk_macro_context={"calendar_events": (later_earnings, later_macro_event, one_week_earnings, today_earnings)},
        exposures=(),
        as_of=as_of,
    )

    assert [event["affected_ticker"] for event in payload["events"] if event["event_type"] == "earnings"] == [
        "FITB",
        "COF",
    ]
    assert "BKR" not in {event["affected_ticker"] for event in payload["events"]}
    assert [event["risk_mechanism"] for event in payload["events"] if event["event_type"] == "macro"] == ["US CPI"]


def test_today_risk_macro_presenter_exposes_assessment_fields_needed_to_filter_earnings_actions():
    decision_time = datetime(2026, 7, 4, 20, 0, tzinfo=timezone.utc)
    own_event = PortfolioEventRiskAssessmentRecord(
        portfolio_event_risk_assessment_id="assessment-own-event",
        calendar_event_id="event-aapl",
        portfolio_risk_snapshot_id="risk-1",
        decision_time=decision_time,
        available_for_decision_at=decision_time,
        ticker="AAPL",
        risk_source="own_event",
        severity="high",
        event_type="earnings",
        days_until_event=26,
        affects_existing_position=False,
        affects_pending_trade=True,
        recommended_action="monitor",
        rationale="AAPL earnings maps to own_event risk within 26 day(s).",
        metadata_json={},
    )
    news_event = PortfolioEventRiskAssessmentRecord(
        portfolio_event_risk_assessment_id="assessment-news",
        calendar_event_id="event-news",
        portfolio_risk_snapshot_id="risk-1",
        decision_time=decision_time,
        available_for_decision_at=decision_time,
        ticker="AAPL",
        risk_source="company_specific",
        severity="medium",
        event_type="company_specific",
        days_until_event=0,
        affects_existing_position=False,
        affects_pending_trade=True,
        recommended_action="review_position",
        rationale="News headline should not render inside the earnings tile.",
        metadata_json={},
    )

    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=None,
        risk_macro_context={"portfolio_event_risk_assessments": (own_event, news_event)},
        exposures=(),
    )

    assert payload["risk_sources"][0]["calendar_event_id"] == "event-aapl"
    assert payload["risk_sources"][0]["event_type"] == "earnings"
    assert payload["risk_sources"][0]["days_until_event"] == 26
    assert payload["risk_sources"][1]["risk_source"] == "company_specific"


def test_today_risk_macro_presenter_hides_past_events_when_as_of_is_provided():
    as_of = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    past_event = CalendarEventRecord(
        calendar_event_id="event-past",
        event_key="macro:cpi:2026-06-16",
        event_type="macro",
        ticker=None,
        event_time=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
        published_at=as_of,
        available_for_decision_at=as_of,
        title="US CPI",
        severity_hint="high",
        source="fixture",
        metadata_json={},
    )
    current_event = CalendarEventRecord(
        calendar_event_id="event-now",
        event_key="macro:fomc:2026-06-16",
        event_type="macro",
        ticker=None,
        event_time=as_of,
        published_at=as_of,
        available_for_decision_at=as_of,
        title="FOMC",
        severity_hint="high",
        source="fixture",
        metadata_json={},
    )
    future_event = CalendarEventRecord(
        calendar_event_id="event-future",
        event_key="earnings:MU:2026-06-23",
        event_type="earnings",
        ticker="MU",
        event_time=datetime(2026, 6, 23, 20, 0, tzinfo=timezone.utc),
        published_at=as_of,
        available_for_decision_at=as_of,
        title="MU earnings",
        severity_hint="high",
        source="fixture",
        metadata_json={},
    )

    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=None,
        risk_macro_context={"calendar_events": (past_event, current_event, future_event)},
        exposures=(),
        as_of=as_of,
    )
    legacy_payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=None,
        risk_macro_context={"calendar_events": (past_event, current_event, future_event)},
        exposures=(),
    )

    assert [event["risk_mechanism"] for event in payload["events"]] == ["FOMC", "MU earnings"]
    assert [event["risk_mechanism"] for event in legacy_payload["events"]] == ["US CPI", "FOMC", "MU earnings"]


def test_today_risk_macro_presenter_converts_notional_gross_exposure_to_equity_percentage():
    decision_time = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    latest_risk = SimpleNamespace(
        risk_appetite="balanced",
        resolver_version="risk_config_resolver_v1",
        gross_exposure=49170.6164,
        account_equity=1_000_000.0,
        decision_time=decision_time,
    )

    payload = build_today_risk_macro_payload(
        latest_risk=latest_risk,
        latest_intent=None,
        risk_macro_context={},
        exposures=(),
    )

    assert payload["command_center"]["exposure_usage_pct"] == 4.92


def test_today_risk_macro_presenter_turns_own_event_source_into_portfolio_risk():
    decision_time = datetime(2026, 7, 4, 20, 0, tzinfo=timezone.utc)
    latest_intent = SimpleNamespace(
        aggregate_risk_state="risk_normalized",
        binding_constraints=("own_event_block",),
        metadata_json={"top_risk_sources": ("own_event",)},
    )
    assessment = PortfolioEventRiskAssessmentRecord(
        portfolio_event_risk_assessment_id="assessment-nvda",
        calendar_event_id="event-nvda",
        portfolio_risk_snapshot_id="risk-1",
        decision_time=decision_time,
        available_for_decision_at=decision_time,
        ticker="NVDA",
        risk_source="own_event",
        severity="high",
        event_type="earnings",
        days_until_event=0,
        affects_existing_position=True,
        affects_pending_trade=False,
        recommended_action="block_open",
        rationale="NVDA earnings maps to own_event risk within 0 day(s).",
        metadata_json={},
    )

    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=latest_intent,
        risk_macro_context={"portfolio_event_risk_assessments": (assessment,)},
        exposures=({"factor_type": "sector", "factor_name": "Semiconductors", "exposure": 0.35},),
    )

    assert payload["summary"]["top_risk_sources"] == (
        {
            "label": "Semiconductors event risk",
            "summary": "High-impact portfolio events are driving tactical caution.",
        },
    )


def test_today_risk_macro_presenter_ignores_directional_exposure_names_for_event_risk():
    latest_intent = SimpleNamespace(
        aggregate_risk_state="risk_normalized",
        binding_constraints=(),
        metadata_json={"top_risk_sources": ("own_event",)},
    )

    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=latest_intent,
        risk_macro_context={},
        exposures=({"factor_type": "direction", "factor_name": "long", "exposure": 0.35},),
    )

    assert payload["summary"]["top_risk_sources"][0]["label"] == "Portfolio event risk"


def test_today_risk_macro_presenter_marks_missing_macro_as_availability_issue():
    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=None,
        risk_macro_context={},
        exposures=(),
    )

    assert payload["command_center"]["regime"] == "Unavailable"
    assert payload["summary"]["availability_issues"] == (
        {
            "label": "Macro regime unavailable",
            "summary": "Global macro regime data is unavailable.",
        },
    )


def test_today_risk_macro_presenter_dedupes_accumulated_audit_rows():
    older = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 6, 16, 14, 0, tzinfo=timezone.utc)
    stale_event = CalendarEventRecord(
        calendar_event_id="event-stale",
        event_key="earnings:GOOGL:2026-06-22",
        event_type="earnings",
        ticker="GOOGL",
        event_time=datetime(2026, 6, 22, 20, 0, tzinfo=timezone.utc),
        published_at=older,
        available_for_decision_at=older,
        title="GOOGL earnings within 6 day(s)",
        severity_hint="high",
        source="fixture",
        metadata_json={},
    )
    latest_event = CalendarEventRecord(
        calendar_event_id="event-latest",
        event_key="earnings:GOOGL:2026-06-21",
        event_type="earnings",
        ticker="GOOGL",
        event_time=datetime(2026, 6, 21, 20, 0, tzinfo=timezone.utc),
        published_at=newer,
        available_for_decision_at=newer,
        title="GOOGL earnings within 5 day(s)",
        severity_hint="high",
        source="fixture",
        metadata_json={},
    )
    stale_assessment = PortfolioEventRiskAssessmentRecord(
        portfolio_event_risk_assessment_id="assessment-stale",
        calendar_event_id="event-stale",
        portfolio_risk_snapshot_id="risk-1",
        decision_time=older,
        available_for_decision_at=older,
        ticker="NVDA",
        risk_source="company_specific",
        severity="medium",
        event_type="readthrough",
        days_until_event=0,
        affects_existing_position=False,
        affects_pending_trade=True,
        recommended_action="monitor",
        rationale="NVDA monitor duplicate from older run.",
        metadata_json={},
    )
    latest_assessment = PortfolioEventRiskAssessmentRecord(
        portfolio_event_risk_assessment_id="assessment-latest",
        calendar_event_id="event-latest",
        portfolio_risk_snapshot_id="risk-1",
        decision_time=newer,
        available_for_decision_at=newer,
        ticker="NVDA",
        risk_source="company_specific",
        severity="medium",
        event_type="readthrough",
        days_until_event=0,
        affects_existing_position=False,
        affects_pending_trade=True,
        recommended_action="monitor",
        rationale="NVDA monitor duplicate from latest run.",
        metadata_json={},
    )

    payload = build_today_risk_macro_payload(
        latest_risk=None,
        latest_intent=None,
        risk_macro_context={
            "calendar_events": (stale_event, latest_event),
            "portfolio_event_risk_assessments": (stale_assessment, latest_assessment),
        },
        exposures=(),
        as_of=older,
    )

    assert [event["risk_mechanism"] for event in payload["events"]] == ["GOOGL earnings within 5 day(s)"]
    assert [row["rationale"] for row in payload["risk_sources"]] == ["NVDA monitor duplicate from latest run."]
