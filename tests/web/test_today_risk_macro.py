from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.trading.events.calendar import CalendarEventRecord
from src.trading.events.risk import PortfolioEventRiskAssessmentRecord
from src.trading.macro.context import MacroSnapshotRecord
from src.web.presenters.today_risk_macro import build_today_risk_macro_payload


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
    assert payload["summary"]["top_risk_sources"][0]["label"] == "Own event window"
    assert payload["macro"]["blocked_strategy_tags"] == ("gap_and_go_v1",)
    assert payload["events"][0]["affected_ticker"] == "AAPL"
    assert payload["events"][0]["scheduled_at"] == "Jun 16, 2026"
    assert payload["risk_sources"][0]["recommended_action_label"] == "Block New Entry"
    assert payload["command_center"]["exposure_usage_pct"] == 42.0


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

    assert payload["events"][0]["scheduled_at"] == "Jul 31, 2026"


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
