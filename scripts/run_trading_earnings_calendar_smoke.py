#!/usr/bin/env python3
"""Diagnose missing earnings events for the trading Event Risk surface.

Failure causes and how to tell them apart:
1. ``FINNHUB_API_KEY`` missing: this script prints
   ``FINNHUB_API_KEY not set — earnings events cannot be generated`` and exits
   non-zero. The runtime cannot fetch Finnhub earnings data, so no earnings
   event can be built.
2. Finnhub returns no upcoming earnings data for the ticker: the key is set,
   the request succeeds, but ``earnings_in_days`` / ``earnings_date`` are
   ``null``. That usually means the event is outside the provider's 45-day
   window, the symbol is wrong, or Finnhub has no row.
3. Finnhub returns earnings data but the ticker still does not appear on
   ``/today``: the ticker likely was not part of the scored pre-open
   candidate set, so the pre-open calendar builder never emitted an event for
   it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.providers.market_data import AlpacaMarketDataProvider


def run_smoke(ticker: str = "MU") -> dict[str, Any]:
    provider = AlpacaMarketDataProvider()
    try:
        payload = provider._fetch_earnings_in_days_from_finnhub(ticker)
    finally:
        provider.close()
    return {
        "ticker": ticker.upper(),
        "earnings_in_days": payload.get("earnings_in_days"),
        "earnings_date": payload.get("earnings_date"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", nargs="?", default="MU")
    args = parser.parse_args(argv)

    load_dotenv()
    if not os.getenv("FINNHUB_API_KEY"):
        print(
            "FINNHUB_API_KEY not set — earnings events cannot be generated",
            file=sys.stderr,
        )
        return 1

    result = run_smoke(args.ticker)
    print(json.dumps(result, default=_json_default, indent=2, sort_keys=True))
    return 0


def _json_default(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    raise SystemExit(main())
