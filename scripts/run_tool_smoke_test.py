#!/usr/bin/env python3
"""Run live smoke checks against the research tool registry."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import json
import os
from pathlib import Path
import sys
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import desc, func, text

from src.core import config as app_config  # noqa: F401  # loads repo-root .env
from src.db.connection import get_session
from src.db.models import InsiderTrade
from src.tools import ToolContext, build_research_tool_registry

SmokeStatus = Literal["passed", "failed", "skipped"]


@dataclass
class SmokeCheckResult:
    name: str
    status: SmokeStatus
    details: str
    preview: Any | None = None


@dataclass
class DbSmokeInputs:
    ticker: str
    insider_query: str
    search_query: str
    min_value: float
    days: int
    min_insiders: int


def _passed(name: str, details: str, preview: Any | None = None) -> SmokeCheckResult:
    return SmokeCheckResult(name=name, status="passed", details=details, preview=preview)


def _failed(name: str, details: str, preview: Any | None = None) -> SmokeCheckResult:
    return SmokeCheckResult(name=name, status="failed", details=details, preview=preview)


def _skipped(name: str, details: str) -> SmokeCheckResult:
    return SmokeCheckResult(name=name, status="skipped", details=details)


def _configured_news_providers() -> list[str]:
    providers: list[str] = []
    if os.getenv("FINNHUB_API_KEY"):
        providers.append("Finnhub")
    if os.getenv("MARKETAUX_API_KEY"):
        providers.append("Marketaux")
    if os.getenv("ALPACA_API_KEY") and (
        os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")
    ):
        providers.append("Alpaca")
    return providers


def _preview(value: Any, max_chars: int = 280) -> str:
    rendered = json.dumps(value, ensure_ascii=False, default=str)
    if len(rendered) <= max_chars:
        return rendered
    return f"{rendered[: max_chars - 3]}..."


def _print_results(results: list[SmokeCheckResult], *, as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "name": result.name,
                        "status": result.status,
                        "details": result.details,
                        "preview": result.preview,
                    }
                    for result in results
                ],
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        return

    for result in results:
        print(f"[{result.status.upper():7}] {result.name}: {result.details}")
        if result.preview is not None:
            print(f"          preview={_preview(result.preview)}")

    passed = sum(result.status == "passed" for result in results)
    failed = sum(result.status == "failed" for result in results)
    skipped = sum(result.status == "skipped" for result in results)
    print()
    print(f"Summary: {passed} passed, {failed} failed, {skipped} skipped")


def _smoke_market_tool(registry, ticker: str) -> SmokeCheckResult:
    if not (
        os.getenv("ALPACA_API_KEY")
        and (os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET"))
    ):
        return _failed(
            "get_market_snapshot",
            (
                "Alpaca credentials are not configured. "
                "Set ALPACA_API_KEY and ALPACA_SECRET_KEY or ALPACA_API_SECRET first."
            ),
        )
    snapshot = registry.dispatch("get_market_snapshot", {"ticker": ticker}, ToolContext())
    if snapshot.get("last_price") is None:
        return _failed(
            "get_market_snapshot",
            "No live price returned. Check Alpaca credentials, network reachability, and market-data permissions.",
            preview=snapshot,
        )
    return _passed(
        "get_market_snapshot",
        f"Fetched live market snapshot for {ticker}.",
        preview=snapshot,
    )


def _smoke_news_tool(registry, ticker: str, limit: int) -> SmokeCheckResult:
    if not _configured_news_providers():
        return _failed(
            "get_recent_news",
            (
                "No news providers are configured. "
                "Set FINNHUB_API_KEY, MARKETAUX_API_KEY, or Alpaca credentials first."
            ),
        )
    items = registry.dispatch(
        "get_recent_news",
        {"ticker": ticker, "limit": limit},
        ToolContext(),
    )
    if not items:
        providers = _configured_news_providers()
        provider_hint = ", ".join(providers) if providers else "none"
        return _failed(
            "get_recent_news",
            f"No news items returned for {ticker}. Configured providers: {provider_hint}.",
            preview=items,
        )
    if not all(isinstance(item, dict) and item.get("title") for item in items):
        return _failed(
            "get_recent_news",
            "News payload shape is invalid; expected non-empty titles.",
            preview=items,
        )
    return _passed(
        "get_recent_news",
        f"Fetched {len(items)} live news item(s) for {ticker}.",
        preview=items[:2],
    )


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
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="AAPL", help="Ticker used for live market/news smoke checks.")
    parser.add_argument(
        "--news-limit",
        type=int,
        default=3,
        help="Number of live news items to request (bounded by the tool to 1-5).",
    )
    parser.add_argument(
        "--db-base-days",
        type=int,
        default=30,
        help="Minimum lookback window used when deriving DB-backed smoke inputs.",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip DB-backed insider query smoke checks.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output instead of human-readable lines.",
    )
    args = parser.parse_args()

    registry = build_research_tool_registry()
    results = [
        _smoke_market_tool(registry, args.ticker.upper()),
        _smoke_news_tool(registry, args.ticker.upper(), args.news_limit),
    ]

    if args.skip_db:
        results.append(_skipped("database_tools", "Skipped by --skip-db."))
    else:
        try:
            db_inputs = _build_db_smoke_inputs(args.db_base_days)
        except Exception as exc:
            results.append(
                _failed(
                    "database_tools",
                    (
                        "Could not prepare live DB smoke inputs. "
                        "Check DATABASE_URL, Postgres availability, and insider_trades data."
                    ),
                    preview={"error": str(exc)},
                )
            )
        else:
            results.extend(_smoke_db_tools(registry, db_inputs))

    _print_results(results, as_json=args.json)
    return 1 if any(result.status == "failed" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
