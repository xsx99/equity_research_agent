from datetime import date, datetime, timedelta, timezone

import pytest

from src.trading.events import CalendarEventPipeline, CalendarEventRecord, PortfolioEventRiskAssessmentPipeline, PortfolioEventRiskAssessmentRecord
from src.trading.macro import MacroReadthroughEventRecord
from src.trading.risk.context import PortfolioContext, PortfolioPosition


def test_calendar_event_record_preserves_decision_available_fields():
    event_time = datetime(2026, 6, 17, 18, 0, tzinfo=timezone.utc)
    record = CalendarEventRecord(
        calendar_event_id="calendar-1",
        event_key="earnings:AAPL:2026-06-17",
        event_type="earnings",
        ticker="aapl",
        event_time=event_time,
        published_at=event_time,
        available_for_decision_at=event_time,
        title="Apple earnings",
        severity_hint="high",
        source="fixture",
        metadata_json={"source_family": "events_news"},
    )

    assert record.ticker == "AAPL"
    assert record.available_for_decision_at == event_time


def test_calendar_event_record_rejects_invalid_availability():
    with pytest.raises(ValueError, match="available_for_decision_at"):
        CalendarEventRecord(
            calendar_event_id="calendar-1",
            event_key="earnings:AAPL:2026-06-17",
            event_type="earnings",
            ticker="AAPL",
            event_time=datetime(2026, 6, 17, 18, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 17, 18, 5, tzinfo=timezone.utc),
            available_for_decision_at=datetime(2026, 6, 17, 18, 4, tzinfo=timezone.utc),
            title="Apple earnings",
            severity_hint="high",
            source="fixture",
            metadata_json={},
        )


def test_portfolio_event_risk_assessment_record_supports_persisted_contract_fields():
    available = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    record = PortfolioEventRiskAssessmentRecord(
        portfolio_event_risk_assessment_id="assessment-1",
        calendar_event_id="calendar-1",
        portfolio_risk_snapshot_id="risk-snapshot-1",
        decision_time=available,
        available_for_decision_at=available,
        ticker="qqq",
        risk_source="macro",
        severity="high",
        event_type="macro",
        days_until_event=1,
        affects_existing_position=True,
        affects_pending_trade=True,
        recommended_action="tighten_risk",
        rationale="FOMC is inside the current risk window.",
        metadata_json={"summary_bucket": "macro_event"},
    )

    assert record.ticker == "QQQ"
    assert record.recommended_action == "tighten_risk"
    assert record.rationale == "FOMC is inside the current risk window."


def test_event_calendar_pipeline_normalizes_earnings_macro_option_and_readthrough_events():
    decision_time = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    pipeline = CalendarEventPipeline(now=lambda: decision_time)

    events = pipeline.build_events(
        ticker="NVDA",
        decision_time=decision_time,
        earnings_in_days=2,
        macro_events=(
            {
                "event_code": "fomc",
                "event_time": decision_time + timedelta(days=1),
                "title": "FOMC rate decision",
                "severity_hint": "critical",
                "source": "fed_calendar",
            },
        ),
        option_expiry_dates=(decision_time.date() + timedelta(days=4),),
        company_event_payloads=(
            {
                "event_type": "regulatory_action",
                "published_at": decision_time,
                "title": "GPU export review escalates",
                "severity_hint": "high",
                "source": "fixture_news",
            },
        ),
        readthrough_events=(
            MacroReadthroughEventRecord(
                macro_readthrough_event_id="readthrough-1",
                event_key="readthrough:nvda:avgo:2026-06-16",
                source_ticker="NVDA",
                affected_ticker="AVGO",
                scope="peer",
                mechanism="earnings_readthrough",
                direction="negative",
                title="NVDA read-through pressures AVGO",
                source="fixture",
                event_time=decision_time,
                published_at=decision_time,
                available_for_decision_at=decision_time,
                valid_until=decision_time + timedelta(days=5),
                metadata_json={"relationship_context": "peer"},
            ),
        ),
    )

    assert [event.event_type for event in events] == [
        "company_specific",
        "readthrough",
        "earnings",
        "macro",
        "option_expiry",
    ]
    assert events[2].event_key == "earnings:NVDA:2026-06-18"
    assert events[3].event_key == "macro:fomc:2026-06-17"
    assert events[4].event_key == "option_expiry:NVDA:2026-06-20"


