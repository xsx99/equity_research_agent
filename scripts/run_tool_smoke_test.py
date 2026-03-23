#!/usr/bin/env python3
"""Run live smoke checks against the research tool registry.

Use --only to target a specific group instead of running all checks:
  python scripts/run_tool_smoke_test.py --only market
  python scripts/run_tool_smoke_test.py --only news

Or run individual smoke modules directly (supports their own --only flag):
  python scripts/smoke/market.py --only alpaca_bars
  python scripts/smoke/news.py --only finnhub_news marketaux_news
  python scripts/smoke/db.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import config as app_config  # noqa: F401
from src.tools import build_research_tool_registry

from scripts.smoke import SmokeCheckResult, _failed, _print_results
from scripts.smoke.db import _build_db_smoke_inputs, _smoke_db_tools
from scripts.smoke.market import (
    _smoke_alpaca_bars,
    _smoke_finnhub_earnings,
    _smoke_finnhub_sector,
    _smoke_market_snapshot,
)
from scripts.smoke.news import (
    _smoke_alpaca_news,
    _smoke_finnhub_news,
    _smoke_marketaux_news,
    _smoke_news_chain,
)

_ALL_GROUPS = ("market", "news", "db")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
        "--only",
        nargs="+",
        choices=_ALL_GROUPS,
        metavar="GROUP",
        help=f"Run only the specified group(s): {', '.join(_ALL_GROUPS)}. Defaults to all.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output instead of human-readable lines.",
    )
    args = parser.parse_args()

    groups: set[str] = set(args.only) if args.only else set(_ALL_GROUPS)
    ticker = args.ticker.upper()
    registry = build_research_tool_registry()
    results: list[SmokeCheckResult] = []

    if "market" in groups:
        results.append(_smoke_alpaca_bars(ticker))
        results.append(_smoke_finnhub_sector(ticker))
        results.append(_smoke_finnhub_earnings(ticker))
        results.append(_smoke_market_snapshot(registry, ticker))
    if "news" in groups:
        limit = max(1, min(args.news_limit, 5))
        results.append(_smoke_finnhub_news(ticker, limit))
        results.append(_smoke_marketaux_news(ticker, limit))
        results.append(_smoke_alpaca_news(ticker, limit))
        results.append(_smoke_news_chain(registry, ticker, limit))

    if "db" in groups:
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
