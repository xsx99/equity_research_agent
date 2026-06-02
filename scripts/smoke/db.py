#!/usr/bin/env python3
"""Smoke checks for DB-backed insider query tools."""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import desc, func, text

from src.core import config as app_config  # noqa: F401
from src.db.connection import get_session
from src.db.models import InsiderTrade
from src.research.repositories import research_repository as repository
from src.tools import ToolContext, build_research_tool_registry

from scripts.smoke import SmokeCheckResult, _failed, _passed, _print_results


@dataclass
class DbSmokeInputs:
    ticker: str
    insider_query: str
    search_query: str
    min_value: float
    days: int
    min_insiders: int


def _build_db_smoke_inputs(base_days: int) -> DbSmokeInputs:
    with get_session() as session:
        session.execute(text("SELECT 1"))
        trade = (
            session.query(InsiderTrade)
            .order_by(desc(InsiderTrade.filing_date), desc(InsiderTrade.id))
            .first()
        )
        if trade is None:
            raise RuntimeError("No rows found in insider_trades.")
        filing_date = trade.filing_date or date.today()
        days = max(base_days, (date.today() - filing_date).days + 1)
        cutoff = date.today() - timedelta(days=days)
        insider_count = (
            session.query(func.count(func.distinct(InsiderTrade.insider_name)))
            .filter(
                InsiderTrade.ticker == trade.ticker,
                InsiderTrade.filing_date >= cutoff,
            )
            .scalar()
        ) or 1

        insider_name = (trade.insider_name or trade.ticker or "").strip()
        insider_query = insider_name.split()[0] if insider_name else trade.ticker
        search_query = (trade.ticker or insider_query or "").strip()
        min_value = float(trade.total_value) if trade.total_value is not None else 0.0

        return DbSmokeInputs(
            ticker=trade.ticker,
            insider_query=insider_query,
            search_query=search_query,
            min_value=min_value,
            days=days,
            min_insiders=max(1, min(3, int(insider_count))),
        )


def _smoke_db_tools(registry, db_inputs: DbSmokeInputs) -> list[SmokeCheckResult]:
    results: list[SmokeCheckResult] = []
    with get_session() as session:
        context = ToolContext(session=session)
        checks = [
            (
                "query_recent_trades",
                {"days": db_inputs.days},
                f"Fetched recent insider trades within {db_inputs.days} day(s).",
            ),
            (
                "query_trades_by_ticker",
                {"ticker": db_inputs.ticker, "days": db_inputs.days},
                f"Fetched insider trades for ticker {db_inputs.ticker}.",
            ),
            (
                "query_trades_by_insider",
                {"name": db_inputs.insider_query, "limit": 10},
                f"Fetched insider trades for name fragment {db_inputs.insider_query!r}.",
            ),
            (
                "query_large_transactions",
                {"min_value": db_inputs.min_value, "days": db_inputs.days},
                f"Fetched large transactions at or above ${db_inputs.min_value:,.2f}.",
            ),
            (
                "query_cluster_activity",
                {"days": db_inputs.days, "min_insiders": db_inputs.min_insiders},
                (
                    "Fetched cluster activity "
                    f"with min_insiders={db_inputs.min_insiders} for the sampled window."
                ),
            ),
            (
                "search_filings",
                {"query": db_inputs.search_query, "limit": 10},
                f"Searched filings for {db_inputs.search_query!r}.",
            ),
        ]

        for tool_name, payload, success_details in checks:
            try:
                result = registry.dispatch(tool_name, payload, context)
            except Exception as exc:
                results.append(_failed(tool_name, f"Execution failed: {exc}"))
                continue
            if not result:
                results.append(
                    _failed(
                        tool_name,
                        f"Tool returned no rows for payload {payload!r}.",
                        preview=result,
                    )
                )
                continue
            preview = result[0] if isinstance(result, list) else result
            results.append(_passed(tool_name, success_details, preview=preview))

        try:
            insider_activity = repository.get_recent_insider_activity(
                session,
                ticker=db_inputs.ticker,
                as_of=datetime.now().astimezone(),
                days=db_inputs.days,
                limit=5,
            )
        except Exception as exc:
            results.append(_failed("insider_activity_summary", f"Execution failed: {exc}"))
        else:
            recent_trades = insider_activity.get("recent_trades")
            if not isinstance(insider_activity, dict) or not isinstance(recent_trades, list):
                results.append(
                    _failed(
                        "insider_activity_summary",
                        "Repository helper returned malformed insider activity payload.",
                        preview=insider_activity,
                    )
                )
            else:
                results.append(
                    _passed(
                        "insider_activity_summary",
                        f"Built insider activity summary for {db_inputs.ticker}.",
                        preview=insider_activity,
                    )
                )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-base-days",
        type=int,
        default=30,
        help="Minimum lookback window used when deriving DB smoke inputs.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    registry = build_research_tool_registry()
    try:
        db_inputs = _build_db_smoke_inputs(args.db_base_days)
    except Exception as exc:
        results: list[SmokeCheckResult] = [
            _failed(
                "database_tools",
                (
                    "Could not prepare live DB smoke inputs. "
                    "Check DATABASE_URL, Postgres availability, and insider_trades data."
                ),
                preview={"error": str(exc)},
            )
        ]
    else:
        results = _smoke_db_tools(registry, db_inputs)

    _print_results(results, as_json=args.json)
    return 1 if any(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
