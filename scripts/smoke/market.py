#!/usr/bin/env python3
"""Smoke checks for market data endpoints.

Checks (use --only to run a subset):
  alpaca_bars       — Alpaca /v2/stocks/bars  (fetch_daily_closes)
  finnhub_sector    — Finnhub /stock/profile2 (sector enrichment)
  finnhub_earnings  — Finnhub /calendar/earnings (earnings-in-days enrichment)
  market_snapshot   — composite get_market_snapshot via the tool registry

Examples:
  python scripts/smoke/market.py
  python scripts/smoke/market.py --only alpaca_bars
  python scripts/smoke/market.py --only finnhub_sector finnhub_earnings
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core import config as app_config  # noqa: F401
from src.tools import ToolContext, build_research_tool_registry
from src.providers.market_data import AlpacaMarketDataProvider

from scripts.smoke import SmokeCheckResult, _failed, _passed, _print_results, _skipped

_ALL_CHECKS = ("alpaca_bars", "finnhub_sector", "finnhub_earnings", "market_snapshot")


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _has_alpaca_creds() -> bool:
    return bool(
        os.getenv("ALPACA_API_KEY")
        and (os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET"))
    )


def _has_finnhub_key() -> bool:
    return bool(os.getenv("FINNHUB_API_KEY"))


# ---------------------------------------------------------------------------
# Individual endpoint checks
# ---------------------------------------------------------------------------


def _smoke_alpaca_bars(ticker: str) -> SmokeCheckResult:
    name = "alpaca_bars"
    if not _has_alpaca_creds():
        return _failed(
            name,
            "Alpaca credentials not configured. Set ALPACA_API_KEY and ALPACA_SECRET_KEY.",
        )
    provider = AlpacaMarketDataProvider()
    try:
        closes = provider.fetch_daily_closes(ticker, lookback_days=6)
    except Exception as exc:
        return _failed(name, f"fetch_daily_closes failed for {ticker}: {exc}")
    finally:
        provider.close()

    if not closes:
        return _failed(name, f"No daily close prices returned for {ticker}.")
    return _passed(
        name,
        f"Fetched {len(closes)} daily close(s) for {ticker}. Last: {closes[-1]:.2f}",
        preview={"ticker": ticker, "closes": closes[-3:], "last_price": closes[-1]},
    )


def _smoke_finnhub_sector(ticker: str) -> SmokeCheckResult:
    name = "finnhub_sector"
    if not _has_finnhub_key():
        return _skipped(name, "Skipped because FINNHUB_API_KEY is not configured.")
    provider = AlpacaMarketDataProvider()
    try:
        sector = provider._fetch_sector_from_finnhub(ticker)
    except Exception as exc:
        return _failed(name, f"Finnhub profile2 request failed for {ticker}: {exc}")
    finally:
        provider.close()

    if not sector:
        return _failed(
            name,
            f"No sector returned for {ticker}. Check FINNHUB_API_KEY permissions.",
            preview={"ticker": ticker, "sector": sector},
        )
    return _passed(
        name,
        f"Fetched sector for {ticker}: {sector!r}",
        preview={"ticker": ticker, "sector": sector},
    )


def _smoke_finnhub_earnings(ticker: str) -> SmokeCheckResult:
    name = "finnhub_earnings"
    if not _has_finnhub_key():
        return _skipped(name, "Skipped because FINNHUB_API_KEY is not configured.")
    provider = AlpacaMarketDataProvider()
    try:
        earnings_in_days = provider._fetch_earnings_in_days_from_finnhub(ticker)
    except Exception as exc:
        return _failed(name, f"Finnhub earnings calendar request failed for {ticker}: {exc}")
    finally:
        provider.close()

    # None is valid — it means no upcoming earnings in the 45-day window
    return _passed(
        name,
        (
            f"Fetched earnings calendar for {ticker}. "
            f"Next earnings: {earnings_in_days if earnings_in_days is not None else 'none in next 45 days'}"
        ),
        preview={"ticker": ticker, "earnings_in_days": earnings_in_days},
    )


def _smoke_market_snapshot(registry, ticker: str) -> SmokeCheckResult:
    name = "market_snapshot"
    if not _has_alpaca_creds():
        return _failed(
            name,
            "Alpaca credentials not configured. Set ALPACA_API_KEY and ALPACA_SECRET_KEY.",
        )
    snapshot = registry.dispatch("get_market_snapshot", {"ticker": ticker}, ToolContext())
    if snapshot.get("last_price") is None:
        return _failed(
            name,
            f"No last_price returned for {ticker}. Check Alpaca credentials and market-data permissions.",
            preview=snapshot,
        )
    if "return_since_market_open" not in snapshot:
        return _failed(
            name,
            f"Snapshot for {ticker} is missing return_since_market_open.",
            preview=snapshot,
        )
    if "session_volume" not in snapshot or "relative_volume" not in snapshot:
        return _failed(
            name,
            f"Snapshot for {ticker} is missing volume context fields.",
            preview=snapshot,
        )
    if "pe_ratio" not in snapshot or "short_interest_pct_float" not in snapshot:
        return _failed(
            name,
            f"Snapshot for {ticker} is missing fundamentals fields.",
            preview=snapshot,
        )
    technical_signals = snapshot.get("technical_signals")
    if not isinstance(technical_signals, dict):
        return _failed(
            name,
            f"Snapshot for {ticker} is missing technical_signals.",
            preview=snapshot,
        )
    momentum = technical_signals.get("momentum")
    volatility = technical_signals.get("volatility")
    if not isinstance(momentum, dict) or "rsi_3" not in momentum or "rsi_14" not in momentum:
        return _failed(
            name,
            f"Snapshot for {ticker} is missing RSI momentum signals.",
            preview=snapshot,
        )
    if (
        not isinstance(volatility, dict)
        or "atr_14" not in volatility
        or "yesterday_range" not in volatility
        or "atr_multiple" not in volatility
    ):
        return _failed(
            name,
            f"Snapshot for {ticker} is missing ATR volatility signals.",
            preview=snapshot,
        )
    since_open = snapshot.get("return_since_market_open")
    return _passed(
        name,
        (
            f"Composite snapshot for {ticker}: last_price={snapshot['last_price']:.2f}, "
            f"return_since_market_open={since_open if since_open is not None else 'n/a'}, "
            f"relative_volume={snapshot.get('relative_volume') if snapshot.get('relative_volume') is not None else 'n/a'}, "
            f"rsi_3={momentum.get('rsi_3') if momentum.get('rsi_3') is not None else 'n/a'}"
        ),
        preview=snapshot,
    )


# ---------------------------------------------------------------------------
# Standalone entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol to use for all checks.")
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
    registry = build_research_tool_registry()
    results: list[SmokeCheckResult] = []

    if "alpaca_bars" in checks:
        results.append(_smoke_alpaca_bars(ticker))
    if "finnhub_sector" in checks:
        results.append(_smoke_finnhub_sector(ticker))
    if "finnhub_earnings" in checks:
        results.append(_smoke_finnhub_earnings(ticker))
    if "market_snapshot" in checks:
        results.append(_smoke_market_snapshot(registry, ticker))

    _print_results(results, as_json=args.json)
    return 1 if any(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