def test_event_calendar_pipeline_prefers_real_earnings_date_when_available():
    decision_time = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    pipeline = CalendarEventPipeline(now=lambda: decision_time)

    events = pipeline.build_events(
        ticker="AAPL",
        decision_time=decision_time,
        earnings_in_days=1,
        earnings_date=date(2026, 7, 31),
    )

    assert len(events) == 1
    assert events[0].event_type == "earnings"
    assert events[0].event_key == "earnings:AAPL:2026-07-31"
    assert events[0].event_time == datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)


def test_portfolio_event_risk_assessment_pipeline_scores_existing_position_pending_trade_and_hides_low_relevance():
    decision_time = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    portfolio = PortfolioContext(
        as_of=decision_time,
        account_equity=100_000.0,
        cash_balance=20_000.0,
        buying_power=150_000.0,
        excess_liquidity=40_000.0,
        positions=(
            PortfolioPosition(
                ticker="NVDA",
                quantity=100,
                market_value=25_000.0,
                notional_exposure=25_000.0,
                trade_identity="tactical_stock_trade",
                direction="long",
                sector="Technology",
                strategy_id="earnings_drift_v1",
                intended_horizon="1d-3d",
                beta_bucket="high",
                volatility_bucket="high",
                liquidity_bucket="liquid",
                event_type="earnings",
                macro_sensitivity="rates_sensitive",
                margin_requirement=12_500.0,
            ),
        ),
        open_strategy_exposure={},
        current_factor_exposure=(),
        stock_margin_requirement=12_500.0,
        option_margin_requirement=0.0,
        total_margin_requirement=12_500.0,
    )
    events = (
        CalendarEventRecord(
            calendar_event_id="calendar-earnings",
            event_key="earnings:NVDA:2026-06-18",
            event_type="earnings",
            ticker="NVDA",
            event_time=decision_time + timedelta(days=2),
            published_at=decision_time,
            available_for_decision_at=decision_time,
            title="NVIDIA earnings",
            severity_hint="high",
            source="fixture",
            metadata_json={},
        ),
        CalendarEventRecord(
            calendar_event_id="calendar-readthrough",
            event_key="readthrough:nvda:avgo:2026-06-16",
            event_type="readthrough",
            ticker="AVGO",
            event_time=decision_time + timedelta(days=1),
            published_at=decision_time,
            available_for_decision_at=decision_time,
            title="NVDA read-through pressures AVGO",
            severity_hint="medium",
            source="fixture",
            metadata_json={"relationship_context": "peer"},
        ),
        CalendarEventRecord(
            calendar_event_id="calendar-low",
            event_key="macro:low:2026-06-25",
            event_type="macro",
            ticker=None,
            event_time=decision_time + timedelta(days=9),
            published_at=decision_time,
            available_for_decision_at=decision_time,
            title="Low-impact calendar event",
            severity_hint="low",
            source="fixture",
            metadata_json={},
        ),
    )
    pipeline = PortfolioEventRiskAssessmentPipeline(now=lambda: decision_time)

    assessments = pipeline.build_assessments(
        calendar_events=events,
        portfolio_context=portfolio,
        pending_candidates=(
            {"ticker": "NVDA", "candidate_score_id": "candidate-nvda"},
            {"ticker": "AVGO", "candidate_score_id": "candidate-avgo"},
        ),
        decision_time=decision_time,
    )

    assert [assessment.risk_source for assessment in assessments] == ["own_event", "readthrough"]
    own_event = assessments[0]
    assert own_event.affects_existing_position is True
    assert own_event.affects_pending_trade is True
    assert own_event.recommended_action == "block_open"
    assert own_event.metadata_json["position_notional"] == 25_000.0
    assert own_event.metadata_json["candidate_score_id"] == "candidate-nvda"
    assert own_event.metadata_json["why_visible"] == "existing_position_and_pending_trade"
    assert own_event.metadata_json["default_visibility"] == "show"
    readthrough = assessments[1]
    assert readthrough.risk_source == "readthrough"
    assert readthrough.metadata_json["relationship_context"] == "peer"
