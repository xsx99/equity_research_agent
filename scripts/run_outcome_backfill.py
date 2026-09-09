#!/usr/bin/env python3
"""Mature persisted candidate outcomes over an explicit source-date range."""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.connection import SessionLocal


def run_backfill(
    *,
    session: Any,
    pipeline: Any,
    start_date: date,
    end_date: date,
    apply: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    """Process each source date independently; dry-run never persists."""
    if end_date < start_date:
        raise ValueError("end_date_before_start_date")
    completed_dates: list[str] = []
    already_evaluated_dates: list[str] = []
    failed_dates: list[str] = []
    date_reports: list[dict[str, Any]] = []
    for source_date in _date_range(start_date, end_date):
        try:
            result = pipeline.run(
                evaluation_as_of_session=end_date,
                source_decision_date=source_date,
                persist=apply,
            )
            due_count = int(getattr(result, "due_checkpoint_count", 0) or 0)
            report = {
                "source_decision_date": source_date.isoformat(),
                "due_checkpoint_count": due_count,
                "created_interim_count": int(getattr(result, "created_interim_count", 0) or 0),
                "created_final_count": int(getattr(result, "created_final_count", 0) or 0),
                "pending_count": int(getattr(result, "pending_count", 0) or 0),
                "unsupported_horizon_count": int(
                    getattr(result, "unsupported_horizon_count", 0) or 0
                ),
                "provider_error_count": int(getattr(result, "provider_error_count", 0) or 0),
            }
            if due_count == 0:
                already_evaluated_dates.append(source_date.isoformat())
                report["status"] = "already_evaluated" if resume else "no_due_checkpoints"
            else:
                completed_dates.append(source_date.isoformat())
                report["status"] = "applied" if apply else "dry_run"
            if apply and due_count > 0:
                session.commit()
            else:
                session.rollback()
            date_reports.append(report)
        except Exception as exc:
            session.rollback()
            failed_dates.append(source_date.isoformat())
            date_reports.append(
                {
                    "source_decision_date": source_date.isoformat(),
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:256],
                }
            )
    status = "dry_run" if not apply else ("applied_with_failures" if failed_dates else "applied")
    return {
        "status": status,
        "apply": apply,
        "resume": resume,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "completed_dates": completed_dates,
        "already_evaluated_dates": already_evaluated_dates,
        "failed_dates": failed_dates,
        "date_reports": date_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Commit successful source dates independently")
    mode.add_argument("--dry-run", action="store_true", help="Preview only (the default)")
    parser.add_argument("--resume", action="store_true", help="Label source dates with no due checkpoints as resumed")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    session = SessionLocal()
    try:
        pipeline = _build_pipeline(session)
        report = run_backfill(
            session=session,
            pipeline=pipeline,
            start_date=args.start_date,
            end_date=args.end_date,
            apply=args.apply,
            resume=args.resume,
        )
    finally:
        session.close()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(
            "outcome backfill: {status}; completed={completed}; failed={failed}".format(
                status=report["status"],
                completed=len(report["completed_dates"]),
                failed=len(report["failed_dates"]),
            )
        )
    return 1 if report["failed_dates"] else 0


def _build_pipeline(session: Any) -> Any:
    from src.providers.market_data import AlpacaMarketDataProvider
    from src.trading.outcomes.pipeline import OutcomeEvaluationPipeline
    from src.trading.outcomes.prices import OutcomePriceLoader
    from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository

    repository = SqlAlchemyTradingRepository(session)
    return OutcomeEvaluationPipeline(
        repository=repository,
        price_loader=OutcomePriceLoader(provider=AlpacaMarketDataProvider()),
    )


def _date_range(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


if __name__ == "__main__":
    raise SystemExit(main())
