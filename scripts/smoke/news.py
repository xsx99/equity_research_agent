#!/usr/bin/env python3
"""Smoke checks for news data endpoints.

Checks (use --only to run a subset):
  finnhub_news    — Finnhub  /api/v1/company-news  (FinnhubNewsProvider)
  marketaux_news  — Marketaux /v1/news/all          (MarketauxNewsProvider)
  alpaca_news     — Alpaca   /v1beta1/news          (AlpacaNewsProvider)
  news_chain      — full fallback chain via the tool registry

Examples:
  python scripts/smoke/news.py
  python scripts/smoke/news.py --only finnhub_news
  python scripts/smoke/news.py --only marketaux_news alpaca_news
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core import config as app_config  # noqa: F401
from src.tools import ToolContext, build_research_tool_registry
from src.tools.news_data import (
    AlpacaNewsProvider,
    FinnhubNewsProvider,
    MarketauxNewsProvider,
)

from scripts.smoke import SmokeCheckResult, _failed, _passed, _print_results, _skipped

_ALL_CHECKS = ("finnhub_news", "marketaux_news", "alpaca_news", "news_chain")


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _has_finnhub_key() -> bool:
    return bool(os.getenv("FINNHUB_API_KEY"))


def _has_marketaux_key() -> bool:
    return bool(os.getenv("MARKETAUX_API_KEY"))


def _has_alpaca_creds() -> bool:
    return bool(
        os.getenv("ALPACA_API_KEY")
        and (os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET"))
    )


def _any_news_provider_configured() -> bool:
    return _has_finnhub_key() or _has_marketaux_key() or _has_alpaca_creds()


# ---------------------------------------------------------------------------
# Shared validation
# ---------------------------------------------------------------------------


def _validate_news_items(
    name: str, ticker: str, items: Any, source_label: str
) -> SmokeCheckResult:
    if not items:
        return _failed(name, f"No news items returned for {ticker} from {source_label}.")
    if not isinstance(items, list):
        return _failed(name, f"{source_label} returned non-list payload.", preview=items)
    if not all(isinstance(i, dict) and i.get("title") for i in items):
        return _failed(name, f"{source_label} items missing titles.", preview=items)
    if not all(isinstance(i, dict) and "source" in i and "signal_type" in i for i in items):
        return _failed(
            name,
            f"{source_label} items are missing source/signal_type metadata.",
            preview=items,
        )
    return _passed(
        name,
        f"Fetched {len(items)} item(s) for {ticker} from {source_label}.",
        preview=items[:2],
    )


# ---------------------------------------------------------------------------
# Individual provider checks
# ---------------------------------------------------------------------------


def _smoke_finnhub_news(ticker: str, limit: int) -> SmokeCheckResult:
    name = "finnhub_news"
    if not _has_finnhub_key():
        return _skipped(name, "Skipped because FINNHUB_API_KEY is not configured.")
    provider = FinnhubNewsProvider()
    try:
        items = provider.fetch_recent(ticker=ticker, limit=limit)
    except Exception as exc:
        return _failed(name, f"Finnhub company-news request failed for {ticker}: {exc}")
    finally:
        provider.close()
    return _validate_news_items(name, ticker, items, "Finnhub")


def _smoke_marketaux_news(ticker: str, limit: int) -> SmokeCheckResult:
    name = "marketaux_news"
    if not _has_marketaux_key():
        return _skipped(name, "Skipped because MARKETAUX_API_KEY is not configured.")
    provider = MarketauxNewsProvider()
    try:
        items = provider.fetch_recent(ticker=ticker, limit=limit)
    except Exception as exc:
        return _failed(name, f"Marketaux news request failed for {ticker}: {exc}")
    finally:
        provider.close()
    return _validate_news_items(name, ticker, items, "Marketaux")


def _smoke_alpaca_news(ticker: str, limit: int) -> SmokeCheckResult:
    name = "alpaca_news"
    if not _has_alpaca_creds():
        return _skipped(name, "Skipped because ALPACA_API_KEY / ALPACA_SECRET_KEY are not configured.")
    provider = AlpacaNewsProvider()
    try:
        items = provider.fetch_recent(ticker=ticker, limit=limit)
    except Exception as exc:
        return _failed(name, f"Alpaca news request failed for {ticker}: {exc}")
    finally:
        provider.close()
    return _validate_news_items(name, ticker, items, "Alpaca")


def _smoke_news_chain(registry, ticker: str, limit: int) -> SmokeCheckResult:
    name = "news_chain"
    if not _any_news_provider_configured():
        return _failed(
            name,
            "No news providers configured. Set FINNHUB_API_KEY, MARKETAUX_API_KEY, or Alpaca credentials.",
        )
    items = registry.dispatch("get_recent_news", {"ticker": ticker, "limit": limit}, ToolContext())
    return _validate_news_items(name, ticker, items, "fallback chain")


# ---------------------------------------------------------------------------
# Standalone entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol to use for all checks.")
    parser.add_argument("--limit", type=int, default=3, help="Max news items to request (1-5).")
    parser.add_argument(
        "--only",
        nargs="+",
        choices=_ALL_CHECKS,
        metavar="CHECK",
        help=f"Run only the specified check(s): {', '.join(_ALL_CHECKS)}. Defaults to all.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    checks: set[str] = set(args.only) if args.only else set(_ALL_CHECKS)
    ticker = args.ticker.upper()
    limit = max(1, min(args.limit, 5))
    registry = build_research_tool_registry()
    results: list[SmokeCheckResult] = []

    if "finnhub_news" in checks:
        results.append(_smoke_finnhub_news(ticker, limit))
    if "marketaux_news" in checks:
        results.append(_smoke_marketaux_news(ticker, limit))
    if "alpaca_news" in checks:
        results.append(_smoke_alpaca_news(ticker, limit))
    if "news_chain" in checks:
        results.append(_smoke_news_chain(registry, ticker, limit))

    _print_results(results, as_json=args.json)
    return 1 if any(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
