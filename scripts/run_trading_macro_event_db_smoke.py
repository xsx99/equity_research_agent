#!/usr/bin/env python3
"""Write and reload canonical macro/event risk rows through the live DB repository."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import config as app_config  # noqa: F401
from src.db.connection import SessionLocal, init_db
from src.db.models.trading import RiskFactorExposure
from src.trading.events import CalendarEventRecord, PortfolioEventRiskAssessmentRecord
from src.trading.macro import MacroSnapshotRecord
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
from src.trading.risk import PortfolioRiskIntentRecord, PortfolioRiskSnapshotRecord, RiskFactorExposureRecord
from src.web.presenters.today_risk_macro import build_today_risk_macro_payload


def run_smoke(
    *,
    as_of: datetime | None = None,
    session_factory: Callable[[], Any] = SessionLocal,
    init_schema: Callable[[], None] | None = init_db,
) -> dict[str, Any]:
    smoke_time = as_of or datetime.now(timezone.utc)
    trade_date = smoke_time.date()
    smoke_run_id = f"macro_event_db_smoke:{smoke_time.strftime('%Y%m%dT%H%M%S')}:{uuid.uuid4().hex[:8]}"

    macro_snapshot = MacroSnapshotRecord(
        macro_snapshot_id=str(uuid.uuid4()),
        snapshot_time=smoke_time,
        trade_date=trade_date,
        regime="risk_off",
        risk_budget_multiplier=0.5,
        volatility_state="elevated",
        rates_state="stable",
        liquidity_state="ample",
        blocked_strategy_tags=("gap_and_go_v1",),
        invalidators=("macro_risk_off",),
        source_freshness={"global_context": {"status": "fresh", "observed_on": trade_date.isoformat()}},
        metadata_json={
            "basis_note": "risk_off, volatility=elevated",
            "favored_exposures": ["defensive_quality"],
            "availability_issues": [],
            "smoke_run_id": smoke_run_id,
        },
    )
    risk_snapshot = PortfolioRiskSnapshotRecord.create(
        decision_time=smoke_time,
        risk_appetite="balanced",
        resolver_version="risk_config_resolver_v1",
        margin_model_profile="estimated_fidelity_like_conservative_v1",
        margin_model_version="v1",
        account_equity=250_000.0,
        cash_balance=90_000.0,
        buying_power=180_000.0,
        excess_liquidity=150_000.0,
        stock_margin_requirement=40_000.0,
        option_margin_requirement=5_000.0,
        total_margin_requirement=45_000.0,
        initial_margin_requirement=45_000.0,
        maintenance_margin_requirement=35_000.0,
        margin_requirement_source="estimated",
        net_exposure=0.18,
        gross_exposure=0.42,
        beta_adjusted_net_exposure=0.16,
        concentration_flags=["technology_cluster"],
        metadata_json={"smoke_run_id": smoke_run_id},
    )
    exposures = (
        RiskFactorExposureRecord(
            factor_type="sector",
            factor_value="Technology",
            gross_exposure=0.31,
            net_exposure=0.28,
            long_exposure=0.31,
            short_exposure=0.0,
            position_count=3,
            metadata_json={
                "portfolio_risk_snapshot_id": risk_snapshot.portfolio_risk_snapshot_id,
                "smoke_run_id": smoke_run_id,
            },
        ),
        RiskFactorExposureRecord(
            factor_type="theme",
            factor_value="AI Infrastructure",
            gross_exposure=0.22,
            net_exposure=0.22,
            long_exposure=0.22,
            short_exposure=0.0,
            position_count=2,
            metadata_json={
                "portfolio_risk_snapshot_id": risk_snapshot.portfolio_risk_snapshot_id,
                "smoke_run_id": smoke_run_id,
            },
        ),
    )
    calendar_events = (
        CalendarEventRecord(
            calendar_event_id=str(uuid.uuid4()),
            event_key=f"{smoke_run_id}:earnings:AAPL",
            event_type="earnings",
            ticker="AAPL",
            event_time=smoke_time + timedelta(hours=6),
            published_at=smoke_time,
            available_for_decision_at=smoke_time,
            title="AAPL earnings",
            severity_hint="high",
            source="macro_event_db_smoke",
            metadata_json={"smoke_run_id": smoke_run_id},
        ),
        CalendarEventRecord(
            calendar_event_id=str(uuid.uuid4()),
            event_key=f"{smoke_run_id}:macro:cpi",
            event_type="macro",
            ticker=None,
            event_time=smoke_time + timedelta(days=1),
            published_at=smoke_time,
            available_for_decision_at=smoke_time,
            title="US CPI",
            severity_hint="high",
            source="macro_event_db_smoke",
            metadata_json={"event_code": "cpi", "smoke_run_id": smoke_run_id},
        ),
    )
    event_assessments = (
        PortfolioEventRiskAssessmentRecord(
            portfolio_event_risk_assessment_id=str(uuid.uuid4()),
            calendar_event_id=calendar_events[0].calendar_event_id,
            portfolio_risk_snapshot_id=risk_snapshot.portfolio_risk_snapshot_id,
            decision_time=smoke_time,
            available_for_decision_at=smoke_time,
            ticker="AAPL",
            risk_source="own_event",
            severity="high",
            event_type="earnings",
            days_until_event=0,
            affects_existing_position=False,
            affects_pending_trade=True,
            recommended_action="block_open",
            rationale="AAPL earnings maps to own_event risk within 0 day(s).",
            metadata_json={
                "why_visible": "pending_trade",
                "summary_bucket": "own_event",
                "candidate_score_id": "smoke-candidate-aapl",
                "smoke_run_id": smoke_run_id,
            },
        ),
        PortfolioEventRiskAssessmentRecord(
            portfolio_event_risk_assessment_id=str(uuid.uuid4()),
            calendar_event_id=calendar_events[1].calendar_event_id,
            portfolio_risk_snapshot_id=risk_snapshot.portfolio_risk_snapshot_id,
            decision_time=smoke_time,
            available_for_decision_at=smoke_time,
            ticker="PORTFOLIO",
            risk_source="macro",
            severity="high",
            event_type="macro",
            days_until_event=1,
            affects_existing_position=True,
            affects_pending_trade=False,
            recommended_action="tighten_risk",
            rationale="US CPI maps to macro risk within 1 day(s).",
            metadata_json={
                "why_visible": "portfolio_context",
                "summary_bucket": "macro",
                "affected_exposure_theme": "Technology",
                "smoke_run_id": smoke_run_id,
            },
        ),
    )
    risk_intent = PortfolioRiskIntentRecord.create(
        decision_time=smoke_time,
        risk_window="open_to_close",
        aggregate_risk_state="macro_high_risk",
        portfolio_risk_snapshot_id=risk_snapshot.portfolio_risk_snapshot_id,
        binding_constraints=("own_event_block", "macro_high_overlay"),
        metadata_json={
            "macro_snapshot_id": macro_snapshot.macro_snapshot_id,
            "calendar_event_ids": [event.calendar_event_id for event in calendar_events],
            "portfolio_event_risk_assessment_ids": [
                assessment.portfolio_event_risk_assessment_id for assessment in event_assessments
            ],
            "top_risk_sources": ("own_event", "macro"),
            "hedge_posture": {
                "action": "open_hedge",
                "risk_source": "macro",
                "target_underlier": "QQQ",
                "coverage_ratio": 0.5,
                "severity": "high",
            },
            "data_availability_issues": (),
            "smoke_run_id": smoke_run_id,
        },
    )

    try:
        load_dotenv()
        if init_schema is not None:
            init_schema()
        with session_factory() as session:
            repository = SqlAlchemyTradingRepository(session)
            repository.save_portfolio_risk_snapshot(risk_snapshot)
            repository.save_risk_factor_exposures(exposures)
            repository.save_macro_snapshot(macro_snapshot)
            repository.save_calendar_events(calendar_events)
            repository.save_portfolio_event_risk_assessments(event_assessments)
            repository.save_portfolio_risk_intent(risk_intent)
            session.commit()

            loaded_macro = repository.load_latest_macro_snapshot(
                trade_date=trade_date,
                decision_time=smoke_time,
            )
            loaded_context = repository.load_decision_available_risk_macro_context(
                trade_date=trade_date,
                decision_time=smoke_time,
            )
            loaded_intents = repository.load_portfolio_risk_intents(trade_date=trade_date)
            latest_intent = next(
                (
                    item
                    for item in reversed(loaded_intents)
                    if item.metadata_json.get("smoke_run_id") == smoke_run_id
                ),
                None,
            )
            loaded_events = tuple(
                item
                for item in tuple(loaded_context.get("calendar_events") or ())
                if item.metadata_json.get("smoke_run_id") == smoke_run_id
            )
            loaded_assessments = tuple(
                item
                for item in tuple(loaded_context.get("portfolio_event_risk_assessments") or ())
                if item.metadata_json.get("smoke_run_id") == smoke_run_id
            )
            exposure_rows = tuple(
                row
                for row in session.query(RiskFactorExposure).all()
                if str(row.portfolio_risk_snapshot_id) == risk_snapshot.portfolio_risk_snapshot_id
                and dict(row.metadata_json or {}).get("smoke_run_id") == smoke_run_id
            )
            exposure_payload = tuple(
                {
                    "factor_type": row.factor_type,
                    "factor_name": row.factor_value,
                    "exposure": float(row.gross_exposure),
                }
                for row in exposure_rows
            )
            risk_macro_payload = build_today_risk_macro_payload(
                latest_risk=risk_snapshot,
                latest_intent=latest_intent,
                risk_macro_context=loaded_context,
                exposures=exposure_payload,
            )
    except Exception as exc:
        return {
            "status": "failed",
            "smoke_run_id": smoke_run_id,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    checks = {
        "macro_snapshot_reloaded": loaded_macro is not None
        and loaded_macro.metadata_json.get("smoke_run_id") == smoke_run_id,
        "calendar_events_reloaded": len(loaded_events) == 2,
        "event_assessments_reloaded": len(loaded_assessments) == 2,
        "today_payload_uses_canonical_regime": risk_macro_payload["command_center"]["regime"] == "risk_off",
        "today_payload_sees_event_risk": risk_macro_payload["command_center"]["event_risk_level"] == "High",
    }
    status = "passed" if all(checks.values()) else "failed"
    return {
        "status": status,
        "trade_date": trade_date.isoformat(),
        "smoke_run_id": smoke_run_id,
        "checks": checks,
        "persisted": {
            "macro_snapshot_id": macro_snapshot.macro_snapshot_id,
            "portfolio_risk_snapshot_id": risk_snapshot.portfolio_risk_snapshot_id,
            "portfolio_risk_intent_id": risk_intent.portfolio_risk_intent_id,
            "calendar_event_ids": [event.calendar_event_id for event in calendar_events],
            "portfolio_event_risk_assessment_ids": [
                assessment.portfolio_event_risk_assessment_id for assessment in event_assessments
            ],
            "risk_factor_exposure_count": len(exposures),
        },
        "reloaded": {
            "macro_snapshot_id": loaded_macro.macro_snapshot_id if loaded_macro is not None else None,
            "calendar_event_keys": [event.event_key for event in loaded_events],
            "assessment_actions": [assessment.recommended_action for assessment in loaded_assessments],
            "risk_macro_regime": risk_macro_payload["command_center"]["regime"],
            "risk_macro_event_risk_level": risk_macro_payload["command_center"]["event_risk_level"],
            "risk_macro_top_source": (
                risk_macro_payload["summary"]["top_risk_sources"][0]["label"]
                if risk_macro_payload["summary"]["top_risk_sources"]
                else None
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = run_smoke()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"[{report['status'].upper()}] trading_macro_event_db_smoke trade_date={report.get('trade_date')}")
        if report["status"] == "passed":
            print(f"smoke_run_id={report['smoke_run_id']}")
            print(f"macro_snapshot_id={report['reloaded']['macro_snapshot_id']}")
            print(
                "calendar_events={events} event_assessments={assessments} regime={regime} event_risk={event_risk}".format(
                    events=len(report["persisted"]["calendar_event_ids"]),
                    assessments=len(report["persisted"]["portfolio_event_risk_assessment_ids"]),
                    regime=report["reloaded"]["risk_macro_regime"],
                    event_risk=report["reloaded"]["risk_macro_event_risk_level"],
                )
            )
        else:
            print(f"{report.get('error_type')}: {report.get('error')}")
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
