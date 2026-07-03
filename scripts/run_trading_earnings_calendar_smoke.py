#!/usr/bin/env python3
"""Diagnose Nasdaq earnings-calendar availability for the Event Risk surface."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.providers.market_data.nasdaq_earnings import NasdaqEarningsCalendar


def run_smoke(
    ticker: str = "MU",
    *,
    as_of: date | None = None,
    horizon_days: int = 45,
) -> dict[str, Any]:
    as_of_date = as_of or datetime.now(timezone.utc).date()
    calendar = NasdaqEarningsCalendar(horizon_days=horizon_days)
    earnings_date = calendar.next_earnings_date(ticker, as_of_date)
    if earnings_date is not None:
        earnings_in_days = (earnings_date - as_of_date).days
    else:
        earnings_in_days = None
    return {
        "ticker": ticker.upper(),
        "as_of": as_of_date,
        "earnings_in_days": earnings_in_days,
        "earnings_date": earnings_date,
        "horizon_days": horizon_days,
        "source": "nasdaq",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", nargs="?", default="MU")
    parser.add_argument("--as-of", dest="as_of", help="Calendar lookup date in YYYY-MM-DD format")
    parser.add_argument("--horizon-days", type=int, default=45)
    args = parser.parse_args(argv)

    load_dotenv()
    as_of = date.fromisoformat(args.as_of) if args.as_of else None

    result = run_smoke(args.ticker, as_of=as_of, horizon_days=args.horizon_days)
    print(json.dumps(result, default=_json_default, indent=2, sort_keys=True))
    return 0


def _json_default(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    raise SystemExit(main())
